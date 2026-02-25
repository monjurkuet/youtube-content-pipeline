"""Core package for video content pipeline."""

from src.core.config import Settings, get_settings
from src.core.http_session import (
    close_all_sessions,
    close_session,
    get,
    get_session,
    post,
    request,
)
from src.core.logging_config import (
    get_logger,
    log_api_request,
    log_channel_sync_event,
    log_transcription_event,
    setup_logging,
)
from src.core.schemas import ProcessingResult, RawTranscript, TranscriptSegment

__all__ = [
    "Settings",
    "get_settings",
    "ProcessingResult",
    "RawTranscript",
    "TranscriptSegment",
    # Logging
    "setup_logging",
    "get_logger",
    "log_api_request",
    "log_transcription_event",
    "log_channel_sync_event",
    # HTTP
    "get_session",
    "close_session",
    "close_all_sessions",
    "request",
    "get",
    "post",
]
