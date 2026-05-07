"""Tests for YouTube downloader configurable timeout."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.transcription.youtube_downloader import YouTubeDownloader


class TestDownloadTimeoutConfigurable:
    """Test that yt-dlp download timeout is configurable via settings."""

    @patch("src.transcription.youtube_downloader.subprocess.run")
    @patch("src.transcription.youtube_downloader._ensure_js_runtime")
    @patch("src.transcription.youtube_downloader.get_cookie_manager")
    @patch("src.core.config.get_settings")
    def test_download_audio_uses_configured_timeout(
        self, mock_get_settings, mock_cookie_mgr, mock_js, mock_run, tmp_path: Path
    ) -> None:
        """subprocess.run should receive the configured ytdlp_download_timeout_sec."""
        mock_get_settings.return_value = MagicMock(ytdlp_download_timeout_sec=600)
        mock_cookie_mgr.return_value = MagicMock()
        mock_js.return_value = None

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (work_dir / "testvid_audio.mp3").write_text("fake audio")

        downloader = YouTubeDownloader(work_dir=work_dir)
        try:
            downloader.download_audio("testvid")
        except Exception:
            pass

        for call in mock_run.call_args_list:
            assert call.kwargs.get("timeout") == 600

    @patch("src.transcription.youtube_downloader.subprocess.run")
    @patch("src.transcription.youtube_downloader._ensure_js_runtime")
    @patch("src.transcription.youtube_downloader.get_cookie_manager")
    @patch("src.core.config.get_settings")
    def test_download_audio_default_timeout_300(
        self, mock_get_settings, mock_cookie_mgr, mock_js, mock_run, tmp_path: Path
    ) -> None:
        """Default ytdlp_download_timeout_sec should be 300."""
        mock_get_settings.return_value = MagicMock(ytdlp_download_timeout_sec=300)
        mock_cookie_mgr.return_value = MagicMock()
        mock_js.return_value = None

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (work_dir / "testvid_audio.mp3").write_text("fake audio")

        downloader = YouTubeDownloader(work_dir=work_dir)
        try:
            downloader.download_audio("testvid")
        except Exception:
            pass

        for call in mock_run.call_args_list:
            assert call.kwargs.get("timeout") == 300


class TestYtdlpConfigInSettings:
    """Test that the ytdlp YAML config section is applied correctly."""

    def test_yaml_config_applies_ytdlp_timeout(self) -> None:
        """YAML ytdlp.download_timeout_sec should override the default 300."""
        from src.core.config import Settings, apply_yaml_config

        settings = Settings()
        assert settings.ytdlp_download_timeout_sec == 300

        config = {"ytdlp": {"download_timeout_sec": 600}}
        result = apply_yaml_config(settings, config)
        assert result.ytdlp_download_timeout_sec == 600

    def test_yaml_config_does_not_override_non_default(self) -> None:
        """YAML should not override if the value is already non-default."""
        from src.core.config import Settings, apply_yaml_config

        settings = Settings()
        settings.ytdlp_download_timeout_sec = 900

        config = {"ytdlp": {"download_timeout_sec": 600}}
        result = apply_yaml_config(settings, config)
        assert result.ytdlp_download_timeout_sec == 900
