"""
STT Streaming Domain Models Module

This module defines the core domain models for real-time STT streaming,
including WebSocket message protocols and session configuration.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class MessageType(str, Enum):
    """Types of WebSocket messages for STT streaming."""
    START_SESSION = "start_session"
    AUDIO_CHUNK = "audio_chunk"
    INTERIM_RESULT = "interim_result"
    FINAL_RESULT = "final_result"
    END_SESSION = "end_session"
    ERROR = "error"


@dataclass
class StreamingConfig:
    """
    Configuration for STT streaming session.

    Attributes:
        language: Language code for recognition (e.g., "en-US").
        enable_automatic_punctuation: Whether to enable automatic punctuation.
        interim_results: Whether to return interim results.
        model: Recognition model to use.
        sample_rate: Audio sample rate in Hz.
        encoding: Audio encoding format.
    """
    language: str = "en-US"
    enable_automatic_punctuation: bool = True
    interim_results: bool = True
    model: str = "latest_long"
    sample_rate: int = 48000
    encoding: str = "webm"


@dataclass
class StartSessionMessage:
    """
    Message to start a streaming session.

    Attributes:
        type: Message type (always "start_session").
        config: Streaming configuration.
    """
    type: str = MessageType.START_SESSION
    config: StreamingConfig = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = StreamingConfig()


@dataclass
class AudioChunkMessage:
    """
    Message containing audio chunk data.

    Attributes:
        type: Message type (always "audio_chunk").
        data: Base64-encoded audio data.
        sequence: Sequence number for ordering.
    """
    type: str = MessageType.AUDIO_CHUNK
    data: str = ""
    sequence: int = 0


@dataclass
class InterimResultMessage:
    """
    Message containing interim recognition result.

    Attributes:
        type: Message type (always "interim_result").
        text: Transcribed text (partial).
        confidence: Recognition confidence score.
        is_final: Whether this is a final result.
        sequence: Sequence number for ordering.
    """
    type: str = MessageType.INTERIM_RESULT
    text: str = ""
    confidence: float = 0.0
    is_final: bool = False
    sequence: int = 0


@dataclass
class FinalResultMessage:
    """
    Message containing final recognition result.

    Attributes:
        type: Message type (always "final_result").
        text: Transcribed text (final).
        confidence: Recognition confidence score.
        is_final: Whether this is a final result.
        sequence: Sequence number for ordering.
    """
    type: str = MessageType.FINAL_RESULT
    text: str = ""
    confidence: float = 0.0
    is_final: bool = True
    sequence: int = 0


@dataclass
class EndSessionMessage:
    """
    Message to end a streaming session.

    Attributes:
        type: Message type (always "end_session").
    """
    type: str = MessageType.END_SESSION


@dataclass
class ErrorMessage:
    """
    Message containing error information.

    Attributes:
        type: Message type (always "error").
        message: Error description.
        code: Optional error code.
    """
    type: str = MessageType.ERROR
    message: str = ""
    code: Optional[str] = None


@dataclass
class StreamingSessionRequest:
    """
    Request to start a streaming session.

    Attributes:
        session_id: Unique session identifier.
        config: Streaming configuration.
    """
    session_id: str
    config: StreamingConfig


@dataclass
class StreamingAudioRequest:
    """
    Request containing audio chunk for streaming.

    Attributes:
        session_id: Session identifier.
        audio_data: Base64-encoded audio data.
        sequence: Sequence number.
    """
    session_id: str
    audio_data: str
    sequence: int


@dataclass
class StreamingResponse:
    """
    Response from streaming recognition.

    Attributes:
        session_id: Session identifier.
        text: Transcribed text.
        confidence: Recognition confidence.
        is_final: Whether this is a final result.
        sequence: Sequence number.
        success: Whether the operation was successful.
        error_message: Error message if operation failed.
    """
    session_id: str
    text: str = ""
    confidence: float = 0.0
    is_final: bool = False
    sequence: int = 0
    success: bool = True
    error_message: Optional[str] = None


@dataclass
class STTStreamingSessionRequest:
    """
    Request to start an STT streaming session.

    Attributes:
        language_code: Language code for recognition.
        sample_rate_hertz: Audio sample rate in Hz.
        encoding: Audio encoding format.
        enable_automatic_punctuation: Whether to enable automatic punctuation.
        model: Recognition model to use.
        use_enhanced: Whether to use enhanced model.
    """
    language_code: str = "en-US"
    sample_rate_hertz: int = 48000
    encoding: str = "WEBM_OPUS"
    enable_automatic_punctuation: bool = True
    model: str = "latest_long"
    use_enhanced: bool = False


@dataclass
class STTStreamingSessionResponse:
    """
    Response from starting an STT streaming session.

    Attributes:
        session_id: Unique session identifier.
        status: Session status.
        message: Status message.
    """
    session_id: str
    status: str
    message: str


@dataclass
class STTStreamingResult:
    """
    Result from STT streaming recognition.

    Attributes:
        session_id: Session identifier.
        transcript: Recognized text.
        confidence: Recognition confidence score.
        is_final: Whether this is a final result.
        timestamp: Result timestamp.
    """
    session_id: str = ""
    transcript: str = ""
    confidence: float = 0.0
    is_final: bool = False
    timestamp: float = 0.0


@dataclass
class STTStreamingError:
    """
    Error result from STT streaming.

    Attributes:
        session_id: Session identifier.
        error_code: Error code.
        error_message: Error description.
        timestamp: Error timestamp.
    """
    session_id: str
    error_code: str
    error_message: str
    timestamp: float
