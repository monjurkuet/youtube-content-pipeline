"""Database models and schemas.

This module defines database-related Pydantic models for validation
and serialization. Note: MongoDB documents are schemaless, but these
models help with validation and type safety.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TranscriptDB(BaseModel):
    """Transcript document model for MongoDB.

    This model represents the structure of a transcript document
    stored in MongoDB.
    """

    video_id: str = Field(..., description="YouTube video ID")
    title: str = Field(..., description="Video title")
    channel_id: str = Field(..., description="Channel ID")
    channel_name: str = Field(..., description="Channel name")
    duration_seconds: float = Field(..., description="Video duration in seconds")
    language: str = Field(..., description="Transcript language code")
    transcript_source: str = Field(..., description="Source of transcript")
    segments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Transcript segments with timestamps",
    )
    full_text: str = Field(..., description="Complete transcript text")
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Creation timestamp",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Last update timestamp",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "video_id": "dQw4w9WgXcQ",
                "title": "Example Video",
                "channel_id": "UC1234567890",
                "channel_name": "Example Channel",
                "duration_seconds": 212.5,
                "language": "en",
                "transcript_source": "youtube_auto",
                "segments": [{"start": 0.0, "end": 5.0, "text": "Hello world"}],
                "full_text": "Hello world",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            }
        }
    }


class ChannelDB(BaseModel):
    """Channel document model for MongoDB."""

    channel_id: str = Field(..., description="YouTube channel ID")
    channel_name: str = Field(..., description="Channel name")
    channel_handle: str | None = Field(default=None, description="Channel handle (@username)")
    channel_url: str = Field(..., description="Channel URL")
    subscriber_count: int | None = Field(default=None, description="Subscriber count")
    tracked_since: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When tracking started",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Last update timestamp",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional channel metadata",
    )


class VideoMetadataDB(BaseModel):
    """Video metadata document model for MongoDB."""

    video_id: str = Field(..., description="YouTube video ID")
    title: str = Field(..., description="Video title")
    channel_id: str = Field(..., description="Channel ID")
    channel_name: str = Field(..., description="Channel name")
    published_at: str = Field(..., description="Video publish date")
    duration_seconds: float | None = Field(default=None, description="Video duration")
    transcript_status: str = Field(
        default="pending",
        description="Transcription status",
    )
    transcript_id: str | None = Field(
        default=None,
        description="Reference to transcript document",
    )
    transcript_error: str | None = Field(
        default=None,
        description="Error message if transcription failed",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Creation timestamp",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Last update timestamp",
    )
