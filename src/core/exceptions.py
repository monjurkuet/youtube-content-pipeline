"""Custom exceptions for the transcription pipeline."""

from src.core.schemas import TranscriptionFailure


class PipelineError(Exception):
    """Base exception for pipeline errors."""


class TranscriptionFailureError(PipelineError):
    """Structured transcription failure."""

    def __init__(self, failure: TranscriptionFailure):
        """Initialize the exception with structured failure data."""
        super().__init__(failure.message)
        self.failure = failure


class TranscriptError(PipelineError):
    """Failed to acquire transcript."""


class YouTubeAPIError(TranscriptError):
    """YouTube Transcript API failed."""


class WhisperError(TranscriptError):
    """Whisper transcription failed."""


class VideoDownloadError(PipelineError):
    """Failed to download video."""
