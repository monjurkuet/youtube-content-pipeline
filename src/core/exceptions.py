"""Custom exceptions for the LLM-driven pipeline."""


class PipelineError(Exception):
    """Base exception for pipeline errors."""

    pass


class SourceIdentificationError(PipelineError):
    """Failed to identify video source type."""

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


class FrameExtractionError(PipelineError):
    """Failed to extract frames from video."""

    pass


class LLMAgentError(PipelineError):
    """LLM agent failed to process."""

    pass


class TranscriptAgentError(LLMAgentError):
    """Transcript intelligence agent failed."""

    pass


class FrameAgentError(LLMAgentError):
    """Frame intelligence agent failed."""

    pass


class FrameAgentBatchError(FrameAgentError):
    """Batch frame analysis failed, can retry individually."""

    pass


class SynthesisAgentError(LLMAgentError):
    """Synthesis agent failed."""

    pass


class SchemaValidationError(PipelineError):
    """LLM output failed schema validation."""

    pass


class CacheError(PipelineError):
    """Cache operation failed."""

    pass


class DatabaseError(PipelineError):
    """Database operation failed."""

    pass
