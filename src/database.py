"""MongoDB storage for transcription pipeline."""

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from src.core.config import get_settings
from src.core.schemas import TranscriptDocument


class MongoDBManager:
    """Manage MongoDB operations for transcription pipeline."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = AsyncIOMotorClient(self.settings.mongodb_url)
        self.db = self.client[self.settings.mongodb_database]
        self.transcripts = self.db.transcripts
        self.channels = self.db.channels
        self.video_metadata = self.db.video_metadata

    async def init_indexes(self) -> None:
        """Initialize database indexes."""
        # Transcripts collection
        await self.transcripts.create_index("video_id", unique=True)
        await self.transcripts.create_index("created_at")
        await self.transcripts.create_index("transcript_source")
        await self.transcripts.create_index("language")

        # Channels collection
        await self.channels.create_index("channel_id", unique=True)
        await self.channels.create_index("channel_handle")
        await self.channels.create_index("tracked_since")

        # Video metadata collection
        await self.video_metadata.create_index("video_id", unique=True)
        await self.video_metadata.create_index("channel_id")
        await self.video_metadata.create_index("transcript_status")
        await self.video_metadata.create_index("published_at")

    async def save_transcript(self, transcript_doc: TranscriptDocument) -> str:
        """Save transcript to MongoDB.

        Args:
            transcript_doc: TranscriptDocument to save

        Returns:
            Document ID as string
        """
        doc = transcript_doc.model_dump_for_mongo()
        doc["updated_at"] = datetime.utcnow().isoformat()

        result_op = await self.transcripts.replace_one(
            {"video_id": transcript_doc.video_id}, doc, upsert=True
        )

        if result_op.upserted_id:
            return str(result_op.upserted_id)

        saved_doc = await self.transcripts.find_one({"video_id": transcript_doc.video_id})
        if saved_doc is None:
            raise RuntimeError("Failed to save transcript to database")
        return str(saved_doc["_id"])

    async def get_transcript(self, video_id: str) -> dict[str, Any] | None:
        """Retrieve transcript from MongoDB.

        Args:
            video_id: Video identifier

        Returns:
            Transcript document as dict, or None if not found
        """
        doc = await self.transcripts.find_one({"video_id": video_id})
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def list_transcripts(
        self,
        limit: int = 100,
        offset: int = 0,
        transcript_source: str | None = None,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        """List transcripts with optional filtering.

        Args:
            limit: Maximum results to return
            offset: Number of results to skip
            transcript_source: Filter by transcript source
            language: Filter by language

        Returns:
            List of transcript documents
        """
        query: dict[str, Any] = {}
        if transcript_source:
            query["transcript_source"] = transcript_source
        if language:
            query["language"] = language

        cursor = self.transcripts.find(query).sort("created_at", -1).skip(offset).limit(limit)

        results = []
        async for doc in cursor:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            results.append(doc)

        return results

    async def delete_transcript(self, video_id: str) -> bool:
        """Delete transcript from MongoDB.

        Args:
            video_id: Video identifier

        Returns:
            True if document was deleted, False otherwise
        """
        result = await self.transcripts.delete_one({"video_id": video_id})
        return result.deleted_count > 0

    async def get_transcript_count(
        self,
        transcript_source: str | None = None,
        language: str | None = None,
    ) -> int:
        """Get count of transcripts with optional filtering.

        Args:
            transcript_source: Filter by transcript source
            language: Filter by language

        Returns:
            Count of matching documents
        """
        query: dict[str, Any] = {}
        if transcript_source:
            query["transcript_source"] = transcript_source
        if language:
            query["language"] = language

        return await self.transcripts.count_documents(query)

    # Channel operations

    async def save_channel(self, channel_doc: Any) -> str:
        """Save channel to MongoDB.

        Args:
            channel_doc: ChannelDocument to save

        Returns:
            Document ID as string
        """
        doc = channel_doc.model_dump_for_mongo()
        doc["updated_at"] = datetime.utcnow().isoformat()

        result_op = await self.channels.replace_one(
            {"channel_id": channel_doc.channel_id}, doc, upsert=True
        )

        if result_op.upserted_id:
            return str(result_op.upserted_id)

        saved_doc = await self.channels.find_one({"channel_id": channel_doc.channel_id})
        if saved_doc is None:
            raise RuntimeError("Failed to save channel to database")
        return str(saved_doc["_id"])

    async def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        """Retrieve channel from MongoDB.

        Args:
            channel_id: Channel identifier

        Returns:
            Channel document as dict, or None if not found
        """
        doc = await self.channels.find_one({"channel_id": channel_id})
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def list_channels(self, limit: int = 100) -> list[dict[str, Any]]:
        """List all tracked channels.

        Args:
            limit: Maximum results to return

        Returns:
            List of channel documents
        """
        cursor = self.channels.find({}).sort("tracked_since", -1).limit(limit)

        results = []
        async for doc in cursor:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            results.append(doc)

        return results

    async def delete_channel(self, channel_id: str) -> bool:
        """Delete channel from MongoDB.

        Args:
            channel_id: Channel identifier

        Returns:
            True if document was deleted, False otherwise
        """
        result = await self.channels.delete_one({"channel_id": channel_id})
        return result.deleted_count > 0

    # Video metadata operations

    async def save_video_metadata(self, video_doc: Any) -> dict[str, Any]:
        """Save video metadata to MongoDB.

        Args:
            video_doc: VideoMetadataDocument to save

        Returns:
            Dict with 'new' boolean and 'id' string
        """
        doc = video_doc.model_dump_for_mongo()

        result_op = await self.video_metadata.replace_one(
            {"video_id": video_doc.video_id}, doc, upsert=True
        )

        saved_doc = await self.video_metadata.find_one({"video_id": video_doc.video_id})
        if saved_doc is None:
            raise RuntimeError("Failed to save video metadata to database")

        return {
            "new": result_op.upserted_id is not None,
            "id": str(saved_doc["_id"]),
        }

    async def get_video_metadata(self, video_id: str) -> dict[str, Any] | None:
        """Retrieve video metadata from MongoDB.

        Args:
            video_id: Video identifier

        Returns:
            Video metadata document as dict, or None if not found
        """
        doc = await self.video_metadata.find_one({"video_id": video_id})
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def list_videos_by_channel(
        self,
        channel_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List videos for a specific channel.

        Args:
            channel_id: Channel identifier
            limit: Maximum results to return
            offset: Number of results to skip

        Returns:
            List of video metadata documents
        """
        cursor = (
            self.video_metadata.find({"channel_id": channel_id})
            .sort("published_at", -1)
            .skip(offset)
            .limit(limit)
        )

        results = []
        async for doc in cursor:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            results.append(doc)

        return results

    async def get_pending_transcription_videos(
        self,
        channel_id: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Get videos pending transcription.

        Args:
            channel_id: Optional channel ID filter
            limit: Maximum results to return

        Returns:
            List of video metadata documents with pending status
        """
        query = {"transcript_status": "pending"}
        if channel_id:
            query["channel_id"] = channel_id

        cursor = self.video_metadata.find(query).sort("published_at", -1).limit(limit)

        results = []
        async for doc in cursor:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            results.append(doc)

        return results

    async def mark_transcript_completed(
        self,
        video_id: str,
        transcript_id: str,
    ) -> bool:
        """Mark video as transcribed.

        Args:
            video_id: Video identifier
            transcript_id: Transcript document ID

        Returns:
            True if successful
        """
        result = await self.video_metadata.update_one(
            {"video_id": video_id},
            {
                "$set": {
                    "transcript_status": "completed",
                    "transcript_id": transcript_id,
                }
            },
        )
        return result.modified_count > 0

    async def mark_transcript_failed(
        self,
        video_id: str,
        error_message: str | None = None,
    ) -> bool:
        """Mark video transcription as failed.

        Args:
            video_id: Video identifier
            error_message: Optional error message

        Returns:
            True if successful
        """
        update = {"$set": {"transcript_status": "failed"}}
        if error_message:
            update["$set"]["transcript_error"] = error_message

        result = await self.video_metadata.update_one(
            {"video_id": video_id},
            update,
        )
        return result.modified_count > 0

    async def get_video_count(
        self,
        channel_id: str | None = None,
        transcript_status: str | None = None,
    ) -> int:
        """Get count of videos with optional filtering.

        Args:
            channel_id: Filter by channel ID
            transcript_status: Filter by transcript status

        Returns:
            Count of matching documents
        """
        query: dict[str, Any] = {}
        if channel_id:
            query["channel_id"] = channel_id
        if transcript_status:
            query["transcript_status"] = transcript_status

        return await self.video_metadata.count_documents(query)

    async def close(self) -> None:
        """Close MongoDB connection."""
        self.client.close()


# Singleton instance for application-wide use
_db_manager: MongoDBManager | None = None


def get_db_manager() -> MongoDBManager:
    """Get or create the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = MongoDBManager()
    return _db_manager
