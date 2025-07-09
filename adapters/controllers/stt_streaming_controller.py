"""
STT Streaming Controller Module

This module provides WebSocket endpoints for real-time Speech-to-Text streaming.
It handles WebSocket connections, message parsing, and coordinates with the
streaming domain service to provide real-time transcription capabilities.
"""

import json
import base64
import asyncio
from typing import Dict, Any, Optional
from flask import Blueprint
from flask_socketio import SocketIO, emit, disconnect
from marshmallow import Schema, fields, ValidationError

from core.interfaces.stt_streaming_domain_service_interface import STTStreamingDomainServiceInterface
from core.domain.stt_streaming_model import (
    MessageType,
    StartSessionMessage,
    AudioChunkMessage,
    InterimResultMessage,
    FinalResultMessage,
    EndSessionMessage,
    ErrorMessage,
    StreamingConfig
)
from adapters.loggers.logger_adapter import app_logger
from app.api_response import ApiResponse


class StreamingConfigSchema(Schema):
    """Schema for validating streaming configuration."""
    language = fields.Str(missing="en-US", validate=lambda x: len(x) >= 2)
    enable_automatic_punctuation = fields.Bool(missing=True)
    interim_results = fields.Bool(missing=True)
    model = fields.Str(missing="latest_long")
    sample_rate = fields.Int(missing=16000, validate=lambda x: x in [8000, 16000, 32000, 44100, 48000])
    encoding = fields.Str(missing="LINEAR16")


class StartSessionMessageSchema(Schema):
    """Schema for validating start session messages."""
    type = fields.Str(required=True, validate=lambda x: x == MessageType.START_SESSION)
    config = fields.Nested(StreamingConfigSchema, missing=dict)


class AudioChunkMessageSchema(Schema):
    """Schema for validating audio chunk messages."""
    type = fields.Str(required=True, validate=lambda x: x == MessageType.AUDIO_CHUNK)
    data = fields.Str(required=True)
    sequence = fields.Int(missing=0)


class EndSessionMessageSchema(Schema):
    """Schema for validating end session messages."""
    type = fields.Str(required=True, validate=lambda x: x == MessageType.END_SESSION)


class STTStreamingController:
    """
    Controller for handling STT streaming WebSocket connections.
    
    This controller manages WebSocket connections for real-time speech-to-text
    transcription, handling session lifecycle and audio streaming.
    """

    def __init__(self, streaming_service: STTStreamingDomainServiceInterface):
        """
        Initialize the STT streaming controller.

        Args:
            streaming_service: STT streaming domain service
        """
        self._streaming_service = streaming_service
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._start_session_schema = StartSessionMessageSchema()
        self._audio_chunk_schema = AudioChunkMessageSchema()
        self._end_session_schema = EndSessionMessageSchema()

    def register_events(self, socketio: SocketIO) -> None:
        """
        Register WebSocket event handlers.

        Args:
            socketio: SocketIO instance
        """

        @socketio.on('connect', namespace='/api/stt/stream')
        def handle_connect():
            """Handle client connection."""
            client_id = self._get_client_id()
            app_logger.info(f"STT streaming client connected: {client_id}")
            emit('connected', {'status': 'connected', 'client_id': client_id})

        @socketio.on('disconnect', namespace='/api/stt/stream')
        def handle_disconnect():
            """Handle client disconnection."""
            client_id = self._get_client_id()
            app_logger.info(f"STT streaming client disconnected: {client_id}")
            
            # Clean up any active sessions for this client
            asyncio.create_task(self._cleanup_client_sessions(client_id))

        @socketio.on('message', namespace='/api/stt/stream')
        def handle_message(data):
            """Handle incoming WebSocket messages."""
            client_id = self._get_client_id()
            
            try:
                # Parse message
                if isinstance(data, str):
                    message_data = json.loads(data)
                else:
                    message_data = data

                message_type = message_data.get('type')
                app_logger.debug(f"Received message type '{message_type}' from client {client_id}")

                # Handle different message types
                if message_type == MessageType.START_SESSION:
                    asyncio.create_task(self._handle_start_session(client_id, message_data))
                elif message_type == MessageType.AUDIO_CHUNK:
                    asyncio.create_task(self._handle_audio_chunk(client_id, message_data))
                elif message_type == MessageType.END_SESSION:
                    asyncio.create_task(self._handle_end_session(client_id, message_data))
                else:
                    self._send_error(client_id, "INVALID_MESSAGE_TYPE", f"Unknown message type: {message_type}")

            except json.JSONDecodeError as e:
                app_logger.error(f"JSON decode error from client {client_id}: {str(e)}")
                self._send_error(client_id, "INVALID_JSON", "Invalid JSON message format")
            except Exception as e:
                app_logger.error(f"Error handling message from client {client_id}: {str(e)}")
                self._send_error(client_id, "MESSAGE_HANDLING_ERROR", str(e))

    async def _handle_start_session(self, client_id: str, message_data: Dict[str, Any]) -> None:
        """
        Handle start session message.

        Args:
            client_id: WebSocket client ID
            message_data: Message data
        """
        try:
            # Validate message
            validated_data = self._start_session_schema.load(message_data)
            config_data = validated_data.get('config', {})

            # Create streaming config
            config = StreamingConfig(
                language=config_data.get('language', 'en-US'),
                enable_automatic_punctuation=config_data.get('enable_automatic_punctuation', True),
                interim_results=config_data.get('interim_results', True),
                model=config_data.get('model', 'latest_long'),
                sample_rate=config_data.get('sample_rate', 16000),
                encoding=config_data.get('encoding', 'LINEAR16')
            )

            # Create session request
            from core.domain.stt_streaming_model import STTStreamingSessionRequest
            session_request = STTStreamingSessionRequest(
                language_code=config.language,
                sample_rate_hertz=config.sample_rate,
                encoding=config.encoding,
                enable_automatic_punctuation=config.enable_automatic_punctuation,
                model=config.model,
                use_enhanced=True
            )

            # Start streaming session
            session_response = await self._streaming_service.start_streaming_session(session_request)
            session_id = session_response.session_id

            # Store session info
            self._active_sessions[client_id] = {
                'session_id': session_id,
                'config': config,
                'audio_generator': None,
                'results_task': None
            }

            # Send success response
            emit('message', {
                'type': 'session_started',
                'session_id': session_id,
                'status': 'active'
            }, namespace='/api/stt/stream')

            app_logger.info(f"Started STT streaming session {session_id} for client {client_id}")

        except ValidationError as e:
            app_logger.error(f"Validation error in start_session for client {client_id}: {e.messages}")
            self._send_error(client_id, "VALIDATION_ERROR", str(e.messages))
        except Exception as e:
            app_logger.error(f"Error starting session for client {client_id}: {str(e)}")
            self._send_error(client_id, "SESSION_START_ERROR", str(e))

    async def _handle_audio_chunk(self, client_id: str, message_data: Dict[str, Any]) -> None:
        """
        Handle audio chunk message.

        Args:
            client_id: WebSocket client ID
            message_data: Message data
        """
        try:
            # Check if session exists
            if client_id not in self._active_sessions:
                self._send_error(client_id, "NO_ACTIVE_SESSION", "No active session found")
                return

            # Validate message
            validated_data = self._audio_chunk_schema.load(message_data)
            audio_data_b64 = validated_data['data']
            sequence = validated_data.get('sequence', 0)

            # Decode base64 audio data
            try:
                audio_data = base64.b64decode(audio_data_b64)
            except Exception as e:
                self._send_error(client_id, "INVALID_AUDIO_DATA", "Failed to decode base64 audio data")
                return

            session_info = self._active_sessions[client_id]
            session_id = session_info['session_id']

            # Initialize audio generator if not exists
            if session_info['audio_generator'] is None:
                session_info['audio_generator'] = self._create_audio_generator()
                # Start processing audio stream
                session_info['results_task'] = asyncio.create_task(
                    self._process_audio_stream(client_id, session_id, session_info['audio_generator'])
                )

            # Add audio chunk to generator
            await session_info['audio_generator'].put(audio_data)

            app_logger.debug(f"Processed audio chunk {sequence} for session {session_id}")

        except ValidationError as e:
            app_logger.error(f"Validation error in audio_chunk for client {client_id}: {e.messages}")
            self._send_error(client_id, "VALIDATION_ERROR", str(e.messages))
        except Exception as e:
            app_logger.error(f"Error processing audio chunk for client {client_id}: {str(e)}")
            self._send_error(client_id, "AUDIO_PROCESSING_ERROR", str(e))

    async def _handle_end_session(self, client_id: str, message_data: Dict[str, Any]) -> None:
        """
        Handle end session message.

        Args:
            client_id: WebSocket client ID
            message_data: Message data
        """
        try:
            # Validate message
            self._end_session_schema.load(message_data)

            # Check if session exists
            if client_id not in self._active_sessions:
                self._send_error(client_id, "NO_ACTIVE_SESSION", "No active session found")
                return

            session_info = self._active_sessions[client_id]
            session_id = session_info['session_id']

            # End audio stream
            if session_info['audio_generator']:
                await session_info['audio_generator'].put(None)  # Signal end of stream

            # Wait for results task to complete
            if session_info['results_task']:
                try:
                    await asyncio.wait_for(session_info['results_task'], timeout=5.0)
                except asyncio.TimeoutError:
                    session_info['results_task'].cancel()

            # End streaming session
            await self._streaming_service.end_streaming_session(session_id)

            # Clean up session
            del self._active_sessions[client_id]

            # Send success response
            emit('message', {
                'type': 'session_ended',
                'session_id': session_id,
                'status': 'ended'
            }, namespace='/api/stt/stream')

            app_logger.info(f"Ended STT streaming session {session_id} for client {client_id}")

        except ValidationError as e:
            app_logger.error(f"Validation error in end_session for client {client_id}: {e.messages}")
            self._send_error(client_id, "VALIDATION_ERROR", str(e.messages))
        except Exception as e:
            app_logger.error(f"Error ending session for client {client_id}: {str(e)}")
            self._send_error(client_id, "SESSION_END_ERROR", str(e))

    async def _process_audio_stream(self, client_id: str, session_id: str, audio_generator) -> None:
        """
        Process audio stream and emit results.

        Args:
            client_id: WebSocket client ID
            session_id: Session ID
            audio_generator: Audio data generator
        """
        try:
            # Create async generator for audio chunks
            async def audio_chunks():
                while True:
                    chunk = await audio_generator.get()
                    if chunk is None:  # End of stream
                        break
                    yield chunk

            # Process audio stream
            async for result in self._streaming_service.process_audio_stream(session_id, audio_chunks()):
                if hasattr(result, 'error_code'):
                    # Error result
                    emit('message', {
                        'type': MessageType.ERROR,
                        'session_id': session_id,
                        'error_code': result.error_code,
                        'error_message': result.error_message,
                        'timestamp': result.timestamp
                    }, namespace='/api/stt/stream')
                else:
                    # Recognition result
                    message_type = MessageType.FINAL_RESULT if result.is_final else MessageType.INTERIM_RESULT
                    emit('message', {
                        'type': message_type,
                        'session_id': session_id,
                        'text': result.transcript,  # Use 'transcript' property
                        'confidence': result.confidence,
                        'is_final': result.is_final,
                        'timestamp': result.timestamp
                    }, namespace='/api/stt/stream')

        except Exception as e:
            app_logger.error(f"Error processing audio stream for session {session_id}: {str(e)}")
            self._send_error(client_id, "STREAM_PROCESSING_ERROR", str(e))

    def _create_audio_generator(self):
        """Create an async queue for audio data."""
        return asyncio.Queue()

    async def _cleanup_client_sessions(self, client_id: str) -> None:
        """
        Clean up sessions for a disconnected client.

        Args:
            client_id: WebSocket client ID
        """
        if client_id in self._active_sessions:
            session_info = self._active_sessions[client_id]
            session_id = session_info['session_id']

            try:
                # End audio stream
                if session_info['audio_generator']:
                    await session_info['audio_generator'].put(None)

                # Cancel results task
                if session_info['results_task']:
                    session_info['results_task'].cancel()

                # End streaming session
                await self._streaming_service.end_streaming_session(session_id)

                # Remove from active sessions
                del self._active_sessions[client_id]

                app_logger.info(f"Cleaned up session {session_id} for disconnected client {client_id}")

            except Exception as e:
                app_logger.error(f"Error cleaning up session for client {client_id}: {str(e)}")

    def _send_error(self, client_id: str, error_code: str, error_message: str) -> None:
        """
        Send error message to client.

        Args:
            client_id: WebSocket client ID
            error_code: Error code
            error_message: Error message
        """
        emit('message', {
            'type': MessageType.ERROR,
            'error_code': error_code,
            'error_message': error_message,
            'timestamp': asyncio.get_event_loop().time()
        }, namespace='/api/stt/stream')

    def _get_client_id(self) -> str:
        """Get the current WebSocket client ID."""
        from flask import request
        return request.sid


def create_stt_streaming_blueprint(streaming_service: STTStreamingDomainServiceInterface) -> Blueprint:
    """
    Create and configure the STT streaming blueprint.

    Args:
        streaming_service: STT streaming domain service

    Returns:
        Configured Flask blueprint
    """
    blueprint = Blueprint('stt_streaming', __name__)
    controller = STTStreamingController(streaming_service)
    
    # Store controller reference for SocketIO registration
    blueprint.streaming_controller = controller
    
    return blueprint
