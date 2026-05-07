"""Video service for database operations on video metadata."""

import logging
from datetime import datetime, timezone

from src.channel.schemas import VideoMetadataDocument
from src.core.constants import (
    PERMANENT_AVAILABILITY,
)
from src.database.manager import MongoDBManager
from src.transcription.failures import (
    MAX_RETRIES_BEFORE_PERMANENT,
    RETRYABLE_FAILURE_CATEGORIES,
)

logger = logging.getLogger(__name__)


async def get_pending_videos(
    channel_id: str | None = None,
    db_manager: MongoDBManager | None = None,
    skip_permanent_failures: bool = True,
) -> list[VideoMetadataDocument]:
    """Get videos pending transcription.

    Args:
        channel_id: Optional channel ID to filter by.
        db_manager: Optional MongoDBManager instance to reuse.
        skip_permanent_failures: When True, exclude videos with permanent
            failure categories (members_only, private, geo_restricted, etc.)
            that were reset to pending.

    Returns:
        List of VideoMetadataDocument instances with non-completed status.
    """
    async with db_manager or MongoDBManager() as db:
        docs = await db.get_pending_transcription_videos(
            channel_id=channel_id,
            limit=1000,
            skip_permanent_failures=skip_permanent_failures,
        )
        return [VideoMetadataDocument(**doc) for doc in docs]


async def get_failed_videos(
    channel_id: str | None = None,
    db_manager: MongoDBManager | None = None,
    skip_permanent_failures: bool = False,
) -> list[VideoMetadataDocument]:
    """Get videos with failed transcription status.

    Args:
        channel_id: Optional channel ID to filter by.
        db_manager: Optional MongoDBManager instance to reuse.
        skip_permanent_failures: When True, exclude videos with permanent
            failure categories (members_only, private, geo_restricted, etc.)

    Returns:
        List of VideoMetadataDocument instances with failed status.
    """
    async with db_manager or MongoDBManager() as db:
        docs = await db.get_failed_transcription_videos(
            channel_id=channel_id,
            limit=1000,
            skip_permanent_failures=skip_permanent_failures,
        )
        return [VideoMetadataDocument(**doc) for doc in docs]


async def get_restricted_videos(
    channel_id: str | None = None,
    availability: str | None = None,
    db_manager: MongoDBManager | None = None,
) -> list[dict]:
    """Get videos with permanent access restrictions.

    Args:
        channel_id: Optional channel ID to filter by.
        availability: Optional specific availability type to filter by.
        db_manager: Optional MongoDBManager instance to reuse.

    Returns:
        List of video metadata dicts with permanent restrictions.
    """
    async with db_manager or MongoDBManager() as db:
        return await db.get_restricted_videos(
            channel_id=channel_id,
            availability=availability,
        )


async def reset_failed_transcription(
    video_id: str, db_manager: MongoDBManager | None = None
) -> bool:
    """Reset failed transcription status to pending for retry.

    Args:
        video_id: The video ID to reset.
        db_manager: Optional MongoDBManager instance to reuse.

    Returns:
        True if the document was updated, False otherwise.
    """
    async with db_manager or MongoDBManager() as db:
        result = await db.video_metadata.update_one(
            {"video_id": video_id},
            {
                "$set": {
                    "transcript_status": "pending",
                    "transcript_error": None,
                    "transcript_error_category": None,
                    "transcript_failure_count": 0,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        return result.modified_count > 0


async def requeue_retryable_failed(
    channel_id: str | None = None,
    db_manager: MongoDBManager | None = None,
) -> int:
    """Requeue failed videos with retryable categories that haven't

    exceeded the escalation threshold.

    Sets transcript_status to "pending" and clears transcript_error /
    transcript_error_category, but does NOT reset transcript_failure_count
    (automatic requeues preserve the count for escalation).

    Args:
        channel_id: Optional channel ID to filter by.
        db_manager: Optional MongoDBManager instance to reuse.

    Returns:
        Number of videos requeued.
    """
    query: dict = {
        "transcript_status": "failed",
        "transcript_error_category": {"$in": list(RETRYABLE_FAILURE_CATEGORIES)},
        "transcript_failure_count": {"$lt": MAX_RETRIES_BEFORE_PERMANENT},
    }
    if channel_id:
        query["channel_id"] = channel_id

    async with db_manager or MongoDBManager() as db:
        query["availability"] = {"$nin": list(PERMANENT_AVAILABILITY)}

        result = await db.video_metadata.update_many(
            query,
            {
                "$set": {
                    "transcript_status": "pending",
                    "transcript_error": None,
                    "transcript_error_category": None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        requeued = result.modified_count
        if requeued > 0:
            logger.info("Requeued %d retryable-failed video(s) for automatic retry", requeued)
        return requeued


async def mark_video_transcribed(
    video_id: str, transcript_id: str, db_manager: MongoDBManager | None = None
) -> bool:
    """Mark video as transcribed.

    Args:
        video_id: The video ID to mark.
        transcript_id: The transcript document ID.
        db_manager: Optional MongoDBManager instance to reuse.

    Returns:
        True if the document was updated, False otherwise.
    """
    async with db_manager or MongoDBManager() as db:
        return await db.mark_transcript_completed(video_id, transcript_id)


async def mark_video_transcription_failed(
    video_id: str,
    error_message: str,
    error_category: str,
    current_failure_count: int | None = None,
    db_manager: MongoDBManager | None = None,
) -> bool:
    """Mark a video transcription attempt as failed.

    Args:
        video_id: Video identifier.
        error_message: Error message to persist.
        error_category: Structured failure category.
        current_failure_count: Optional current failure count for escalation logic.
        db_manager: Optional MongoDBManager instance to reuse.

    Returns:
        True when a matching video document was found.
    """
    async with db_manager or MongoDBManager() as db:
        return await db.mark_transcript_failed(
            video_id,
            error_message,
            error_category,
            current_failure_count=current_failure_count,
        )
