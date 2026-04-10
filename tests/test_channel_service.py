"""Tests for channel service batch behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.channel.resolver import VideoChannelResolution
from src.services.channel_service import add_channels_from_videos_service


@pytest.mark.asyncio
async def test_add_channels_from_videos_reports_structured_resolution_failure() -> None:
    """A failed resolution should be recorded with stage information."""
    db_manager = AsyncMock()
    db_manager.get_channel = AsyncMock(return_value=None)

    with patch("src.services.channel_service.extract_video_id", return_value="dQw4w9WgXcQ"), patch(
        "src.services.channel_service.resolve_channel_from_video",
        return_value=VideoChannelResolution(
            success=False,
            source="watch_page",
            error_stage="watch_page_parse",
            error_message="Could not locate a channel ID on the watch page",
            retryable=True,
        ),
    ):
        result = await add_channels_from_videos_service(["https://www.youtube.com/watch?v=dQw4w9WgXcQ"], db_manager)

    assert result["total_failed"] == 1
    assert result["failed"][0]["error_stage"] == "watch_page_parse"
    assert result["failed"][0]["resolution_source"] == "watch_page"
    assert result["failed"][0]["retryable"] is True


@pytest.mark.asyncio
async def test_add_channels_from_videos_keeps_success_when_auto_sync_fails() -> None:
    """Channel creation should still succeed when auto-sync fails."""
    db_manager = AsyncMock()
    db_manager.get_channel = AsyncMock(return_value=None)
    db_manager.save_channel = AsyncMock(return_value="507f1f77bcf86cd799439011")

    with patch("src.services.channel_service.extract_video_id", return_value="dQw4w9WgXcQ"), patch(
        "src.services.channel_service.resolve_channel_from_video",
        return_value=VideoChannelResolution(
            success=True,
            channel_id="UC1234567890123456789012",
            channel_handle="TestChannel",
            channel_title="Test Channel",
            source="watch_page",
        ),
    ), patch("src.services.channel_service.resolve_channel_handle", side_effect=ValueError("boom")), patch(
        "src.services.channel_service.sync_channel_async",
        side_effect=RuntimeError("sync failed"),
    ):
        result = await add_channels_from_videos_service(["https://www.youtube.com/watch?v=dQw4w9WgXcQ"], db_manager)

    assert result["total_added"] == 1
    assert result["added"][0]["resolution_source"] == "watch_page"
    assert result["added"][0]["sync_error"] == "sync failed"


@pytest.mark.asyncio
async def test_add_channels_from_videos_deduplicates_batch_entries() -> None:
    """The same channel in a batch should only be processed once."""
    db_manager = AsyncMock()
    db_manager.get_channel = AsyncMock(return_value=None)
    db_manager.save_channel = AsyncMock(return_value="507f1f77bcf86cd799439011")

    with patch("src.services.channel_service.extract_video_id", return_value="dQw4w9WgXcQ"), patch(
        "src.services.channel_service.resolve_channel_from_video",
        return_value=VideoChannelResolution(
            success=True,
            channel_id="UC1234567890123456789012",
            channel_handle="TestChannel",
            channel_title="Test Channel",
            source="watch_page",
        ),
    ), patch("src.services.channel_service.resolve_channel_handle", return_value=("UC1234567890123456789012", "https://www.youtube.com/channel/UC1234567890123456789012")):
        result = await add_channels_from_videos_service(
            [
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            ],
            db_manager,
            auto_sync=False,
        )

    assert result["total_processed"] == 2
    assert result["total_added"] == 1
    assert result["total_skipped"] == 1
    assert result["skipped_duplicate"]
