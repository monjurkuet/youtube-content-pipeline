"""Tests for channel video-to-channel resolution strategies."""

from unittest.mock import patch

import pytest

from src.channel.models import StrategyResult
from src.channel.resolver import resolve_channel_from_video


class TestResolveChannelFromVideo:
    """Test the multi-strategy video-to-channel resolver."""

    def test_delegates_to_ytdlp_when_it_succeeds(self) -> None:
        """The orchestrator should stop at the first successful strategy."""
        with patch(
            "src.channel.resolver.resolve_video_channel_via_ytdlp",
            return_value=StrategyResult(
                success=True,
                channel_id="UC1234567890123456789012",
                channel_handle="TestChannel",
                channel_title="Test Channel",
                source="yt-dlp",
            ),
        ) as mock_ytdlp, patch(
            "src.channel.resolver.resolve_video_channel_via_watch_page"
        ) as mock_watch, patch("src.channel.resolver.resolve_video_channel_via_innertube") as mock_innertube:
            result = resolve_channel_from_video("dQw4w9WgXcQ")

        assert result.success is True
        assert result.channel_id == "UC1234567890123456789012"
        assert result.channel_handle == "TestChannel"
        assert result.source == "yt-dlp"
        mock_ytdlp.assert_called_once_with("dQw4w9WgXcQ")
        mock_watch.assert_not_called()
        mock_innertube.assert_not_called()

    def test_falls_back_to_watch_page(self) -> None:
        """watch page should be used when yt-dlp fails."""
        with patch(
            "src.channel.resolver.resolve_video_channel_via_ytdlp",
            return_value=StrategyResult(
                success=False,
                source="yt-dlp",
                error_message="yt-dlp timeout",
                retryable=True,
            ),
        ) as mock_ytdlp, patch(
            "src.channel.resolver.resolve_video_channel_via_watch_page",
            return_value=StrategyResult(
                success=True,
                channel_id="UC2222222222222222222222",
                channel_handle="WatchPageChannel",
                channel_title="Watch Page Channel",
                source="watch_page",
            ),
        ) as mock_watch, patch("src.channel.resolver.resolve_video_channel_via_innertube") as mock_innertube:
            result = resolve_channel_from_video("dQw4w9WgXcQ")

        assert result.success is True
        assert result.channel_id == "UC2222222222222222222222"
        assert result.channel_handle == "WatchPageChannel"
        assert result.source == "watch_page"
        mock_ytdlp.assert_called_once()
        mock_watch.assert_called_once()
        mock_innertube.assert_not_called()

    def test_falls_back_to_innertube(self) -> None:
        """Innertube should be used when yt-dlp and watch page both fail."""
        with patch(
            "src.channel.resolver.resolve_video_channel_via_ytdlp",
            return_value=StrategyResult(
                success=False,
                source="yt-dlp",
                error_message="yt-dlp failed",
                retryable=True,
            ),
        ), patch(
            "src.channel.resolver.resolve_video_channel_via_watch_page",
            return_value=StrategyResult(
                success=False,
                source="watch_page",
                error_message="watch page failed",
                retryable=True,
            ),
        ), patch(
            "src.channel.resolver.resolve_video_channel_via_innertube",
            return_value=StrategyResult(
                success=True,
                channel_id="UC3333333333333333333333",
                channel_handle="InnerTubeChannel",
                channel_title="Innertube Channel",
                source="innertube",
            ),
        ) as mock_innertube:
            result = resolve_channel_from_video("dQw4w9WgXcQ")

        assert result.success is True
        assert result.channel_id == "UC3333333333333333333333"
        assert result.channel_handle == "InnerTubeChannel"
        assert result.source == "innertube"
        mock_innertube.assert_called_once()

    def test_returns_structured_failure_when_all_strategies_fail(self) -> None:
        """The resolver should return a structured failure object if every strategy fails."""
        with patch(
            "src.channel.resolver.resolve_video_channel_via_ytdlp",
            return_value=StrategyResult(
                success=False,
                source="yt-dlp",
                error_message="yt-dlp failed",
                retryable=True,
            ),
        ), patch(
            "src.channel.resolver.resolve_video_channel_via_watch_page",
            return_value=StrategyResult(
                success=False,
                source="watch_page",
                error_message="watch page failed",
                retryable=True,
            ),
        ), patch(
            "src.channel.resolver.resolve_video_channel_via_innertube",
            return_value=StrategyResult(
                success=False,
                source="innertube",
                error_message="innertube failed",
                retryable=False,
            ),
        ):
            result = resolve_channel_from_video("dQw4w9WgXcQ")

        assert result.success is False
        assert result.source == "structured_failure"
        assert result.error_stage == "all_strategies_failed"
        assert result.retryable is True
        assert result.metadata["failures"]
        assert len(result.metadata["failures"]) == 3

    def test_invalid_video_id_returns_validation_failure(self) -> None:
        """Invalid video IDs should fail fast without contacting external services."""
        result = resolve_channel_from_video("not-a-video-id")

        assert result.success is False
        assert result.source == "validation"
        assert result.error_stage == "video_id_validation"
        assert result.retryable is False

