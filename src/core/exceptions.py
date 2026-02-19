"""Custom exceptions for the transcription pipeline."""


class PipelineError(Exception):
    """Base exception for pipeline errors."""

    pass


class TranscriptError(PipelineError):
    """Failed to acquire transcript."""

    pass


class YouTubeAPIError(TranscriptError):
    """YouTube Transcript API failed."""

    pass


class WhisperError(TranscriptError):
    """Whisper transcription failed."""

    pass


class VideoDownloadError(PipelineError):
    """Failed to download video."""

    pass
