"""
Google STT Streaming Client Module

This module provides the implementation for Google Cloud Speech-to-Text streaming client.
It handles real-time speech recognition using WebSocket connections.
"""

import asyncio
import base64
import os
from typing import Dict, AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

from google.cloud import speech
from google.api_core import exceptions as gcp_exceptions

from adapters.loggers.logger_adapter import app_logger
from core.domain.stt_streaming_model import (
    StreamingSessionRequest,
    StreamingAudioRequest,
    StreamingResponse
)
from core.interfaces.stt_streaming_client_interface import STTStreamingClientInterface


class AudioGenerator:
    """
    Audio generator for streaming recognition.
    
    This class manages audio chunks for a streaming session and provides
    them as an async generator for Google Cloud Speech API.
    """

    def __init__(self):
        self._audio_queue = asyncio.Queue()
        self._finished = False

    async def add_chunk(self, audio_data: bytes) -> None:
        """Add audio chunk to the queue."""
        if not self._finished:
            await self._audio_queue.put(audio_data)

    async def finish(self) -> None:
        """Mark the audio stream as finished."""
        self._finished = True
        await self._audio_queue.put(None)  # Sentinel value

    async def __aiter__(self):
        """Async iterator for audio chunks."""
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:  # Sentinel value indicates end
                break
            yield chunk


class GoogleSTTStreamingClient(STTStreamingClientInterface):
    """
    Google Cloud Speech-to-Text streaming client implementation.

    This class provides real-time speech recognition capabilities using
    Google Cloud Speech-to-Text API with WebSocket-like streaming.
    """

    FORMAT_MAPPING = {
        "webm": speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        "wav": speech.RecognitionConfig.AudioEncoding.LINEAR16,
        "flac": speech.RecognitionConfig.AudioEncoding.FLAC,
        "opus": speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
    }

    def __init__(self) -> None:
        """Initialize the Google STT streaming client."""
        creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "tts-key.json")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds
        self.client = speech.SpeechClient()
        self._sessions: Dict[str, Dict] = {}
        self._executor = ThreadPoolExecutor(max_workers=10)

    async def start_streaming_session(self, request: StreamingSessionRequest) -> bool:
        """
        Start a new streaming recognition session.

        Args:
            request: Streaming session configuration.

        Returns:
            bool: True if session started successfully, False otherwise.
        """
        try:
            session_id = request.session_id
            config = request.config

            # Create recognition config
            recognition_config = speech.RecognitionConfig(
                encoding=self.FORMAT_MAPPING.get(
                    config.encoding,
                    speech.RecognitionConfig.AudioEncoding.WEBM_OPUS
                ),
                sample_rate_hertz=config.sample_rate,
                language_code=config.language,
                enable_automatic_punctuation=config.enable_automatic_punctuation,
                model=config.model,
                use_enhanced=True,
                max_alternatives=1,
            )

            # Create streaming config
            streaming_config = speech.StreamingRecognitionConfig(
                config=recognition_config,
                interim_results=config.interim_results,
                single_utterance=False,
            )

            # Create audio generator
            audio_generator = AudioGenerator()

            # Store session info
            self._sessions[session_id] = {
                "config": streaming_config,
                "audio_generator": audio_generator,
                "results_queue": asyncio.Queue(),
                "active": True,
                "sequence": 0,
            }

            # Start recognition task
            asyncio.create_task(self._run_recognition(session_id))

            app_logger.info(f"Started streaming session: {session_id}")
            return True

        except Exception as e:
            app_logger.error(f"Failed to start streaming session: {str(e)}")
            return False

    async def process_audio_chunk(self, request: StreamingAudioRequest) -> None:
        """
        Process an audio chunk for streaming recognition.

        Args:
            request: Audio chunk data with session info.
        """
        try:
            session_id = request.session_id
            session = self._sessions.get(session_id)

            if not session or not session["active"]:
                app_logger.warning(f"Session not found or inactive: {session_id}")
                return

            # Decode base64 audio data
            audio_data = base64.b64decode(request.audio_data)

            # Add to audio generator
            await session["audio_generator"].add_chunk(audio_data)

            app_logger.debug(f"Processed audio chunk for session {session_id}, sequence: {request.sequence}")

        except Exception as e:
            app_logger.error(f"Failed to process audio chunk: {str(e)}")

    async def get_streaming_results(self, session_id: str) -> AsyncGenerator[StreamingResponse, None]:
        """
        Get streaming recognition results for a session.

        Args:
            session_id: Session identifier.

        Yields:
            StreamingResponse: Recognition results as they become available.
        """
        session = self._sessions.get(session_id)
        if not session:
            app_logger.warning(f"Session not found: {session_id}")
            return

        results_queue = session["results_queue"]

        try:
            while session.get("active", False):
                try:
                    # Wait for results with timeout
                    result = await asyncio.wait_for(results_queue.get(), timeout=1.0)
                    if result is None:  # Sentinel value
                        break
                    yield result
                except asyncio.TimeoutError:
                    continue  # Continue waiting for results

        except Exception as e:
            app_logger.error(f"Error getting streaming results: {str(e)}")
            yield StreamingResponse(
                session_id=session_id,
                success=False,
                error_message=f"Error getting results: {str(e)}"
            )

    async def end_streaming_session(self, session_id: str) -> bool:
        """
        End a streaming recognition session.

        Args:
            session_id: Session identifier.

        Returns:
            bool: True if session ended successfully, False otherwise.
        """
        try:
            session = self._sessions.get(session_id)
            if not session:
                app_logger.warning(f"Session not found: {session_id}")
                return False

            # Mark session as inactive
            session["active"] = False

            # Finish audio generator
            await session["audio_generator"].finish()

            # Add sentinel to results queue
            await session["results_queue"].put(None)

            # Remove session
            del self._sessions[session_id]

            app_logger.info(f"Ended streaming session: {session_id}")
            return True

        except Exception as e:
            app_logger.error(f"Failed to end streaming session: {str(e)}")
            return False

    async def _run_recognition(self, session_id: str) -> None:
        """
        Run the streaming recognition in a background task.

        Args:
            session_id: Session identifier.
        """
        try:
            session = self._sessions.get(session_id)
            if not session:
                return

            streaming_config = session["config"]
            audio_generator = session["audio_generator"]
            results_queue = session["results_queue"]

            # Create audio request generator
            def audio_request_generator():
                async def async_gen():
                    async for chunk in audio_generator:
                        yield speech.StreamingRecognizeRequest(audio_content=chunk)
                
                # Convert async generator to sync for Google API
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    async_iter = async_gen()
                    while True:
                        try:
                            chunk = loop.run_until_complete(async_iter.__anext__())
                            yield chunk
                        except StopAsyncIteration:
                            break
                finally:
                    loop.close()

            # Run recognition in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                self._process_recognition_sync,
                session_id,
                streaming_config,
                audio_request_generator(),
                results_queue
            )

        except Exception as e:
            app_logger.error(f"Recognition task failed for session {session_id}: {str(e)}")

    def _process_recognition_sync(self, session_id: str, streaming_config, requests, results_queue) -> None:
        """
        Process recognition synchronously (runs in thread pool).

        Args:
            session_id: Session identifier.
            streaming_config: Google streaming configuration.
            requests: Audio request generator.
            results_queue: Queue for results.
        """
        try:
            # Start streaming recognition
            responses = self.client.streaming_recognize(streaming_config, requests)

            sequence = 0
            for response in responses:
                if not self._sessions.get(session_id, {}).get("active", False):
                    break

                for result in response.results:
                    if result.alternatives:
                        alternative = result.alternatives[0]
                        
                        # Create response
                        streaming_response = StreamingResponse(
                            session_id=session_id,
                            text=alternative.transcript,
                            confidence=alternative.confidence,
                            is_final=result.is_final,
                            sequence=sequence,
                            success=True
                        )

                        # Add to results queue (sync)
                        asyncio.run_coroutine_threadsafe(
                            results_queue.put(streaming_response),
                            asyncio.get_event_loop()
                        )

                        sequence += 1

                        app_logger.debug(
                            f"Recognition result for session {session_id}: "
                            f"'{alternative.transcript}' (final: {result.is_final})"
                        )

        except gcp_exceptions.GoogleAPIError as e:
            app_logger.error(f"Google API error in recognition: {str(e)}")
            error_response = StreamingResponse(
                session_id=session_id,
                success=False,
                error_message=f"Google API error: {str(e)}"
            )
            asyncio.run_coroutine_threadsafe(
                results_queue.put(error_response),
                asyncio.get_event_loop()
            )
        except Exception as e:
            app_logger.error(f"Unexpected error in recognition: {str(e)}")
            error_response = StreamingResponse(
                session_id=session_id,
                success=False,
                error_message=f"Recognition error: {str(e)}"
            )
            asyncio.run_coroutine_threadsafe(
                results_queue.put(error_response),
                asyncio.get_event_loop()
            )
