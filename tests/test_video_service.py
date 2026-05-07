"""Tests for video service helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.video_service import (
    get_pending_videos,
    get_failed_videos,
    requeue_retryable_failed,
    reset_failed_transcription,
)


@pytest.mark.asyncio
async def test_get_pending_videos_uses_pending_query_only() -> None:
    """Pending helper should delegate to the pending-only database query."""
    db = AsyncMock()
    db.get_pending_transcription_videos = AsyncMock(
        return_value=[
            {
                "video_id": "abc123def45",
                "channel_id": "UC123",
                "title": "Newest pending video",
                "transcript_status": "pending",
            }
        ]
    )
    db_manager = AsyncMock()
    db_manager.__aenter__.return_value = db
    db_manager.__aexit__.return_value = None

    videos = await get_pending_videos(channel_id="UC123", db_manager=db_manager)

    db.get_pending_transcription_videos.assert_awaited_once_with(
        channel_id="UC123",
        limit=1000,
        skip_permanent_failures=True,
    )
    assert len(videos) == 1
    assert videos[0].video_id == "abc123def45"
    assert videos[0].transcript_status == "pending"


@pytest.mark.asyncio
async def test_get_pending_videos_includes_restricted() -> None:
    """When skip_permanent_failures=False, restricted videos are included."""
    db = AsyncMock()
    db.get_pending_transcription_videos = AsyncMock(return_value=[])
    db_manager = AsyncMock()
    db_manager.__aenter__.return_value = db
    db_manager.__aexit__.return_value = None

    await get_pending_videos(
        channel_id="UC123", db_manager=db_manager, skip_permanent_failures=False
    )

    db.get_pending_transcription_videos.assert_awaited_once_with(
        channel_id="UC123",
        limit=1000,
        skip_permanent_failures=False,
    )


@pytest.mark.asyncio
async def test_get_failed_videos_skips_permanent() -> None:
    """Failed videos should skip permanent failures by default."""
    db = AsyncMock()
    db.get_failed_transcription_videos = AsyncMock(return_value=[])
    db_manager = AsyncMock()
    db_manager.__aenter__.return_value = db
    db_manager.__aexit__.return_value = None

    await get_failed_videos(channel_id="UC123", db_manager=db_manager, skip_permanent_failures=True)

    db.get_failed_transcription_videos.assert_awaited_once_with(
        channel_id="UC123",
        limit=1000,
        skip_permanent_failures=True,
    )


class TestResetFailedTranscription:
    """Test reset_failed_transcription clears all failure state."""

    @pytest.mark.asyncio
    async def test_resets_error_category_and_failure_count(self) -> None:
        """Manual reset should clear error, error_category, and failure_count."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_collection.update_one.return_value = mock_result

        db = AsyncMock()
        db.video_metadata = mock_collection
        db_manager = AsyncMock()
        db_manager.__aenter__.return_value = db
        db_manager.__aexit__.return_value = None

        result = await reset_failed_transcription("video123", db_manager=db_manager)
        assert result is True

        call_args = mock_collection.update_one.call_args
        set_fields = call_args[0][1]["$set"]
        assert set_fields["transcript_status"] == "pending"
        assert set_fields["transcript_error"] is None
        assert set_fields["transcript_error_category"] is None
        assert set_fields["transcript_failure_count"] == 0


class TestRequeueRetryableFailed:
    """Test requeue_retryable_failed preserves failure count."""

    @pytest.mark.asyncio
    async def test_requeues_without_resetting_failure_count(self) -> None:
        """Automatic requeue should NOT reset transcript_failure_count."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.modified_count = 3
        mock_collection.update_many.return_value = mock_result

        db = AsyncMock()
        db.video_metadata = mock_collection
        db_manager = AsyncMock()
        db_manager.__aenter__.return_value = db
        db_manager.__aexit__.return_value = None

        count = await requeue_retryable_failed(channel_id="UC123", db_manager=db_manager)
        assert count == 3

        call_args = mock_collection.update_many.call_args
        query = call_args[0][0]
        set_fields = call_args[0][1]["$set"]

        assert query["transcript_status"] == "failed"
        assert query["channel_id"] == "UC123"
        assert set_fields["transcript_status"] == "pending"
        assert set_fields["transcript_error_category"] is None
        assert "transcript_failure_count" not in set_fields

    @pytest.mark.asyncio
    async def test_requeue_filters_by_escalation_threshold(self) -> None:
        """Requeue should only include videos below the escalation threshold."""
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.modified_count = 0
        mock_collection.update_many.return_value = mock_result

        db = AsyncMock()
        db.video_metadata = mock_collection
        db_manager = AsyncMock()
        db_manager.__aenter__.return_value = db
        db_manager.__aexit__.return_value = None

        await requeue_retryable_failed(channel_id=None, db_manager=db_manager)

        call_args = mock_collection.update_many.call_args
        query = call_args[0][0]
        assert "transcript_failure_count" in query
        assert query["transcript_failure_count"]["$lt"] == 3
