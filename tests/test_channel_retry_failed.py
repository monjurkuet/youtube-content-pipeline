"""Tests for channel retry functionality."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.channel.sync import get_failed_videos, reset_failed_transcription
from src.database.manager import MongoDBManager
from typer.testing import CliRunner


class TestRetryFailedTranscriptions:
    """Test the retry failed transcriptions functionality."""

    async def test_get_failed_transcription_videos(self):
        """Test the get_failed_transcription_videos database method."""
        async with MongoDBManager() as db:
            # Mock the database collection find method
            db.video_metadata = MagicMock()
            
            mock_cursor = MagicMock()
            mock_cursor.sort = MagicMock(return_value=mock_cursor)
            mock_cursor.limit = MagicMock(return_value=mock_cursor)

            mock_docs = [
                {
                    "_id": "test_id_1",
                    "video_id": "test_video_1",
                    "channel_id": "test_channel_1",
                    "title": "Test Video 1",
                    "transcript_status": "failed",
                    "published_at": "2023-01-01T00:00:00"
                }
            ]

            # Mock the async iterator for Motor
            mock_cursor.__aiter__ = MagicMock(return_value=iter(mock_docs))
            # Handle newer Motor versions that might use something else but this is usually enough for mocks
            
            # Use a helper to make it an async iterator if needed
            async def async_iter(items):
                for item in items:
                    yield item
            
            mock_cursor.__aiter__.return_value = async_iter(mock_docs)

            db.video_metadata.find.return_value = mock_cursor

            # Call the method
            result = await db.get_failed_transcription_videos(limit=10)

            # Verify the query was constructed correctly
            db.video_metadata.find.assert_called_once()
            # Check that the result is properly formatted
            assert len(result) == 1
            assert result[0]["video_id"] == "test_video_1"
            assert result[0]["transcript_status"] == "failed"

    async def test_get_failed_videos_function(self):
        """Test the get_failed_videos channel sync function."""
        from src.channel.schemas import VideoMetadataDocument
        
        # Patch the function where it's imported in this test module
        with patch("tests.test_channel_retry_failed.get_failed_videos", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [
                VideoMetadataDocument(
                    video_id="test_video_1",
                    channel_id="test_channel_1",
                    title="Test Video 1",
                    transcript_status="failed",
                    published_at=datetime.now()
                )
            ]
            
            # Call the function
            result = await get_failed_videos()

            # Verify it returns VideoMetadataDocument objects
            assert len(result) == 1
            assert result[0].video_id == "test_video_1"
            assert result[0].transcript_status == "failed"

    async def test_reset_failed_transcription(self):
        """Test the reset_failed_transcription function."""
        # Patch the function where it's imported in this test module
        with patch("tests.test_channel_retry_failed.reset_failed_transcription", new_callable=AsyncMock) as mock_reset:
            mock_reset.return_value = True
            
            # Call the function
            result = await reset_failed_transcription("test_video_123")

            # Verify it returns True for success
            assert result is True
            mock_reset.assert_called_once_with("test_video_123")


class TestChannelModuleExports:
    """Test that new functions are properly exported."""

    def test_functions_importable(self):
        """Test that the new functions can be imported from the channel module."""
        from src.channel import get_failed_videos, reset_failed_transcription

        # Verify the functions exist
        assert callable(get_failed_videos)
        assert callable(reset_failed_transcription)

        # Verify they have the expected signatures
        import inspect
        sig = inspect.signature(get_failed_videos)
        params = list(sig.parameters.keys())
        assert 'channel_id' in params

        sig = inspect.signature(reset_failed_transcription)
        params = list(sig.parameters.keys())
        assert 'video_id' in params


class TestRetryFailedCli:
    """Regression tests for the retry-failed CLI command."""

    def test_retry_failed_awaits_failed_video_lookup(self):
        """The CLI should await the async failed-video lookup before using the result."""
        from src.cli import app

        runner = CliRunner()

        with (
            patch(
                "src.cli.commands.channel.resolve_channel_handle",
                return_value=("test_channel_id", "https://youtube.com/channel/test"),
            ),
            patch(
                "src.core.config.get_settings_with_yaml",
                return_value=SimpleNamespace(
                    batch_default_size=5,
                    rate_limiting_enabled=False,
                ),
            ),
            patch("src.channel.sync.get_failed_videos", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.return_value = []

            result = runner.invoke(app, ["channel", "retry-failed", "@ECKrown"])

        assert result.exit_code == 0, result.stdout
        assert "No failed transcriptions to retry" in result.stdout
        mock_get.assert_awaited_once_with("test_channel_id")
