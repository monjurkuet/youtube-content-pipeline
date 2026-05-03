"""Tests for video service helpers."""

from unittest.mock import AsyncMock

import pytest

from src.services.video_service import get_pending_videos, get_failed_videos


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
