"""Source-agnostic transcription handler with fallback chain."""

import random
import re
import subprocess
import time
from pathlib import Path

from rich.console import Console

from src.core.config import get_settings_with_yaml
from src.core.exceptions import TranscriptError, WhisperError, YouTubeAPIError
from src.core.schemas import RawTranscript, TranscriptSegment
from src.video.cookie_manager import get_cookie_manager

console = Console()


class TranscriptionHandler:
    """Handle transcript acquisition from any source with fallback chain."""

    def __init__(self, work_dir: Path | None = None):
        self.settings = get_settings_with_yaml()
        self.work_dir = work_dir or self.settings.work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Initialize cookie manager
        self.cookie_manager = get_cookie_manager(
            cache_duration_hours=self.settings.youtube_api_cookie_cache_hours
        )

        # Track last request time for rate limiting
        self._last_request_time: float | None = None

    def get_transcript(self, video_id: str, source_type: str = "youtube") -> RawTranscript:
        """
        Get transcript with automatic fallback.

        For YouTube:
        1. Try YouTube Transcript API (fast, accurate)
        2. Fallback: Download audio + Whisper OpenVINO

        For other sources:
        - Direct Whisper transcription

        Args:
            video_id: Video ID or identifier
            source_type: "youtube", "url", or "local"

        Returns:
            RawTranscript object
        """
        if source_type == "youtube":
            return self._get_youtube_transcript_with_fallback(video_id)
        else:
            # For non-YouTube, use Whisper directly
            return self._transcribe_with_whisper(video_id)

    def _get_youtube_transcript_with_fallback(self, video_id: str) -> RawTranscript:
        """Get YouTube transcript with Whisper fallback."""
        # Try YouTube API first
        try:
            return self._get_youtube_api_transcript(video_id)
        except YouTubeAPIError as e:
            print(f"YouTube API failed: {e}")
            print("Falling back to Whisper transcription...")

        # Fallback to Whisper
        try:
            return self._transcribe_youtube_with_whisper(video_id)
        except Exception as e:
            raise TranscriptError(f"All transcription methods failed: {e}") from e

    def _apply_rate_limiting(self):
        """Apply rate limiting delay before making a request."""
        if not self.settings.rate_limiting_enabled:
            return

        if self._last_request_time is not None:
            # Calculate random delay
            min_delay = self.settings.rate_limiting_min_delay
            max_delay = self.settings.rate_limiting_max_delay
            delay = random.uniform(min_delay, max_delay)

            elapsed = time.time() - self._last_request_time
            if elapsed < delay:
                sleep_time = delay - elapsed
                console.print(f"[dim]   Rate limiting: waiting {sleep_time:.1f}s...[/dim]")
                time.sleep(sleep_time)

        self._last_request_time = time.time()

    def _get_youtube_api_transcript(self, video_id: str) -> RawTranscript:
        """Get transcript using YouTube Transcript API with cookies and rate limiting."""
        # Apply rate limiting
        self._apply_rate_limiting()

        # Retry logic for rate limit errors
        retries = 0
        last_error = None

        while retries <= self.settings.rate_limiting_max_retries:
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                from youtube_transcript_api._errors import (
                    HTTPError,
                    IpBlocked,
                    RequestBlocked,
                    TranscriptsDisabled,
                    VideoUnavailable,
                )

                ytt_api = YouTubeTranscriptApi()

                # Add cookies if enabled and available
                if self.settings.youtube_api_use_cookies:
                    cookie_string = self.cookie_manager.get_cookie_string()
                    if cookie_string:
                        console.print("[dim]   Using browser cookies for YouTube API[/dim]")
                        # Monkey-patch requests to use our cookies
                        # youtube_transcript_api uses requests internally
                        import requests

                        original_session = requests.Session

                        def patched_session(
                            *args,
                            _cookie_string=cookie_string,
                            _original_session=original_session,
                            **kwargs,
                        ):
                            session = _original_session(*args, **kwargs)
                            # Parse cookie string and add to session
                            for cookie_part in _cookie_string.split("; "):
                                if "=" in cookie_part:
                                    name, value = cookie_part.split("=", 1)
                                    session.cookies.set(name, value, domain=".youtube.com")
                            return session

                        requests.Session = patched_session

                try:
                    # Fetch transcript
                    transcript_list = ytt_api.fetch(
                        video_id, languages=self.settings.youtube_api_languages
                    )
                finally:
                    # Restore original Session
                    if self.settings.youtube_api_use_cookies and cookie_string:
                        requests.Session = original_session  # type: ignore[possibly-unbound]

                segments = [
                    TranscriptSegment(
                        text=item.text,
                        start=float(item.start),
                        duration=float(item.duration),
                    )
                    for item in transcript_list
                ]

                return RawTranscript(
                    video_id=video_id,
                    segments=segments,
                    source="youtube_api",
                    language="en",
                )

            except (IpBlocked, RequestBlocked) as e:
                retries += 1
                last_error = e
                if retries <= self.settings.rate_limiting_max_retries:
                    wait_time = self.settings.rate_limiting_retry_delay * (2 ** (retries - 1))
                    msg = f"[yellow]   IP blocked/rate limited, retrying in {wait_time:.1f}s "
                    msg += f"(attempt {retries}/{self.settings.rate_limiting_max_retries + 1})"
                    msg += "...[/yellow]"
                    console.print(msg)
                    time.sleep(wait_time)
                else:
                    raise YouTubeAPIError(
                        f"IP blocked after {retries} attempts. Consider using proxies."
                    ) from e

            except (TranscriptsDisabled, VideoUnavailable) as e:
                # These are not retryable errors
                raise YouTubeAPIError(f"YouTube API failed: {e}") from e

            except HTTPError as e:
                # Check if it's a rate limit error
                error_msg = str(e).lower()
                if "429" in error_msg or "too many requests" in error_msg:
                    retries += 1
                    last_error = e
                    if retries <= self.settings.rate_limiting_max_retries:
                        wait_time = self.settings.rate_limiting_retry_delay * (2 ** (retries - 1))
                        msg = f"[yellow]   HTTP 429 rate limit, retrying in {wait_time:.1f}s "
                        msg += f"(attempt {retries}/{self.settings.rate_limiting_max_retries + 1})"
                        msg += "...[/yellow]"
                        console.print(msg)
                        time.sleep(wait_time)
                    else:
                        raise YouTubeAPIError(
                            f"Rate limit exceeded after {retries} attempts"
                        ) from e
                else:
                    raise YouTubeAPIError(f"YouTube API HTTP error: {e}") from e

            except Exception as e:
                # Check if it's a rate limit error in disguise
                error_msg = str(e).lower()
                if (
                    "too many requests" in error_msg
                    or "rate limit" in error_msg
                    or "429" in error_msg
                ):
                    retries += 1
                    last_error = e
                    if retries <= self.settings.rate_limiting_max_retries:
                        wait_time = self.settings.rate_limiting_retry_delay * (2 ** (retries - 1))
                        msg = f"[yellow]   Rate limit detected, retrying in {wait_time:.1f}s "
                        msg += f"(attempt {retries}/{self.settings.rate_limiting_max_retries + 1})"
                        msg += "...[/yellow]"
                        console.print(msg)
                        time.sleep(wait_time)
                    else:
                        raise YouTubeAPIError(
                            f"Rate limit exceeded after {retries} attempts"
                        ) from e
                else:
                    raise YouTubeAPIError(f"YouTube API failed: {e}") from e

        # Should not reach here, but just in case
        raise YouTubeAPIError(f"Failed after {retries} retries: {last_error}")

    def _transcribe_youtube_with_whisper(self, video_id: str) -> RawTranscript:
        """Download YouTube audio and transcribe with Whisper."""
        # Download audio only
        audio_path = self._download_youtube_audio(video_id)

        try:
            result = self._transcribe_with_whisper(str(audio_path))
            result.source = "whisper"
            return result
        finally:
            # Cleanup
            if audio_path.exists():
                audio_path.unlink()

    def _download_youtube_audio(self, video_id: str) -> Path:
        """Download audio from YouTube video using browser cookies."""
        # Apply rate limiting
        self._apply_rate_limiting()

        output_path = self.work_dir / f"{video_id}_audio.mp3"
        url = f"https://www.youtube.com/watch?v={video_id}"

        # Build command
        cmd = [
            "yt-dlp",
            "-f",
            "bestaudio/best",
            "--extract-audio",
            "--audio-format",
            self.settings.audio_format,
            "--audio-quality",
            self.settings.audio_bitrate,
            "-o",
            str(output_path.with_suffix(".%(ext)s")),
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--js-runtimes",
            "node",
        ]

        # Add cookies from browser
        if self.cookie_manager.ensure_cookies():
            cookie_args = self.cookie_manager.get_cookie_args()
            if cookie_args:
                cmd.extend(cookie_args)
                console.print("[dim]   Using browser cookies for audio download[/dim]")

        cmd.append(url)

        try:
            subprocess.run(cmd, check=True, timeout=300, capture_output=True, text=True)

            # Find the downloaded file (may have different extension)
            for ext in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                candidate = output_path.with_suffix(ext)
                if candidate.exists():
                    return candidate

            # Check for any audio file in work_dir
            for f in self.work_dir.glob(f"{video_id}_audio.*"):
                if f.suffix in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                    return f

            raise WhisperError("Audio download completed but file not found")

        except subprocess.TimeoutExpired as e:
            raise WhisperError("Audio download timeout") from e
        except subprocess.CalledProcessError as e:
            error_detail = e.stderr if e.stderr else str(e)
            raise WhisperError(f"Audio download failed: {error_detail}") from e

    def _transcribe_with_whisper(self, audio_path: str) -> RawTranscript:
        """Transcribe audio file using OpenVINO Whisper."""
        from src.transcription.whisper_openvino import OpenVINOWhisperTranscriber

        transcriber = OpenVINOWhisperTranscriber(
            model_id=self.settings.openvino_whisper_model,
            device=self.settings.openvino_device,
            cache_dir=self.settings.openvino_cache_dir,
        )

        result = transcriber.transcribe(
            audio_path,
            chunk_length=self.settings.whisper_chunk_length,
        )

        # Convert to RawTranscript format
        segments = [
            TranscriptSegment(
                text=seg["text"],
                start=float(seg["start"]),
                duration=float(seg["end"] - seg["start"]),
            )
            for seg in result.get("segments", [])
        ]

        # Extract video_id from audio path (remove _audio suffix)
        audio_filename = Path(audio_path).stem
        video_id = (
            audio_filename.replace("_audio", "")
            if audio_filename.endswith("_audio")
            else audio_filename
        )

        return RawTranscript(
            video_id=video_id,
            segments=segments,
            source="whisper",
            language=result.get("language", "en"),
        )


def identify_source_type(source: str) -> tuple[str, str]:
    """
    Identify video source type and extract identifier.

    Returns:
        Tuple of (source_type, identifier)
    """
    # YouTube patterns
    youtube_patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",  # Just the ID
    ]

    for pattern in youtube_patterns:
        match = re.search(pattern, source)
        if match:
            return ("youtube", match.group(1))

    # Local file - check this BEFORE URL parsing to avoid issues
    source_path = Path(source)
    if source_path.exists() and source_path.is_file():
        return ("local", str(source_path.resolve()))

    # URL - check if it's a valid HTTP(S) URL
    from urllib.parse import urlparse

    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        return ("url", source)

    raise ValueError(f"Unknown source type: {source}")
