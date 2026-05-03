"""Video service for database operations on video metadata."""

import logging
from datetime import datetime, timezone

from src.channel.schemas import VideoMetadataDocument
from src.database.manager import MongoDBManager

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
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        return result.modified_count > 0


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
