"""Custom exceptions for the transcription pipeline."""


class PipelineError(Exception):
    """Base exception for pipeline errors."""


class TranscriptError(PipelineError):
    """Failed to acquire transcript."""


class YouTubeAPIError(TranscriptError):
    """YouTube Transcript API failed."""


class WhisperError(TranscriptError):
    """Whisper transcription failed."""


class VideoDownloadError(PipelineError):
    """Failed to download video."""
