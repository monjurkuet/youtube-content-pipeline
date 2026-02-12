"""MongoDB storage for video analysis results using new LLM-driven schemas."""

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from src.core.config import get_settings
from src.core.schemas import VideoAnalysisResult, TranscriptDocument


class MongoDBManager:
    """Manage MongoDB operations for LLM-driven video analysis."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = AsyncIOMotorClient(self.settings.mongodb_url)
        self.db = self.client[self.settings.mongodb_database]
        self.analyses = self.db.video_analyses
        self.transcripts = self.db.transcripts

    async def init_indexes(self) -> None:
        """Initialize database indexes."""
        await self.analyses.create_index("video_id", unique=True)
        await self.analyses.create_index("analyzed_at")
        await self.analyses.create_index("source_type")
        await self.analyses.create_index("content_type")
        await self.analyses.create_index("primary_asset")
        # Also init transcript indexes
        await self.init_transcript_indexes()

    async def init_transcript_indexes(self) -> None:
        """Initialize transcript collection indexes."""
        await self.transcripts.create_index("video_id", unique=True)
        await self.transcripts.create_index("created_at")
        await self.transcripts.create_index("transcript_source")
        await self.transcripts.create_index("language")

    async def save_analysis(self, result: VideoAnalysisResult) -> str:
        """Save video analysis to MongoDB.

        Args:
            result: VideoAnalysisResult to save

        Returns:
            Document ID as string
        """
        # Convert to dict using the model's method for MongoDB compatibility
        doc = result.model_dump_for_mongo()
        doc["updated_at"] = datetime.utcnow().isoformat()

        result_op = await self.analyses.replace_one({"video_id": result.video_id}, doc, upsert=True)

        if result_op.upserted_id:
            return str(result_op.upserted_id)

        saved_doc = await self.analyses.find_one({"video_id": result.video_id})
        if saved_doc is None:
            raise RuntimeError("Failed to save analysis to database")
        return str(saved_doc["_id"])

    async def get_analysis(self, video_id: str) -> dict[str, Any] | None:
        """Retrieve video analysis from MongoDB.

        Args:
            video_id: Video identifier

        Returns:
            Analysis document as dict, or None if not found
        """
        doc = await self.analyses.find_one({"video_id": video_id})
        if doc and "_id" in doc:
            # Convert ObjectId to string for JSON serialization
            doc["_id"] = str(doc["_id"])
        return doc

    async def list_analyses(
        self,
        limit: int = 100,
        offset: int = 0,
        content_type: str | None = None,
        primary_asset: str | None = None,
    ) -> list[dict[str, Any]]:
        """List video analyses with optional filtering.

        Args:
            limit: Maximum results to return
            offset: Number of results to skip
            content_type: Filter by content type
            primary_asset: Filter by primary asset

        Returns:
            List of analysis documents
        """
        query: dict[str, Any] = {}
        if content_type:
            query["content_type"] = content_type
        if primary_asset:
            query["primary_asset"] = primary_asset

        cursor = self.analyses.find(query).sort("analyzed_at", -1).skip(offset).limit(limit)

        results = []
        async for doc in cursor:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            results.append(doc)

        return results

    async def delete_analysis(self, video_id: str) -> bool:
        """Delete video analysis from MongoDB.

        Args:
            video_id: Video identifier

        Returns:
            True if document was deleted, False otherwise
        """
        result = await self.analyses.delete_one({"video_id": video_id})
        return result.deleted_count > 0

    async def get_analysis_count(
        self,
        content_type: str | None = None,
        primary_asset: str | None = None,
    ) -> int:
        """Get count of analyses with optional filtering.

        Args:
            content_type: Filter by content type
            primary_asset: Filter by primary asset

        Returns:
            Count of matching documents
        """
        query: dict[str, Any] = {}
        if content_type:
            query["content_type"] = content_type
        if primary_asset:
            query["primary_asset"] = primary_asset

        return await self.analyses.count_documents(query)

    async def close(self) -> None:
        """Close MongoDB connection."""
        self.client.close()

    async def save_transcript(self, transcript_doc: "TranscriptDocument") -> str:
        """Save transcript to MongoDB.

        Args:
            transcript_doc: TranscriptDocument to save

        Returns:
            Document ID as string
        """
        from src.core.schemas import TranscriptDocument

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


# Singleton instance for application-wide use
_db_manager: MongoDBManager | None = None


def get_db_manager() -> MongoDBManager:
    """Get or create the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = MongoDBManager()
    return _db_manager
