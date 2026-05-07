"""Tests for MongoDB manager — focused on failure-count and escalation semantics."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import get_settings
from src.database.manager import MongoDBManager


@pytest.mark.asyncio
async def test_initialize_uses_configured_mongo_timeouts() -> None:
    """MongoDB client should inherit explicit timeout settings from config."""
    with patch.dict(
        "os.environ",
        {
            "MONGODB_SERVER_SELECTION_TIMEOUT_MS": "1234",
            "MONGODB_CONNECT_TIMEOUT_MS": "2345",
            "MONGODB_SOCKET_TIMEOUT_MS": "3456",
        },
        clear=False,
    ):
        get_settings(force_reload=True)

    with patch("src.database.manager.AsyncIOMotorClient") as mock_client:
        manager = MongoDBManager()
        await manager.initialize()

        mock_client.assert_called_once_with(
            manager.settings.mongodb_url,
            serverSelectionTimeoutMS=1234,
            connectTimeoutMS=2345,
            socketTimeoutMS=3456,
        )


class TestMarkTranscriptFailed:
    """Test mark_transcript_failed failure-count and escalation logic."""

    @pytest.mark.asyncio
    async def test_accepts_current_failure_count_without_error(self) -> None:
        """Passing current_failure_count should not raise TypeError."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result

        manager = MongoDBManager()
        manager.video_metadata = mock_collection
        manager._initialized = True

        result = await manager.mark_transcript_failed(
            "video123",
            error_message="timeout",
            error_category="timeout",
            current_failure_count=0,
        )
        assert result is True
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$inc"]["transcript_failure_count"] == 1

    @pytest.mark.asyncio
    async def test_increments_failure_count_atomically(self) -> None:
        """The update should use $inc to atomically increment the failure count."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result

        manager = MongoDBManager()
        manager.video_metadata = mock_collection
        manager._initialized = True

        await manager.mark_transcript_failed(
            "video123",
            error_message="timeout",
            error_category="timeout",
            current_failure_count=1,
        )
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert "$inc" in update_doc
        assert update_doc["$inc"]["transcript_failure_count"] == 1

    @pytest.mark.asyncio
    async def test_escalates_timeout_at_threshold(self) -> None:
        """When current_failure_count+1 >= MAX_RETRIES_BEFORE_PERMANENT and
        the category is escalable, availability should be set to unavailable."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result

        manager = MongoDBManager()
        manager.video_metadata = mock_collection
        manager._initialized = True

        await manager.mark_transcript_failed(
            "video123",
            error_message="timeout again",
            error_category="timeout",
            current_failure_count=2,
        )
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$set"]["availability"] == "unavailable"

    @pytest.mark.asyncio
    async def test_no_escalation_before_threshold(self) -> None:
        """When current_failure_count+1 < MAX_RETRIES_BEFORE_PERMANENT,
        availability should NOT be set to unavailable for escalable categories."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result

        manager = MongoDBManager()
        manager.video_metadata = mock_collection
        manager._initialized = True

        await manager.mark_transcript_failed(
            "video123",
            error_message="timeout",
            error_category="timeout",
            current_failure_count=0,
        )
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert "availability" not in update_doc["$set"]

    @pytest.mark.asyncio
    async def test_no_escalation_without_current_failure_count(self) -> None:
        """When current_failure_count is omitted, escalation is skipped."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result

        manager = MongoDBManager()
        manager.video_metadata = mock_collection
        manager._initialized = True

        await manager.mark_transcript_failed(
            "video123",
            error_message="timeout",
            error_category="timeout",
        )
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert "availability" not in update_doc["$set"]

    @pytest.mark.asyncio
    async def test_permanent_category_sets_availability_immediately(self) -> None:
        """Permanent categories like 'private' should set availability regardless of count."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result

        manager = MongoDBManager()
        manager.video_metadata = mock_collection
        manager._initialized = True

        await manager.mark_transcript_failed(
            "video123",
            error_message="Video is private",
            error_category="private",
            current_failure_count=0,
        )
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$set"]["availability"] == "private"

    @pytest.mark.asyncio
    async def test_returns_matched_count_not_modified_count(self) -> None:
        """Return value should be based on matched_count for idempotent updates."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_result.modified_count = 0
        mock_collection.update_one.return_value = mock_result

        manager = MongoDBManager()
        manager.video_metadata = mock_collection
        manager._initialized = True

        result = await manager.mark_transcript_failed(
            "video123",
            error_message="already failed",
            error_category="timeout",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_escalates_temporary_block_at_threshold(self) -> None:
        """temporary_block should also escalate at the threshold."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result

        manager = MongoDBManager()
        manager.video_metadata = mock_collection
        manager._initialized = True

        await manager.mark_transcript_failed(
            "video123",
            error_message="blocked again",
            error_category="temporary_block",
            current_failure_count=2,
        )
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$set"]["availability"] == "unavailable"


class TestMarkTranscriptCompleted:
    """Test mark_transcript_completed resets failure count."""

    @pytest.mark.asyncio
    async def test_resets_failure_count_on_success(self) -> None:
        """Completion should reset transcript_failure_count to 0."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result

        manager = MongoDBManager()
        manager.video_metadata = mock_collection
        manager._initialized = True

        await manager.mark_transcript_completed("video123", "transcript-abc")
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]
        assert update_doc["$set"]["transcript_failure_count"] == 0
