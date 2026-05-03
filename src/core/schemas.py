"""Pydantic schemas for transcription pipeline."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# Raw transcript models (input)
class TranscriptSegment(BaseModel):
    """A single transcript segment."""

    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


class RawTranscript(BaseModel):
    """Raw transcript before processing."""

    video_id: str
    segments: list[TranscriptSegment]
    source: Literal["youtube_api", "whisper", "groq_whisper", "local_service"]
    language: str = "en"

    @property
    def full_text(self) -> str:
        return " ".join([s.text for s in self.segments])

    @property
    def duration(self) -> float:
        if not self.segments:
            return 0.0
        return self.segments[-1].end


TranscriptionFailureCategory = Literal[
    "invalid_source",
    "geo_restricted",
    "members_only",
    "age_restricted",
    "private",
    "unavailable",
    "live_stream",
    "temporary_block",
    "timeout",
    "remote_service",
    "provider_error",
    "database",
    "unknown",
]

TranscriptionFailureStage = Literal[
    "source_identification",
    "youtube_api",
    "download",
    "transcription",
    "database",
    "pipeline",
]


class TranscriptionFailure(BaseModel):
    """Structured failure details for transcription jobs."""

    message: str
    category: TranscriptionFailureCategory
    retryable: bool = False
    stage: TranscriptionFailureStage
    video_id: str | None = None


class TranscriptDocument(BaseModel):
    """Transcript document for MongoDB storage with full segments and metadata."""

    video_id: str
    source_type: Literal["youtube", "url", "local"]
    source_url: str | None = None
    title: str | None = None
    channel_id: str | None = None

    # Transcript metadata
    transcript_source: Literal["youtube_api", "whisper", "groq_whisper", "local_service"]
    language: str = "en"
    segment_count: int
    duration_seconds: float
    total_text_length: int

    # Full segments with timestamps
    segments: list[TranscriptSegment]

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    analyzed_at: datetime | None = None

    def model_dump_for_mongo(self) -> dict[str, Any]:
        """Convert to dict suitable for MongoDB storage."""
        data = self.model_dump()
        data["created_at"] = self.created_at.isoformat()
        if self.analyzed_at:
            data["analyzed_at"] = self.analyzed_at.isoformat()
        return data

    @classmethod
    def from_raw_transcript(
        cls,
        raw_transcript: RawTranscript,
        source_type: str,
        source_url: str | None = None,
        title: str | None = None,
    ) -> "TranscriptDocument":
        """Create transcript document from RawTranscript."""

        # Validate source_type
        valid_source_types: tuple[str, ...] = ("youtube", "url", "local")
        if source_type not in valid_source_types:
            raise ValueError(f"Invalid source_type: {source_type!r}. Must be one of {valid_source_types}")

        return cls(
            video_id=raw_transcript.video_id,
            source_type=source_type,  # type: ignore
            source_url=source_url,
            title=title,
            transcript_source=raw_transcript.source,
            language=raw_transcript.language,
            segment_count=len(raw_transcript.segments),
            duration_seconds=raw_transcript.duration,
            total_text_length=len(raw_transcript.full_text),
            segments=raw_transcript.segments,
        )


class ProcessingResult(BaseModel):
    """Result of the transcription pipeline processing."""

    # Identity
    video_id: str
    source_type: Literal["youtube", "url", "local"]
    source_url: str | None = None

    # Transcript info
    transcript_source: Literal["youtube_api", "whisper", "groq_whisper", "local_service"]
    segment_count: int
    duration_seconds: float
    total_text_length: int
    language: str = "en"

    # Processing metadata
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds_total: float = 0.0
    saved_to_db: bool = False

    # Extra info
    success: bool = True
    error: str | None = None
    failure: TranscriptionFailure | None = None
    transcript_id: str | None = None

    @model_validator(mode="after")
    def sync_failure_fields(self) -> "ProcessingResult":
        """Keep compatibility fields aligned with structured failures."""
        if self.failure:
            self.success = False
            self.error = self.failure.message
        return self

    def model_dump_for_mongo(self) -> dict:
        """Convert to dict suitable for MongoDB storage."""
        data = self.model_dump()
        data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        return data


class SyncResult(BaseModel):
    """Result of a channel sync operation."""

    channel_id: str
    channel_handle: str
    channel_title: str
    videos_fetched: int
    videos_new: int
    videos_existing: int
    sync_mode: str = "recent"
    success: bool = True
    error: str | None = None
