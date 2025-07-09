"""
Domain service for handling Speech-to-Text streaming operations.
Coordinates between the streaming client and provides business logic for streaming sessions.
"""

import asyncio
import base64
from typing import Dict, AsyncGenerator, Optional
from uuid import uuid4

from core.interfaces.stt_streaming_domain_service_interface import STTStreamingDomainServiceInterface
from core.interfaces.stt_streaming_client_interface import STTStreamingClientInterface
from core.interfaces.logger_interface import ILogger
from core.domain.stt_streaming_model import (
    STTStreamingSessionRequest,
    STTStreamingSessionResponse,
    STTStreamingResult,
    STTStreamingError
)
from core.domain.exceptions import InvalidInputError, ExternalServiceError


class STTStreamingDomainService(STTStreamingDomainServiceInterface):
    """
    Domain service for Speech-to-Text streaming operations.
    Manages streaming sessions and coordinates with the underlying STT client.
    """

    def __init__(self, stt_streaming_client: STTStreamingClientInterface, logger: ILogger):
        """
        Initialize the STT streaming domain service.

        Args:
            stt_streaming_client: Client for STT streaming operations
            logger: Logger interface for logging
        """
        self._stt_streaming_client = stt_streaming_client
        self._logger = logger
        self._active_sessions: Dict[str, Dict] = {}

    async def start_streaming_session(self, request: STTStreamingSessionRequest) -> STTStreamingSessionResponse:
        """
        Start a new streaming STT session.

        Args:
            request: Session configuration request

        Returns:
            Session response with session ID

        Raises:
            InvalidInputError: If request is invalid
            ExternalServiceError: If STT service fails
        """
        try:
            # Validate request
            if not request.language_code:
                raise InvalidInputError("Language code is required")

            # Generate session ID
            session_id = str(uuid4())

            # Initialize session state
            session_config = {
                'language_code': request.language_code,
                'sample_rate_hertz': request.sample_rate_hertz,
                'encoding': request.encoding,
                'enable_automatic_punctuation': request.enable_automatic_punctuation,
                'model': request.model,
                'use_enhanced': request.use_enhanced,
                'created_at': asyncio.get_event_loop().time(),
                'active': True
            }

            self._active_sessions[session_id] = session_config

            self._logger.info(f"Started STT streaming session {session_id} with config: {session_config}")

            return STTStreamingSessionResponse(
                session_id=session_id,
                status="active",
                message="Streaming session started successfully"
            )

        except Exception as e:
            self._logger.error(f"Failed to start streaming session: {str(e)}")
            if isinstance(e, InvalidInputError):
                raise
            raise ExternalServiceError(f"Failed to start streaming session: {str(e)}") from e

    async def process_audio_stream(
        self,
        session_id: str,
        audio_generator: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[STTStreamingResult, None]:
        """
        Process streaming audio data and yield recognition results.

        Args:
            session_id: ID of the streaming session
            audio_generator: Async generator yielding audio chunks

        Yields:
            STT streaming results (interim and final)

        Raises:
            InvalidInputError: If session is invalid
            ExternalServiceError: If STT processing fails
        """
        try:
            # Validate session
            if session_id not in self._active_sessions:
                raise InvalidInputError(f"Invalid session ID: {session_id}")

            session_config = self._active_sessions[session_id]
            if not session_config.get('active'):
                raise InvalidInputError(f"Session {session_id} is not active")

            self._logger.info(f"Processing audio stream for session {session_id}")

            # The existing streaming client uses a different approach
            # We need to process audio chunks through the client
            async for audio_chunk in audio_generator:
                if audio_chunk:
                    # Create audio request
                    from core.domain.stt_streaming_model import StreamingAudioRequest
                    audio_request = StreamingAudioRequest(
                        session_id=session_id,
                        audio_data=base64.b64encode(audio_chunk).decode('utf-8'),
                        sequence=0  # You might want to track sequence numbers
                    )
                    
                    # Process audio chunk
                    await self._stt_streaming_client.process_audio_chunk(audio_request)

            # Get results from the client
            async for result in self._stt_streaming_client.get_streaming_results(session_id):
                if not result.success:
                    # Error result
                    error_result = STTStreamingError(
                        session_id=session_id,
                        error_code="PROCESSING_ERROR",
                        error_message=result.error_message or "Unknown error",
                        timestamp=asyncio.get_event_loop().time()
                    )
                    yield error_result
                else:
                    # Success result - convert to STTStreamingResult
                    streaming_result = STTStreamingResult(
                        session_id=session_id,
                        transcript=result.text,
                        confidence=result.confidence,
                        is_final=result.is_final,
                        timestamp=asyncio.get_event_loop().time()
                    )
                    yield streaming_result

        except Exception as e:
            self._logger.error(f"Error processing audio stream for session {session_id}: {str(e)}")
            
            # Yield error result
            error_result = STTStreamingError(
                session_id=session_id,
                error_code="PROCESSING_ERROR",
                error_message=str(e),
                timestamp=asyncio.get_event_loop().time()
            )
            yield error_result

            if isinstance(e, InvalidInputError):
                raise
            raise ExternalServiceError(f"Audio stream processing failed: {str(e)}") from e

    async def end_streaming_session(self, session_id: str) -> bool:
        """
        End a streaming STT session.

        Args:
            session_id: ID of the session to end

        Returns:
            True if session was ended successfully

        Raises:
            InvalidInputError: If session ID is invalid
        """
        try:
            if session_id not in self._active_sessions:
                raise InvalidInputError(f"Invalid session ID: {session_id}")

            # Mark session as inactive
            self._active_sessions[session_id]['active'] = False
            self._active_sessions[session_id]['ended_at'] = asyncio.get_event_loop().time()

            self._logger.info(f"Ended STT streaming session {session_id}")

            # Clean up session after some time (keep for debugging/logging)
            # In production, you might want to implement proper cleanup
            
            return True

        except Exception as e:
            self._logger.error(f"Failed to end streaming session {session_id}: {str(e)}")
            if isinstance(e, InvalidInputError):
                raise
            raise ExternalServiceError(f"Failed to end session: {str(e)}") from e

    def get_active_sessions(self) -> Dict[str, Dict]:
        """
        Get information about active streaming sessions.

        Returns:
            Dictionary of active sessions with their configurations
        """
        return {
            session_id: config 
            for session_id, config in self._active_sessions.items() 
            if config.get('active', False)
        }

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """
        Get information about a specific session.

        Args:
            session_id: ID of the session

        Returns:
            Session configuration dictionary or None if not found
        """
        return self._active_sessions.get(session_id)
