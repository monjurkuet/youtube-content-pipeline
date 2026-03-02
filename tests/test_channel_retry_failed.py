"""Tests for the new retry failed transcriptions functionality."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.channel.sync import get_failed_videos, reset_failed_transcription
from src.database.manager import MongoDBManager
from src.channel import get_failed_videos as channel_get_failed_videos


class TestRetryFailedTranscriptions:
    """Test the retry failed transcriptions functionality."""

    async def test_get_failed_transcription_videos(self):
        """Test the get_failed_transcription_videos database method."""
        async with MongoDBManager() as db:
            # Mock the database find method to return test data
            original_find = db.video_metadata.find
            db.video_metadata.find = AsyncMock()

            mock_cursor = AsyncMock()
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

            # Mock the async iterator
            mock_cursor.__aiter__ = MagicMock(return_value=iter(mock_docs))

            db.video_metadata.find.return_value = mock_cursor

            # Call the method
            result = await db.get_failed_transcription_videos(limit=10)

            # Verify the query was constructed correctly
            db.video_metadata.find.assert_called_once()
            # Check that the query includes the failed status filter
            call_args = db.video_metadata.find.call_args[0][0]
            assert call_args["transcript_status"] == "failed"

            # Check that the result is properly formatted
            assert len(result) == 1
            assert result[0]["video_id"] == "test_video_1"
            assert result[0]["transcript_status"] == "failed"

    def test_get_failed_videos_function(self):
        """Test the get_failed_videos channel sync function."""
        with patch('src.channel.sync.asyncio.run') as mock_run:
            # Mock the async function that gets called
            mock_result = [
                {
                    "video_id": "test_video_1",
                    "channel_id": "test_channel_1",
                    "title": "Test Video 1",
                    "transcript_status": "failed",
                    "published_at": "2023-01-01T00:00:00",
                    "synced_at": "2023-01-01T00:00:00"
                }
            ]
            mock_run.return_value = mock_result

            # Call the function
            result = get_failed_videos()

            # Verify it returns VideoMetadataDocument objects
            assert len(result) == 1
            assert result[0].video_id == "test_video_1"
            assert result[0].transcript_status == "failed"

    def test_reset_failed_transcription(self):
        """Test the reset_failed_transcription function."""
        with patch('src.channel.sync.asyncio.run') as mock_run:
            # Mock the update operation result
            mock_update_result = MagicMock()
            mock_update_result.modified_count = 1
            mock_run.return_value = True  # Simulate successful update

            # Call the function
            result = reset_failed_transcription("test_video_123")

            # Verify it returns True for success
            assert result is True

            # Verify that the async function was called
            mock_run.assert_called_once()


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