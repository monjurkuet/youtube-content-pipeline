"""Statistics and metrics endpoints.

This module provides endpoints for:
- Dashboard statistics
- System health metrics
- Content counts
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from src.api.dependencies import get_db
from src.api.security import validate_api_key
from src.database.redis import get_redis_manager

router = APIRouter(prefix="/stats", tags=["stats"])


class StatsResponse(BaseModel):
    """Response model for statistics endpoint."""

    # Content counts
    total_channels: int = Field(..., description="Total number of tracked channels")
    total_videos: int = Field(..., description="Total number of tracked videos")
    total_transcripts: int = Field(..., description="Total number of transcripts")

    # Video status breakdown
    videos_pending: int = Field(..., description="Videos pending transcription")
    videos_completed: int = Field(..., description="Videos with transcripts")
    videos_failed: int = Field(..., description="Videos with failed transcription")

    # Transcript sources
    transcripts_by_source: dict[str, int] = Field(
        default_factory=dict,
        description="Transcript count by source type",
    )

    # Job stats
    active_jobs: int = Field(..., description="Currently active transcription jobs")

    # System info
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When these stats were collected",
    )
    redis_available: bool = Field(..., description="Whether Redis is available")


@router.get(
    "/",
    response_model=StatsResponse,
    summary="Get system statistics",
    description="""
    Get comprehensive statistics about the transcription pipeline.

    Returns counts for:
    - Tracked channels, videos, and transcripts
    - Video transcription status breakdown
    - Transcripts by source type
    - Active job count
    - System status (Redis availability)
    """,
    operation_id="get_stats",
    responses={
        200: {
            "description": "System statistics",
            "content": {
                "application/json": {
                    "example": {
                        "total_channels": 5,
                        "total_videos": 1500,
                        "total_transcripts": 1200,
                        "videos_pending": 250,
                        "videos_completed": 1200,
                        "videos_failed": 50,
                        "transcripts_by_source": {
                            "youtube_auto": 800,
                            "whisper_openvino": 400,
                        },
                        "active_jobs": 3,
                        "timestamp": "2024-01-15T10:30:00Z",
                        "redis_available": True,
                    }
                }
            },
        },
    },
)
async def get_stats(
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> StatsResponse:
    """Get system statistics.

    Args:
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        StatsResponse with comprehensive metrics
    """
    # Get counts
    total_channels = await db.channels.count_documents({})
    total_videos = await db.video_metadata.count_documents({})
    total_transcripts = await db.transcripts.count_documents({})

    # Video status breakdown
    videos_pending = await db.video_metadata.count_documents(
        {"transcript_status": "pending"}
    )
    videos_completed = await db.video_metadata.count_documents(
        {"transcript_status": "completed"}
    )
    videos_failed = await db.video_metadata.count_documents(
        {"transcript_status": "failed"}
    )

    # Transcripts by source
    transcripts_by_source: dict[str, int] = {}
    async for doc in db.transcripts.aggregate(
        [
            {"$group": {"_id": "$transcript_source", "count": {"$sum": 1}}},
        ]
    ):
        source = doc["_id"] or "unknown"
        transcripts_by_source[source] = doc["count"]

    # Active jobs
    redis_manager = get_redis_manager()
    active_jobs = 0
    redis_available = redis_manager.is_available

    if redis_available:
        try:
            # Count active jobs from Redis
            jobs = await redis_manager.list_jobs(limit=1000)
            active_jobs = sum(
                1
                for j in jobs
                if j.get("status") in ("queued", "processing")
            )
        except Exception:
            redis_available = False

    return StatsResponse(
        total_channels=total_channels,
        total_videos=total_videos,
        total_transcripts=total_transcripts,
        videos_pending=videos_pending,
        videos_completed=videos_completed,
        videos_failed=videos_failed,
        transcripts_by_source=transcripts_by_source,
        active_jobs=active_jobs,
        redis_available=redis_available,
    )
