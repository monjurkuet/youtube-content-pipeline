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
