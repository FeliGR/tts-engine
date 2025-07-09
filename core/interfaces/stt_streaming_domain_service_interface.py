"""
STT Streaming Domain Service Interface Module

This module defines the interface for STT streaming domain services that handle
the core business logic for real-time speech-to-text operations.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator
from core.domain.stt_streaming_model import (
    STTStreamingSessionRequest,
    STTStreamingSessionResponse,
    STTStreamingResult
)


class STTStreamingDomainServiceInterface(ABC):
    """
    Interface for STT streaming domain services.

    This interface defines the contract for services that handle
    the core business logic of real-time speech-to-text streaming.
    """

    @abstractmethod
    async def start_streaming_session(self, request: STTStreamingSessionRequest) -> STTStreamingSessionResponse:
        """
        Start a new streaming STT session.

        Args:
            request: Session configuration request

        Returns:
            Session response with session ID
        """
        raise NotImplementedError

    @abstractmethod
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
        """
        raise NotImplementedError

    @abstractmethod
    async def end_streaming_session(self, session_id: str) -> bool:
        """
        End a streaming STT session.

        Args:
            session_id: ID of the session to end

        Returns:
            True if session was ended successfully
        """
        raise NotImplementedError
