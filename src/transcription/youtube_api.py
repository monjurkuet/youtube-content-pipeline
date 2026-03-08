"""YouTube Transcript API provider with cookie support and rate limiting."""

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeRequestFailed,
)

from src.core.schemas import RawTranscript, TranscriptSegment
from src.video.cookie_manager import get_cookie_manager

logger = logging.getLogger(__name__)


class YouTubeAPIProvider:
    """Provides transcripts using the official YouTube Transcript API."""

    def __init__(self, cookie_manager=None):
        self.cookie_manager = cookie_manager or get_cookie_manager()
        self._last_request_time = 0.0
        # Create API instance for the new v1.x library
        self._api = YouTubeTranscriptApi()

    def get_transcript(self, video_id: str, language: str = "en") -> RawTranscript:
        """Get transcript using YouTube Transcript API."""
        try:
            # Apply rate limiting
            self._apply_rate_limiting()

            # Ensure cookies are available (for yt-dlp fallback)
            self.cookie_manager.ensure_cookies()

            logger.info(f"Fetching YouTube API transcript for {video_id}")

            # Use new v1.x API: create instance and call list()
            # Note: v1.x API doesn't support passing cookies directly
            # Cookies are handled at the HTTP client level if needed
            transcript_list = self._api.list(video_id)

            try:
                # Try requested language
                transcript = transcript_list.find_transcript([language])
            except NoTranscriptFound:
                # Fallback to any manual transcript
                try:
                    transcript = transcript_list.find_manually_created_transcript()
                except NoTranscriptFound:
                    # Fallback to generated transcript
                    transcript = transcript_list.find_generated_transcript([language, "en"])

            data = transcript.fetch()

            segments = [
                TranscriptSegment(
                    text=entry.text,
                    start=entry.start,
                    duration=entry.duration,
                )
                for entry in data
            ]

            return RawTranscript(
                video_id=video_id,
                segments=segments,
                source="youtube_api",
                language=transcript.language_code,
            )

        except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound) as e:
            logger.warning(f"YouTube transcript not available for {video_id}: {e}")
            raise
        except YouTubeRequestFailed:
            logger.error("YouTube API rate limit or request blocked hit")
            raise
        except Exception as e:
            logger.error(f"YouTube API error for {video_id}: {e}")
            raise

    def _apply_rate_limiting(self):
        """Simple rate limiting to avoid TooManyRequests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 2.0:
            delay = 2.0 - elapsed + random.uniform(0.5, 1.5)
            time.sleep(delay)
        self._last_request_time = time.time()
