"""Tests for video service helpers."""

from unittest.mock import AsyncMock

import pytest

from src.services.video_service import get_pending_videos


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
    )
    assert len(videos) == 1
    assert videos[0].video_id == "abc123def45"
    assert videos[0].transcript_status == "pending"
