"""Pydantic models for API requests and responses."""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChannelSyncMode(str, Enum):
    """Supported channel sync modes."""

    RECENT = "recent"
    ALL = "all"

# =============================================================================
# Request Models
# =============================================================================


class TranscriptionRequest(BaseModel):
    """Request model for video transcription submission."""

    source: str = Field(
        ...,
        description="YouTube URL, video URL, or local file path",
        examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
    )
    webhook_url: str | None = Field(
        default=None,
        description="Optional webhook URL to notify when transcription completes",
    )
    priority: Literal["low", "normal", "high"] = Field(
        default="normal",
        description="Processing priority for the job",
    )
    save_to_db: bool = Field(
        default=True,
        description="Whether to save transcript to database",
    )

    model_config = {
        "strict": True,
        "json_schema_extra": {
            "example": {
                "source": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "webhook_url": "https://callback.example.com/webhook",
                "priority": "normal",
                "save_to_db": True,
            }
        }
    }


class AddChannelsFromVideosRequest(BaseModel):
    """Request model for adding channels from video URLs."""

    video_urls: list[str] = Field(
        ...,
        description="List of YouTube video URLs",
        min_length=1,
        examples=[
            [
                "https://youtu.be/S9s1rZKO_18",
                "https://youtu.be/fpKtJLc5Ntg",
            ]
        ],
    )
    auto_sync: bool = Field(
        default=True,
        description="Whether to sync channel videos after adding",
    )
    sync_mode: ChannelSyncMode = Field(
        default=ChannelSyncMode.RECENT,
        description="Sync mode: 'recent' for ~15 videos, 'all' for all videos",
    )
    sync_max_videos_per_channel: int | None = Field(
        default=None,
        ge=1,
        description="Maximum videos to sync per channel when sync_mode='all'",
    )

    @model_validator(mode="after")
    def validate_sync_limits(self) -> "AddChannelsFromVideosRequest":
        """Require explicit bounds for expensive full-channel sync requests."""
        if (
            self.auto_sync
            and self.sync_mode == ChannelSyncMode.ALL
            and self.sync_max_videos_per_channel is None
        ):
            raise ValueError(
                "sync_max_videos_per_channel is required when auto_sync=true and sync_mode='all'"
            )
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "video_urls": [
                    "https://youtu.be/S9s1rZKO_18",
                    "https://youtu.be/fpKtJLc5Ntg",
                ],
                "auto_sync": True,
                "sync_mode": "recent",
                "sync_max_videos_per_channel": None,
            }
        }
    }


# =============================================================================
# Response Models
# =============================================================================


class TranscriptionJobResponse(BaseModel):
    """Response model for transcription job submission."""

    job_id: str = Field(..., description="Unique job identifier")
    status: Literal["queued", "processing", "completed", "failed"] = Field(
        ...,
        description="Current job status",
    )
    video_id: str = Field(..., description="Video identifier")
    message: str = Field(..., description="Human-readable status message")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the job was created",
    )
    estimated_completion: datetime | None = Field(
        default=None,
        description="Estimated completion time (if available)",
    )


class JobStatusResponse(BaseModel):
    """Response model for job status check."""

    job_id: str = Field(..., description="Unique job identifier")
    status: Literal["queued", "processing", "completed", "failed"] = Field(
        ...,
        description="Current job status",
    )
    video_id: str = Field(..., description="Video identifier")
    progress_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Progress percentage (0-100)",
    )
    current_step: str = Field(
        default="",
        description="Description of current processing step",
    )
    started_at: datetime | None = Field(
        default=None,
        description="When processing started",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="When processing completed",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if job failed",
    )
    result_url: str | None = Field(
        default=None,
        description="URL to fetch results (when completed)",
    )


class TranscriptSummaryResponse(BaseModel):
    """Summary response model for transcript list endpoints."""

    document_id: str | None = Field(
        default=None,
        validation_alias="_id",
        serialization_alias="_id",
        description="MongoDB document identifier",
    )
    video_id: str = Field(..., description="YouTube video identifier")
    title: str | None = Field(default=None, description="Video title")
    channel_id: str | None = Field(default=None, description="YouTube channel identifier")
    channel_name: str | None = Field(default=None, description="Channel name")
    duration_seconds: float | None = Field(default=None, description="Video duration in seconds")
    language: str | None = Field(default=None, description="Transcript language")
    transcript_source: str | None = Field(default=None, description="Transcript provider/source")
    segment_count: int | None = Field(default=None, description="Number of transcript segments")
    total_text_length: int | None = Field(
        default=None,
        description="Total transcript text length in characters",
    )
    source_type: str | None = Field(default=None, description="Original source type")
    source_url: str | None = Field(default=None, description="Original source URL")
    analyzed_at: datetime | None = Field(default=None, description="Analysis timestamp")
    created_at: datetime | None = Field(default=None, description="Creation timestamp")
    updated_at: datetime | None = Field(default=None, description="Last update timestamp")

    model_config = ConfigDict(populate_by_name=True)


class ChannelAddedEntry(BaseModel):
    """Response model for a single added channel."""

    url: str = Field(..., description="Video URL that was processed")
    channel_id: str = Field(..., description="YouTube channel ID")
    channel_handle: str = Field(..., description="Normalized channel handle")
    channel_title: str = Field(..., description="Channel title/name")
    database_id: str = Field(..., description="MongoDB document ID")
    resolution_source: str | None = Field(
        default=None,
        description="Strategy that resolved the channel information",
    )
    sync_videos_fetched: int | None = Field(
        default=None,
        description="Number of videos fetched during sync",
    )
    sync_videos_new: int | None = Field(
        default=None,
        description="Number of new videos added during sync",
    )
    sync_error: str | None = Field(
        default=None,
        description="Error message if sync failed",
    )


class ChannelSkippedEntry(BaseModel):
    """Response model for a skipped channel."""

    url: str = Field(..., description="Video URL that was skipped")
    channel_id: str = Field(..., description="YouTube channel ID")
    channel_handle: str = Field(..., description="Channel handle")


class ChannelFailedEntry(BaseModel):
    """Response model for a failed channel addition."""

    url: str = Field(..., description="Video URL that failed")
    video_id: str | None = Field(
        default=None,
        description="Video ID if extracted",
    )
    error: str = Field(..., description="Error message")
    error_stage: str | None = Field(
        default=None,
        description="Pipeline stage where the failure occurred",
    )
    resolution_source: str | None = Field(
        default=None,
        description="Strategy that was being used when the failure occurred",
    )
    retryable: bool = Field(
        default=False,
        description="Whether this failure is likely to succeed on retry",
    )


class AddChannelsFromVideosResponse(BaseModel):
    """Response model for adding channels from video URLs."""

    success: bool = Field(..., description="Whether operation completed")
    added: list[ChannelAddedEntry] = Field(
        ...,
        description="List of channels successfully added",
    )
    skipped_duplicate: list[ChannelSkippedEntry] = Field(
        ...,
        description="Channels skipped (duplicate in batch)",
    )
    skipped_existing: list[ChannelSkippedEntry] = Field(
        ...,
        description="Channels already being tracked",
    )
    failed: list[ChannelFailedEntry] = Field(
        ...,
        description="Channels that failed to add",
    )
    total_processed: int = Field(..., description="Total URLs processed")
    total_added: int = Field(..., description="Total channels added")
    total_skipped: int = Field(..., description="Total channels skipped")
    total_failed: int = Field(..., description="Total channels failed")
