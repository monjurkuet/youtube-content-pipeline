"""Source-agnostic transcription handler with fallback chain."""

import logging
from pathlib import Path
from typing import Any

from rich.console import Console

from src.core.config import get_settings_with_yaml
from src.core.exceptions import WhisperError
from src.core.schemas import RawTranscript

from src.video.cookie_manager import get_cookie_manager
from src.transcription.youtube_api import YouTubeAPIProvider
from src.transcription.youtube_downloader import YouTubeDownloader, ErrorCategory
from src.transcription.whisper_provider import WhisperProvider, check_intel_gpu

console = Console()
logger = logging.getLogger(__name__)


class TranscriptionHandler:
    """Handle transcript acquisition from any source with fallback chain."""

    def __init__(self, work_dir: Path | None = None):
        self.settings = get_settings_with_yaml()
        self.work_dir = work_dir or Path(self.settings.work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Initialize providers
        self.cookie_manager = get_cookie_manager()
        self.youtube_api_provider = YouTubeAPIProvider(self.cookie_manager)
        self.youtube_downloader = YouTubeDownloader(self.work_dir, self.cookie_manager)
        self.whisper_provider = WhisperProvider(self.settings)

    def get_transcript(self, video_id: str, source_type: str = "youtube") -> RawTranscript:
        """Get transcript with automatic fallback."""
        if source_type == "youtube":
            return self._get_youtube_transcript_with_fallback(video_id)
        elif source_type == "local":
            return self.whisper_provider.transcribe(video_id)
        elif source_type == "url":
            # For remote URLs, download and transcribe
            from src.core.utils import download_remote_file
            audio_path = download_remote_file(video_id, self.work_dir)
            return self.whisper_provider.transcribe(str(audio_path))
        else:
            raise ValueError(f"Unsupported source type: {source_type}")

    def _get_youtube_transcript_with_fallback(self, video_id: str) -> RawTranscript:
        """Get YouTube transcript with Whisper fallback."""
        try:
            # Step 1: Try official YouTube API
            return self.youtube_api_provider.get_transcript(video_id)
        except Exception:
            # Step 2: Fallback to audio download + Whisper
            return self._transcribe_youtube_with_whisper(video_id)

    def _transcribe_youtube_with_whisper(self, video_id: str) -> RawTranscript:
        """Download YouTube audio and transcribe with Whisper."""
        try:
            # Download audio
            audio_path = self.youtube_downloader.download_audio(video_id)

            # Transcribe with Whisper
            result = self.whisper_provider.transcribe(str(audio_path))
            result.video_id = video_id
            return result
        except WhisperError:
            raise
        except Exception as e:
            raise WhisperError(f"Whisper transcription failed for {video_id}: {e}")

    # Aliases for compatibility if needed
    def _check_video_availability(self, video_id: str) -> tuple[bool, str, ErrorCategory]:
        return self.youtube_downloader.check_video_availability(video_id)

    def _classify_error(self, error_detail: str) -> tuple[str, ErrorCategory]:
        return self.youtube_downloader.classify_error(error_detail)

    def _download_youtube_audio(self, video_id: str) -> Path:
        return self.youtube_downloader.download_audio(video_id)

    def _transcribe_with_whisper(self, audio_path: str) -> RawTranscript:
        return self.whisper_provider.transcribe(audio_path)

    def _check_intel_gpu(self) -> bool:
        return check_intel_gpu()


def identify_source_type(source: str) -> tuple[str, str]:
    """Identify video source type and extract identifier."""
    # YouTube URL
    if "youtube.com" in source or "youtu.be" in source:
        from src.core.utils import extract_video_id
        video_id = extract_video_id(source)
        if video_id:
            return "youtube", video_id

    # Local file
    if Path(source).exists():
        return "local", str(source)

    # Remote URL
    if source.startswith(("http://", "https://")):
        return "url", source

    # Assume YouTube ID if matches pattern
    import re
    if re.match(r"^[a-zA-Z0-9_-]{11}$", source):
        return "youtube", source

    raise ValueError(f"Could not identify source type: {source}")
