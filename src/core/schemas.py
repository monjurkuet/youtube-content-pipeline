"""Pydantic schemas for transcription pipeline."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    source: Literal["youtube_api", "whisper"]
    language: str = "en"

    @property
    def full_text(self) -> str:
        return " ".join([s.text for s in self.segments])

    @property
    def duration(self) -> float:
        if not self.segments:
            return 0.0
        return self.segments[-1].end


class TranscriptDocument(BaseModel):
    """Transcript document for MongoDB storage with full segments and metadata."""

    video_id: str
    source_type: Literal["youtube", "url", "local"]
    source_url: str | None = None
    title: str | None = None

    # Transcript metadata
    transcript_source: Literal["youtube_api", "whisper"]
    language: str = "en"
    segment_count: int
    duration_seconds: float
    total_text_length: int

    # Full segments with timestamps
    segments: list[TranscriptSegment]

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    analyzed_at: datetime | None = None

    def model_dump_for_mongo(self) -> dict:
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
    transcript_source: Literal["youtube_api", "whisper"]
    segment_count: int
    duration_seconds: float
    total_text_length: int
    language: str = "en"

    # Processing metadata
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds_total: float = 0.0
    saved_to_db: bool = False

    def model_dump_for_mongo(self) -> dict:
        """Convert to dict suitable for MongoDB storage."""
        data = self.model_dump()
        data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        return data
