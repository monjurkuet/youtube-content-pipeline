"""Video service for database operations on video metadata."""

import logging
from datetime import datetime, timezone
from typing import Any

from src.database.manager import MongoDBManager
from src.channel.schemas import VideoMetadataDocument

logger = logging.getLogger(__name__)


async def get_pending_videos(
    channel_id: str | None = None, db_manager: MongoDBManager | None = None
) -> list[VideoMetadataDocument]:
    """Get videos pending transcription."""
    from src.database.manager import MongoDBManager

    async def _fetch():
        async with (db_manager or MongoDBManager()) as db:
            query = {"transcript_status": {"$ne": "completed"}}
            if channel_id:
                query["channel_id"] = channel_id

            cursor = db.video_metadata.find(query)
            docs = await cursor.to_list(length=None)
            return [VideoMetadataDocument(**doc) for doc in docs]

    import asyncio

    try:
        loop = asyncio.get_running_loop()
        return await _fetch()
    except RuntimeError:
        return asyncio.run(_fetch())


async def get_failed_videos(
    channel_id: str | None = None, db_manager: MongoDBManager | None = None
) -> list[VideoMetadataDocument]:
    """Get videos with failed transcription status."""
    from src.database.manager import MongoDBManager

    async def _fetch():
        async with (db_manager or MongoDBManager()) as db:
            query = {"transcript_status": "failed"}
            if channel_id:
                query["channel_id"] = channel_id

            cursor = db.video_metadata.find(query)
            docs = await cursor.to_list(length=None)
            return [VideoMetadataDocument(**doc) for doc in docs]

    import asyncio

    try:
        loop = asyncio.get_running_loop()
        return await _fetch()
    except RuntimeError:
        return asyncio.run(_fetch())


async def reset_failed_transcription(
    video_id: str, db_manager: MongoDBManager | None = None
) -> bool:
    """Reset failed transcription status to pending for retry."""
    from src.database.manager import MongoDBManager

    async def _reset():
        async with (db_manager or MongoDBManager()) as db:
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

    import asyncio

    try:
        loop = asyncio.get_running_loop()
        return await _reset()
    except RuntimeError:
        return asyncio.run(_reset())


async def mark_video_transcribed(
    video_id: str, transcript_id: str, db_manager: MongoDBManager | None = None
) -> bool:
    """Mark video as transcribed."""
    from src.database.manager import MongoDBManager

    async def _mark():
        async with (db_manager or MongoDBManager()) as db:
            return await db.mark_transcript_completed(video_id, transcript_id)

    import asyncio

    try:
        loop = asyncio.get_running_loop()
        return await _mark()
    except RuntimeError:
        return asyncio.run(_mark())
