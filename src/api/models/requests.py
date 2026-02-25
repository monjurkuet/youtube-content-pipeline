"""Pydantic models for API requests and responses."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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
    sync_mode: Literal["recent", "all"] = Field(
        default="recent",
        description="Sync mode: 'recent' for ~15 videos, 'all' for all videos",
    )


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
        default_factory=datetime.utcnow,
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


class ChannelAddedEntry(BaseModel):
    """Response model for a single added channel."""

    url: str = Field(..., description="Video URL that was processed")
    channel_id: str = Field(..., description="YouTube channel ID")
    channel_handle: str = Field(..., description="Normalized channel handle")
    channel_title: str = Field(..., description="Channel title/name")
    database_id: str = Field(..., description="MongoDB document ID")
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
