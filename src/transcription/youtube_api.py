"""YouTube Transcript API provider with cookie auth and rate limiting.

Key improvement: Passes an authenticated requests.Session (http_client) to
YouTubeTranscriptApi, which sends cookies from the running Chrome CDP sessions
with every request. This bypasses "Sign in to confirm" IP blocks that occur
when the bare library makes unauthenticated requests from cloud IPs.
"""

import logging
import random
import time

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeRequestFailed,
)

from src.core.exceptions import TranscriptionFailureError
from src.core.schemas import RawTranscript, TranscriptSegment
from src.transcription.failures import create_failure
from src.video.cookie_manager import get_cookie_manager

logger = logging.getLogger(__name__)


class YouTubeAPIProvider:
    """Provides transcripts using the official YouTube Transcript API."""

    def __init__(self, cookie_manager=None):
        self.cookie_manager = cookie_manager or get_cookie_manager()
        self._last_request_time = 0.0
        # Create an authenticated API instance using cookies from CDP
        self._api = self._create_authenticated_api()

    def _create_authenticated_api(self) -> YouTubeTranscriptApi:
        """Create a YouTubeTranscriptApi with cookie-authenticated session.

        The youtube_transcript_api v1.x accepts an http_client parameter
        (a requests.Session). By pre-loading it with YouTube/Google cookies
        extracted from CDP, every request includes auth cookies that bypass
        "Sign in to confirm" challenges on cloud/server IPs.
        """
        try:
            self.cookie_manager.ensure_cookies()
            cookies_dict = self.cookie_manager.get_cookies_dict()

            if cookies_dict:
                session = requests.Session()
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                })
                # Load cookies into the session
                for name, value in cookies_dict.items():
                    # Set on youtube.com and google.com domains
                    session.cookies.set(name, value, domain=".youtube.com")
                    session.cookies.set(name, value, domain=".google.com")

                logger.info(
                    f"YouTubeTranscriptApi: injected {len(cookies_dict)} cookies "
                    f"into authenticated session (CDP source)"
                )
                return YouTubeTranscriptApi(http_client=session)
            else:
                logger.warning("No cookies available for YouTube API - using unauthenticated session")
        except Exception as e:
            logger.warning(f"Failed to create authenticated API session: {e}")

        return YouTubeTranscriptApi()

    def get_transcript(self, video_id: str, language: str = "en") -> RawTranscript:
        """Get transcript using YouTube Transcript API."""
        try:
            # Apply rate limiting
            self._apply_rate_limiting()

            # Ensure cookies are available (for yt-dlp fallback)
            self.cookie_manager.ensure_cookies()

            logger.info(f"Fetching YouTube API transcript for {video_id}")

            # v1.x API with cookie-authenticated http_client
            transcript_list = self._api.list(video_id)

            try:
                # Try requested language first
                transcript = transcript_list.find_transcript([language])
            except NoTranscriptFound:
                # Fallback to any manual transcript with language preference
                try:
                    transcript = transcript_list.find_manually_created_transcript([language, "en"])
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
            if isinstance(e, VideoUnavailable):
                raise TranscriptionFailureError(
                    create_failure(
                        str(e),
                        "unavailable",
                        "youtube_api",
                        video_id=video_id,
                        retryable=False,
                    )
                ) from e
            raise TranscriptionFailureError(
                create_failure(
                    str(e),
                    "provider_error",
                    "youtube_api",
                    video_id=video_id,
                    retryable=False,
                )
            ) from e
        except YouTubeRequestFailed:
            logger.error("YouTube API rate limit or request blocked hit")
            raise TranscriptionFailureError(
                create_failure(
                    "YouTube transcript API request failed",
                    "remote_service",
                    "youtube_api",
                    video_id=video_id,
                )
            )
        except Exception as e:
            logger.error(f"YouTube API error for {video_id}: {e}")
            raise TranscriptionFailureError(
                create_failure(
                    str(e),
                    "provider_error",
                    "youtube_api",
                    video_id=video_id,
                    retryable=False,
                )
            ) from e

    def _apply_rate_limiting(self):
        """Simple rate limiting to avoid TooManyRequests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 2.0:
            delay = 2.0 - elapsed + random.uniform(0.5, 1.5)
            time.sleep(delay)
        self._last_request_time = time.time()

