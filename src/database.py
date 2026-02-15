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

    async def init_indexes(self) -> None:
        """Initialize database indexes."""
        await self.transcripts.create_index("video_id", unique=True)
        await self.transcripts.create_index("created_at")
        await self.transcripts.create_index("transcript_source")
        await self.transcripts.create_index("language")

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
