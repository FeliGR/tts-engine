"""
STT Streaming Client Interface Module

This module defines the interface for STT streaming clients that handle
real-time speech recognition using WebSocket connections.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator
from core.domain.stt_streaming_model import (
    StreamingSessionRequest,
    StreamingAudioRequest,
    StreamingResponse
)


class STTStreamingClientInterface(ABC):
    """
    Interface for STT streaming clients.

    This interface defines the contract for clients that handle
    real-time speech-to-text streaming operations.
    """

    @abstractmethod
    async def start_streaming_session(self, request: StreamingSessionRequest) -> bool:
        """
        Start a new streaming recognition session.

        Args:
            request: Streaming session configuration.

        Returns:
            bool: True if session started successfully, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def process_audio_chunk(self, request: StreamingAudioRequest) -> None:
        """
        Process an audio chunk for streaming recognition.

        Args:
            request: Audio chunk data with session info.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_streaming_results(self, session_id: str) -> AsyncGenerator[StreamingResponse, None]:
        """
        Get streaming recognition results for a session.

        Args:
            session_id: Session identifier.

        Yields:
            StreamingResponse: Recognition results as they become available.
        """
        raise NotImplementedError

    @abstractmethod
    async def end_streaming_session(self, session_id: str) -> bool:
        """
        End a streaming recognition session.

        Args:
            session_id: Session identifier.

        Returns:
            bool: True if session ended successfully, False otherwise.
        """
        raise NotImplementedError
