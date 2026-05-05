"""Source-agnostic transcription handler with fallback chain."""

import logging
from pathlib import Path

from src.core.config import get_settings_with_yaml
from src.core.exceptions import TranscriptionFailureError, WhisperError
from src.core.schemas import RawTranscript

from src.transcription.failures import create_failure, failure_from_exception
from src.video.cookie_manager import get_cookie_manager
from src.transcription.youtube_api import YouTubeAPIProvider
from src.transcription.youtube_downloader import YouTubeDownloader
from src.transcription.whisper_provider import WhisperProvider

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

        if source_type == "local":
            try:
                return self.whisper_provider.transcribe(video_id)
            except Exception as exc:
                raise TranscriptionFailureError(
                    failure_from_exception(
                        exc,
                        stage="transcription",
                        video_id=video_id,
                        default_category="provider_error",
                        retryable=False,
                    )
                ) from exc

        if source_type == "url":
            from src.core.utils import download_remote_file

            try:
                audio_path = download_remote_file(video_id, self.work_dir)
            except Exception as exc:
                raise TranscriptionFailureError(
                    failure_from_exception(
                        exc,
                        stage="download",
                        video_id=video_id,
                        default_category="remote_service",
                    )
                ) from exc

            try:
                return self.whisper_provider.transcribe(str(audio_path))
            except Exception as exc:
                raise TranscriptionFailureError(
                    failure_from_exception(
                        exc,
                        stage="transcription",
                        video_id=video_id,
                        default_category="provider_error",
                        retryable=False,
                    )
                ) from exc

        raise TranscriptionFailureError(
            create_failure(
                f"Unsupported source type: {source_type}",
                "invalid_source",
                "source_identification",
                video_id=video_id,
                retryable=False,
            )
        )

    def _get_youtube_transcript_with_fallback(self, video_id: str) -> RawTranscript:
        """Get YouTube transcript with Whisper fallback."""
        try:
            # Step 1: Try official YouTube API
            return self.youtube_api_provider.get_transcript(video_id)
        except TranscriptionFailureError as exc:
            logger.info(
                "Falling back to Whisper for %s after YouTube API failure: %s",
                video_id,
                exc.failure.message,
            )
            # Step 2: Fallback to audio download + Whisper
            return self._transcribe_youtube_with_whisper(video_id)
        except Exception as exc:
            logger.info(
                "Falling back to Whisper for %s after unexpected YouTube API error: %s",
                video_id,
                exc,
            )
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
        except TranscriptionFailureError:
            raise
        except WhisperError as exc:
            raise TranscriptionFailureError(
                create_failure(
                    str(exc),
                    "provider_error",
                    "transcription",
                    video_id=video_id,
                    retryable=False,
                )
            ) from exc
        except Exception as e:
            raise TranscriptionFailureError(
                failure_from_exception(
                    e,
                    stage="transcription",
                    video_id=video_id,
                    default_category="provider_error",
                    retryable=False,
                )
            ) from e


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
