"""Pydantic schemas for channel tracking module."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class VideoMetadata(BaseModel):
    """Video metadata from YouTube."""

    video_id: str
    title: str
    description: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    published_at: datetime | None = None
    channel_id: str | None = None
    channel_title: str | None = None


class VideoMetadataDocument(BaseModel):
    """Video metadata document for MongoDB storage."""

    video_id: str
    channel_id: str
    title: str
    description: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    published_at: datetime | None = None
    transcript_status: Literal["pending", "completed", "failed"] = "pending"
    transcript_id: str | None = None
    synced_at: datetime = Field(default_factory=datetime.utcnow)

    def model_dump_for_mongo(self) -> dict[str, Any]:
        """Convert to dict suitable for MongoDB storage."""
        data = self.model_dump()
        data["synced_at"] = self.synced_at.isoformat()
        if self.published_at:
            data["published_at"] = self.published_at.isoformat()
        return data


class ChannelDocument(BaseModel):
    """Channel document for MongoDB storage."""

    channel_id: str
    channel_handle: str
    channel_title: str
    channel_url: str
    tracked_since: datetime = Field(default_factory=datetime.utcnow)
    last_synced: datetime | None = None
    total_videos_tracked: int = 0
    sync_mode: Literal["recent", "all"] = "recent"

    def model_dump_for_mongo(self) -> dict[str, Any]:
        """Convert to dict suitable for MongoDB storage."""
        data = self.model_dump()
        data["tracked_since"] = self.tracked_since.isoformat()
        if self.last_synced:
            data["last_synced"] = self.last_synced.isoformat()
        return data


class SyncResult(BaseModel):
    """Result of channel sync operation."""

    channel_id: str
    channel_handle: str
    channel_title: str
    sync_mode: Literal["recent", "all"]
    videos_fetched: int
    videos_new: int
    videos_existing: int
    sync_completed_at: datetime = Field(default_factory=datetime.utcnow)
