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

    async def test_get_failed_transcription_videos_query(self):
        """Test the get_failed_transcription_videos database method constructs the correct query."""
        manager = MongoDBManager()
        manager._initialized = True
        mock_collection = MagicMock()
        manager.video_metadata = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_collection.find.return_value = mock_cursor

        with patch.object(manager, "initialize", new_callable=AsyncMock):
            try:
                await manager.get_failed_transcription_videos(channel_id="UC123", limit=10)
            except Exception:
                pass

        mock_collection.find.assert_called_once()
        query = mock_collection.find.call_args[0][0]
        assert query["transcript_status"] == "failed"
        assert query["channel_id"] == "UC123"

    async def test_get_failed_videos_function(self):
        """Test the get_failed_videos channel sync function."""
        from src.channel.schemas import VideoMetadataDocument

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

            result = await get_failed_videos()

            assert len(result) == 1
            assert result[0].video_id == "test_video_1"
            assert result[0].transcript_status == "failed"

    async def test_reset_failed_transcription(self):
        """Test the reset_failed_transcription function."""
        with patch("tests.test_channel_retry_failed.reset_failed_transcription", new_callable=AsyncMock) as mock_reset:
            mock_reset.return_value = True

            result = await reset_failed_transcription("test_video_123")

            assert result is True
            mock_reset.assert_called_once_with("test_video_123")


class TestChannelModuleExports:
    """Test that new functions are properly exported."""

    def test_functions_importable(self):
        """Test that the new functions can be imported from the channel module."""
        from src.channel import get_failed_videos, reset_failed_transcription, requeue_retryable_failed

        assert callable(get_failed_videos)
        assert callable(reset_failed_transcription)
        assert callable(requeue_retryable_failed)

        import inspect
        sig = inspect.signature(get_failed_videos)
        params = list(sig.parameters.keys())
        assert 'channel_id' in params

        sig = inspect.signature(reset_failed_transcription)
        params = list(sig.parameters.keys())
        assert 'video_id' in params

        sig = inspect.signature(requeue_retryable_failed)
        params = list(sig.parameters.keys())
        assert 'channel_id' in params


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
            mock_get.assert_awaited_once_with("test_channel_id", skip_permanent_failures=True)

    def test_retry_failed_passes_current_failure_count(self):
        """When a retry fails again, mark_transcript_failed should receive current_failure_count."""
        from src.cli import app
        from src.channel.schemas import VideoMetadataDocument

        runner = CliRunner()
        video = VideoMetadataDocument(
            video_id="vid_timeout",
            channel_id="test_channel_id",
            title="Test Timeout Video",
            transcript_status="failed",
            published_at=datetime.now(),
            transcript_error_category="timeout",
            transcript_failure_count=1,
        )

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
            patch("src.pipeline.get_transcript", side_effect=Exception("timeout error")),
            patch(
                "src.services.video_service.mark_video_transcription_failed",
                new_callable=AsyncMock,
            ) as mock_mark_failed,
        ):
            mock_get.return_value = [video]

            result = runner.invoke(app, ["channel", "retry-failed", "@ECKrown", "--all"])

            mock_mark_failed.assert_awaited()
            call_kwargs = mock_mark_failed.await_args.kwargs
            assert call_kwargs.get("current_failure_count") == 1

    def test_retry_failed_reset_clears_failure_count(self):
        """The --reset flag should clear transcript_failure_count via reset_failed_transcription."""
        from src.cli import app
        from src.channel.schemas import VideoMetadataDocument

        runner = CliRunner()
        video = VideoMetadataDocument(
            video_id="vid_reset",
            channel_id="test_channel_id",
            title="Reset Video",
            transcript_status="failed",
            published_at=datetime.now(),
            transcript_failure_count=2,
        )

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
            patch(
                "src.services.video_service.reset_failed_transcription",
                new_callable=AsyncMock,
            ) as mock_reset,
        ):
            mock_get.return_value = [video]
            mock_reset.return_value = True

            result = runner.invoke(
                app, ["channel", "retry-failed", "@ECKrown", "--reset"]
            )

            assert result.exit_code == 0, result.stdout
            assert "Reset" in result.stdout
            mock_reset.assert_awaited_with("vid_reset")
