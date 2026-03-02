"""Source-agnostic transcription handler with fallback chain."""

import json
import logging
import os
import random
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

import torch
from rich.console import Console

from src.core.config import get_settings_with_yaml
from src.core.exceptions import TranscriptError, WhisperError, YouTubeAPIError
from src.core.schemas import RawTranscript, TranscriptSegment
from src.video.cookie_manager import get_cookie_manager

console = Console()
logger = logging.getLogger(__name__)

# Error category type for structured error tracking
ErrorCategory = Literal[
    "geo_restricted",
    "members_only",
    "age_restricted",
    "temporary_block",
    "private",
    "unavailable",
    "live_stream",
    "unknown",
]

# JS Runtime paths (bun is preferred for yt-dlp JS challenges)
BUN_PATH = "/root/.bun/bin/bun"
DENO_PATH = "/root/.deno/bin/deno"


def _find_js_runtime(preferred: str = "bun") -> tuple[str, str] | None:
    """
    Find available JS runtime.

    Args:
        preferred: Preferred runtime ('bun' or 'deno')

    Returns:
        Tuple of (runtime_name, path) or None if not found
    """
    # Check preferred runtime first
    if preferred == "bun":
        bun_path = shutil.which("bun")
        if bun_path:
            return ("bun", bun_path)
        if os.path.isfile(BUN_PATH) and os.access(BUN_PATH, os.X_OK):
            return ("bun", BUN_PATH)

    # Check deno
    deno_path = shutil.which("deno")
    if deno_path:
        return ("deno", deno_path)
    if os.path.isfile(DENO_PATH) and os.access(DENO_PATH, os.X_OK):
        return ("deno", DENO_PATH)

    # Check bun as fallback
    if preferred != "bun":
        bun_path = shutil.which("bun")
        if bun_path:
            return ("bun", bun_path)
        if os.path.isfile(BUN_PATH) and os.access(BUN_PATH, os.X_OK):
            return ("bun", BUN_PATH)

    return None


def _ensure_js_runtime() -> tuple[bool, str]:
    """
    Check if a JS runtime is available.

    Returns:
        Tuple of (success, message)
    """
    runtime = _find_js_runtime()
    if runtime:
        console.print(f"[dim]   {runtime[0].title()} found: {runtime[1]}[/dim]")
        return (True, f"{runtime[0]} is available")

    console.print("[yellow]   No JS runtime found.[/yellow]")
    console.print("[dim]   Install bun: curl -fsSL https://bun.sh/install | bash[/dim]")
    console.print("[dim]   Install deno: curl -fsSL https://deno.land/install.sh | sh[/dim]")
    return (False, "No JS runtime available")


def _get_yt_dlp_base_cmd(output_path: Path) -> list:
    """
    Build base yt-dlp command with recommended args for 2026 YouTube.

    Args:
        output_path: Output file path
        js_runtime: JS runtime to use (deno or node)

    Returns:
        List of command line arguments
    """
    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",  # Best quality
        "-o", str(output_path.with_suffix(".%(ext)s")),
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        # Extractor args to bypass 403 errors (2026 YouTube updates)
        "--extractor-args", "youtube:player_js_version=actual",
        "--extractor-args", "youtube:player_client=default,web_safari",
        # Reconnect args for stability
        "--downloader-args", "ffmpeg_i:-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        # User agent to match browser
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    # Add JS runtime (bun is preferred for YouTube JS challenges, fallback to deno)
    runtime = _find_js_runtime(preferred="bun")
    if runtime:
        cmd.extend(["--js-runtimes", runtime[0]])

    return cmd


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
                cookie_string = None
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
                    # Fetch transcript - try multiple language options
                    transcript_list = None

                    # Try English (auto-generated)
                    try:
                        transcript_list = ytt_api.fetch(
                            video_id, languages=self.settings.youtube_api_languages
                        )
                    except Exception:
                        pass

                    # If still no transcript, try all available languages
                    if transcript_list is None:
                        try:
                            # Try any manually created or generated transcripts
                            transcript_list = ytt_api.fetch(video_id)
                        except Exception:
                            pass

                    if transcript_list is None:
                        raise YouTubeAPIError("No transcript available in any language")
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

    def _check_video_availability(self, video_id: str) -> tuple[bool, str, ErrorCategory]:
        """
        Check if video is available for transcription using yt-dlp.

        This is a pre-flight check to avoid wasting download attempts on
        permanently unavailable videos.

        Args:
            video_id: YouTube video ID

        Returns:
            Tuple of (is_available, reason, error_category)
        """
        try:
            cmd = [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                "--no-warnings",
                "--quiet",
                f"https://www.youtube.com/watch?v={video_id}",
            ]

            # Try with cookies first
            result = None
            if self.cookie_manager.ensure_cookies():
                cookie_args = self.cookie_manager.get_cookie_args()
                if cookie_args:
                    cmd_with_cookies = cmd + cookie_args
                    result = subprocess.run(cmd_with_cookies, capture_output=True, text=True, timeout=15)

                    # Check if cookies caused "No video formats found" error
                    if result.returncode != 0 and "No video formats found" in result.stderr:
                        logger.warning("Cookies caused 'No video formats found' error in pre-flight check, retrying without cookies")
                        result = None  # Will retry without cookies below

            # If no cookies used or cookies failed, try without cookies
            if result is None:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

            # Check stderr for errors
            if result.returncode != 0:
                error_msg = result.stderr.strip().lower()
                error_detail = result.stderr.strip()

                # Classify the error
                if "live event" in error_msg or "upcoming" in error_msg:
                    return False, "Live stream (upcoming)", "live_stream"
                elif "private" in error_msg:
                    return False, "Video is private", "private"
                elif "unavailable" in error_msg or "not available" in error_msg:
                    return False, "Video unavailable", "unavailable"
                elif "members-only" in error_msg or "join this channel" in error_msg:
                    return False, "Members-only video", "members_only"
                elif "age" in error_msg and ("restricted" in error_msg or "verification" in error_msg):
                    return False, "Age-restricted", "age_restricted"
                elif "geo" in error_msg or "country" in error_msg or "not available in your region" in error_msg:
                    return False, "Geo-restricted", "geo_restricted"
                elif "403" in error_msg and "forbidden" in error_msg:
                    # Could be temporary or permanent
                    return False, "Access forbidden (403)", "temporary_block"
                else:
                    return False, f"Video error: {error_detail[:50]}", "unknown"

            if not result.stdout.strip():
                return False, "No video metadata", "unavailable"

            data = json.loads(result.stdout.strip())

            # Check for live stream indicators
            live_status = data.get("live_status")
            if live_status in ["is_live", "is_upcoming", "post_live"]:
                return False, f"Live stream ({live_status})", "live_stream"

            # Check availability field
            availability = data.get("availability")
            if availability == "private":
                return False, "Video is private", "private"
            elif availability == "unavailable":
                return False, "Video unavailable", "unavailable"

            # Check for members-only content
            if data.get("is_members_only") or "members-only" in str(data).lower():
                return False, "Members-only video", "members_only"

            # Check for basic metadata (if we have title, it's likely playable)
            if not data.get("title"):
                return False, "Missing video title", "unavailable"

            return True, "Available", "unknown"

        except subprocess.TimeoutExpired:
            return False, "Timeout checking video", "unknown"
        except json.JSONDecodeError:
            return False, "Invalid video metadata", "unknown"
        except Exception as e:
            return False, f"Check failed: {str(e)[:50]}", "unknown"

    def _classify_error(self, error_detail: str) -> tuple[str, ErrorCategory]:
        """
        Classify yt-dlp error into structured categories.

        Args:
            error_detail: Error message from yt-dlp stderr

        Returns:
            Tuple of (human_readable_reason, error_category)
        """
        error_lower = error_detail.lower()

        # Private videos
        if "private video" in error_lower or "video is private" in error_lower:
            return "Video is private", "private"

        # Unavailable videos
        if "this video is unavailable" in error_lower or "video unavailable" in error_lower:
            return "Video unavailable", "unavailable"

        # Members-only content
        members_patterns = ["members-only", "join this channel", "channel members", "only available for members", "members only"]
        if any(pattern in error_lower for pattern in members_patterns):
            return "Members-only video", "members_only"

        # Age-restricted content
        if "age-restricted" in error_lower or "age verification" in error_lower or "sign in" in error_lower:
            return "Age-restricted (sign in required)", "age_restricted"

        # Geo-restriction - check for various patterns
        geo_patterns = [
            "geo",
            "country",
            "not available in your region",
            "not available in this country",
            "restricted in your country",
        ]
        if any(pattern in error_lower for pattern in geo_patterns):
            return "Geo-restricted content", "geo_restricted"

        # HTTP 403 Forbidden - could be temporary or permanent
        if "403" in error_lower and "forbidden" in error_lower:
            # Try to distinguish temporary vs permanent
            if any(pattern in error_lower for pattern in geo_patterns):
                return "Access forbidden (geo-restricted)", "geo_restricted"
            # Check for signs this might be a temporary/sign-in issue
            elif "sign in" in error_lower or "log in" in error_lower or "account" in error_lower:
                return "Access forbidden (sign in required)", "age_restricted"
            else:
                # Default: treat as temporary block (IP-level block from CDN)
                # Allow retry with fresh cookies
                return "Access forbidden (likely temporary IP block)", "temporary_block"

        # Copyright claims
        if "copyright claim" in error_lower or "contains content from" in error_lower:
            return "Copyright claim", "unavailable"

        # Live streams
        if "live event" in error_lower or "upcoming" in error_lower or "premiere" in error_lower:
            return "Live stream or premiere", "live_stream"

        # Default - unknown (might be retryable)
        return f"Download error: {error_detail[:100]}", "unknown"

    def _download_youtube_audio(self, video_id: str) -> Path:
        """Download audio from YouTube video using browser cookies."""
        logger.info(f"Starting audio download for video: {video_id}")

        # Apply rate limiting
        self._apply_rate_limiting()

        # PRE-FLIGHT CHECK: Check video availability before attempting download
        console.print("[dim]   Checking video availability...[/dim]")
        is_available, reason, error_category = self._check_video_availability(video_id)

        logger.info(f"Pre-flight check result: available={is_available}, reason={reason}, category={error_category}")

        if not is_available:
            error_msg = f"Pre-flight check failed: {reason}"
            console.print(f"[yellow]   {error_msg}[/yellow]")
            # Raise appropriate error based on category
            if error_category == "geo_restricted":
                raise WhisperError(f"Geo-restricted: {reason}")
            elif error_category == "members_only":
                raise WhisperError(f"Members-only: {reason}")
            elif error_category == "age_restricted":
                raise WhisperError(f"Age-restricted: {reason}")
            elif error_category == "private":
                raise WhisperError(f"Private video: {reason}")
            elif error_category == "live_stream":
                raise WhisperError(f"Live stream: {reason}")
            else:
                raise WhisperError(error_msg)

        console.print(f"[dim]   Video available: {reason}[/dim]")

        output_path = self.work_dir / f"{video_id}_audio.mp3"
        url = f"https://www.youtube.com/watch?v={video_id}"

        # Ensure JS runtime is available (bun preferred, deno fallback)
        _ensure_js_runtime()

        # Define format fallback options
        format_options = [
            "bestaudio/best",  # Primary option
            "bestaudio",       # Fallback without /best restriction
            "m4a/mp3/aac/opus/m4r/flac/wav",  # Specific audio formats
        ]

        # Try different format options with cookies first
        last_error = None
        last_error_category: ErrorCategory = "unknown"
        consecutive_403_errors = 0  # Track consecutive 403 errors for IP block detection

        for format_option in format_options:
            # Build command with current format option using base command
            cmd = _get_yt_dlp_base_cmd(output_path)
            cmd.insert(2, "-f")  # Insert format after yt-dlp
            cmd.insert(3, format_option)

            # Add cookies from browser
            if self.cookie_manager.ensure_cookies():
                cookie_args = self.cookie_manager.get_cookie_args()
                if cookie_args:
                    cmd.extend(cookie_args)
                    logger.info(f"Using cached cookies for audio download (format: {format_option})")
                    console.print(f"[dim]   Using browser cookies for audio download (format: {format_option})[/dim]")

            cmd.append(url)

            try:
                result = subprocess.run(cmd, check=True, timeout=300, capture_output=True, text=True)

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

            except subprocess.CalledProcessError as e:
                error_detail = e.stderr if e.stderr else str(e)
                last_error = error_detail
                _, last_error_category = self._classify_error(error_detail)

                # Check if cookies caused "No video formats found" error
                if "No video formats found" in error_detail and "--cookies" in " ".join(cmd):
                    logger.warning("Cookies caused 'No video formats found' error, retrying without cookies")
                    console.print("[dim]   Cookies caused error, retrying without cookies...[/dim]")

                    # Build command without cookies
                    cmd_no_cookies = _get_yt_dlp_base_cmd(output_path)
                    cmd_no_cookies.insert(2, "-f")
                    cmd_no_cookies.insert(3, format_option)
                    cmd_no_cookies.append(url)

                    try:
                        subprocess.run(cmd_no_cookies, check=True, timeout=300, capture_output=True, text=True)

                        # Find the downloaded file
                        for ext in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                            candidate = output_path.with_suffix(ext)
                            if candidate.exists():
                                return candidate

                        # Check for any audio file in work_dir
                        for f in self.work_dir.glob(f"{video_id}_audio.*"):
                            if f.suffix in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                                return f

                        raise WhisperError("Audio download completed but file not found")

                    except subprocess.CalledProcessError as e2:
                        # Update error detail with the no-cookies error
                        last_error = e2.stderr if e2.stderr else str(e2)
                        _, last_error_category = self._classify_error(last_error)

                        # If the no-cookies retry got a 403, trigger 403 error handling
                        if last_error_category == "temporary_block":
                            consecutive_403_errors += 1
                            timestamp = datetime.now().isoformat()
                            logger.warning(f"403 error detected at {timestamp} (consecutive: {consecutive_403_errors})")
                            logger.warning(f"403 error details: Access forbidden (likely temporary IP block)")
                            logger.warning(f"403 error detail: {last_error[:200]}")
                            console.print(f"[yellow]   403 error detected (consecutive: {consecutive_403_errors})[/yellow]")
                            console.print(f"[yellow]   Details: Access forbidden (likely temporary IP block)[/yellow]")

                            # Invalidate cookie cache and refresh
                            logger.info("Invalidating cookie cache...")
                            console.print("[yellow]   Invalidating cookie cache...[/yellow]")
                            self.cookie_manager.invalidate_cache()

                            logger.info("Waiting 5 seconds before refreshing cookies...")
                            console.print("[yellow]   Waiting 5 seconds before refreshing cookies...[/yellow]")
                            time.sleep(5)

                            logger.info("Refreshing cookies from browser...")
                            console.print("[yellow]   Refreshing cookies from browser...[/yellow]")
                            refresh_success = self.cookie_manager.ensure_cookies()
                            logger.info(f"Cookie refresh result: {refresh_success}")

                            logger.info(f"Retrying with fresh cookies (attempt {consecutive_403_errors})...")
                            console.print(f"[yellow]   Retrying with fresh cookies (attempt {consecutive_403_errors})...[/yellow]")
                            continue

                # Format availability error - try next format
                if "Requested format is not available" in last_error or "format is not available" in last_error:
                    console.print(f"[dim]   Format '{format_option}' not available, trying next option...[/dim]")
                    continue

                # Permanent errors - don't retry
                if last_error_category in ["private", "members_only", "age_restricted", "geo_restricted", "live_stream", "unavailable"]:
                    raise WhisperError(f"Permanent error: {last_error}") from e

                # Temporary 403 - might be retryable with different cookies
                if last_error_category == "temporary_block":
                    consecutive_403_errors += 1
                    timestamp = datetime.now().isoformat()
                    logger.warning(f"403 error detected at {timestamp} (consecutive: {consecutive_403_errors})")
                    logger.warning(f"403 error details: Access forbidden (likely temporary IP block)")
                    logger.warning(f"403 error detail: {last_error[:200]}")
                    console.print(f"[yellow]   403 error detected (consecutive: {consecutive_403_errors})[/yellow]")
                    console.print(f"[yellow]   Details: Access forbidden (likely temporary IP block)[/yellow]")

                    # Invalidate cookie cache and refresh
                    logger.info("Invalidating cookie cache...")
                    console.print("[yellow]   Invalidating cookie cache...[/yellow]")
                    self.cookie_manager.invalidate_cache()

                    logger.info("Waiting 5 seconds before refreshing cookies...")
                    console.print("[yellow]   Waiting 5 seconds before refreshing cookies...[/yellow]")
                    time.sleep(5)

                    logger.info("Refreshing cookies from browser...")
                    console.print("[yellow]   Refreshing cookies from browser...[/yellow]")
                    refresh_success = self.cookie_manager.ensure_cookies()
                    logger.info(f"Cookie refresh result: {refresh_success}")

                    logger.info(f"Retrying with fresh cookies (attempt {consecutive_403_errors})...")
                    console.print(f"[yellow]   Retrying with fresh cookies (attempt {consecutive_403_errors})...[/yellow]")
                    continue

                # Some other error, don't retry
                raise WhisperError(f"Audio download failed: {last_error}") from e
                # Check if this is a format availability error
                if "Requested format is not available" in error_detail or "format is not available" in error_detail:
                    console.print(f"[dim]   Format '{format_option}' not available, trying next option...[/dim]")
                    continue

                # Classify and handle the error
                reason, category = self._classify_error(error_detail)

                # Permanent errors - don't retry
                if category in ["private", "members_only", "age_restricted", "geo_restricted", "live_stream", "unavailable"]:
                    raise WhisperError(f"{reason}: {error_detail}") from e

                # Temporary 403 - refresh cookies and retry
                if category == "temporary_block":
                    consecutive_403_errors += 1
                    timestamp = datetime.now().isoformat()
                    logger.warning(f"403 error detected at {timestamp} (consecutive: {consecutive_403_errors})")
                    logger.warning(f"403 error details: {reason}")
                    logger.warning(f"403 error detail: {error_detail[:200]}")
                    console.print(f"[yellow]   403 error detected (consecutive: {consecutive_403_errors})[/yellow]")
                    console.print(f"[yellow]   Details: {reason}[/yellow]")

                    # Invalidate cookie cache and refresh
                    logger.info("Invalidating cookie cache...")
                    console.print("[yellow]   Invalidating cookie cache...[/yellow]")
                    self.cookie_manager.invalidate_cache()

                    logger.info("Waiting 5 seconds before refreshing cookies...")
                    console.print("[yellow]   Waiting 5 seconds before refreshing cookies...[/yellow]")
                    time.sleep(5)

                    logger.info("Refreshing cookies from browser...")
                    console.print("[yellow]   Refreshing cookies from browser...[/yellow]")
                    refresh_success = self.cookie_manager.ensure_cookies()
                    logger.info(f"Cookie refresh result: {refresh_success}")

                    logger.info(f"Retrying with fresh cookies (attempt {consecutive_403_errors})...")
                    console.print(f"[yellow]   Retrying with fresh cookies (attempt {consecutive_403_errors})...[/yellow]")
                    continue

                # Some other error, don't retry
                raise WhisperError(f"Audio download failed: {error_detail}") from e

            except subprocess.TimeoutExpired:
                raise WhisperError("Audio download timeout")

        # If all format options with cookies failed, try --cookies-from-browser
        logger.info("Cookie file approach failed, trying --cookies-from-browser...")
        console.print("[dim]   Cookie file approach failed, trying --cookies-from-browser...[/dim]")

        # Try --cookies-from-browser with available browsers
        browsers_to_try = self.cookie_manager.get_available_browsers()
        if not browsers_to_try:
            browsers_to_try = ["chrome"]  # Default fallback

        logger.info(f"Available browsers for cookie extraction: {browsers_to_try}")

        for browser in browsers_to_try:
            logger.info(f"Trying --cookies-from-browser={browser}...")
            try:
                # Use base command with extractor args and --cookies-from-browser
                browser_cmd = _get_yt_dlp_base_cmd(output_path)
                browser_cmd.insert(2, "-f")
                browser_cmd.insert(3, "bestaudio/best")
                browser_cmd.extend(["--cookies-from-browser", browser])

                console.print(f"[dim]   Trying --cookies-from-browser={browser}...[/dim]")

                subprocess.run(browser_cmd, check=True, timeout=300, capture_output=True, text=True)

                # Find the downloaded file
                for ext in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                    candidate = output_path.with_suffix(ext)
                    if candidate.exists():
                        logger.info(f"Successfully downloaded audio using --cookies-from-browser={browser}")
                        console.print(f"[green]   Success with --cookies-from-browser={browser}![/green]")
                        return candidate

                # Check for any audio file in work_dir
                for f in self.work_dir.glob(f"{video_id}_audio.*"):
                    if f.suffix in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                        logger.info(f"Successfully downloaded audio using --cookies-from-browser={browser}")
                        console.print(f"[green]   Success with --cookies-from-browser={browser}![/green]")
                        return f

            except subprocess.CalledProcessError as e:
                logger.warning(f"--cookies-from-browser={browser} failed: {e.stderr[:200] if e.stderr else str(e)}")
                console.print(f"[dim]   --cookies-from-browser={browser} failed, trying next...[/dim]")
                continue
            except subprocess.TimeoutExpired:
                logger.warning(f"--cookies-from-browser={browser} timed out")
                console.print(f"[dim]   --cookies-from-browser={browser} timed out...[/dim]")
                continue

        # Final attempt without cookies (with extractor args for 2026 YouTube)
        logger.info("All cookie-based methods failed, trying without cookies...")
        console.print("[dim]   --cookies-from-browser failed, trying without cookies...[/dim]")

        final_cmd = _get_yt_dlp_base_cmd(output_path)
        final_cmd.insert(2, "-f")
        final_cmd.insert(3, "bestaudio/best")
        final_cmd.append(url)  # No cookies added

        try:
            logger.info("Attempting download without cookies...")
            subprocess.run(final_cmd, check=True, timeout=300, capture_output=True, text=True)

            # Find the downloaded file
            for ext in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                candidate = output_path.with_suffix(ext)
                if candidate.exists():
                    logger.info(f"Successfully downloaded audio without cookies: {candidate}")
                    return candidate

            # Check for any audio file in work_dir
            for f in self.work_dir.glob(f"{video_id}_audio.*"):
                if f.suffix in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                    logger.info(f"Successfully downloaded audio without cookies: {f}")
                    return f

            raise WhisperError("Audio download completed but file not found")

        except subprocess.TimeoutExpired:
            logger.error(f"Audio download timeout for video {video_id}")
            raise WhisperError("Audio download timeout")
        except subprocess.CalledProcessError as e:
            error_detail = e.stderr if e.stderr else str(e)

            # Classify the error
            reason, category = self._classify_error(error_detail)

            logger.error(f"Final download attempt failed: {reason} (category: {category})")
            logger.error(f"Error detail: {error_detail[:300]}")

            # Permanent errors
            if category in ["private", "members_only", "age_restricted", "geo_restricted", "live_stream", "unavailable"]:
                raise WhisperError(f"{reason}: {error_detail}") from e

            # If even the no-cookies attempt failed, raise the original error
            if last_error:
                logger.error(f"All download methods failed. Tried cookies, browser cookies, and no cookies.")
                logger.error(f"Last error: {last_error[:200]}")
                logger.error(f"Final error: {error_detail[:200]}")
                raise WhisperError(
                    f"Audio download failed: {last_error} "
                    f"(also tried without cookies: {error_detail})"
                ) from e
            else:
                logger.error(f"Download failed: {error_detail[:200]}")
                raise WhisperError(f"Audio download failed: {error_detail}") from e

    def _transcribe_with_whisper(self, audio_path: str) -> RawTranscript:
        """Transcribe audio file using faster-whisper or OpenVINO."""
        # Check for Intel GPU availability first
        intel_gpu_available = self._check_intel_gpu()

        if intel_gpu_available:
            # Use Optimum Intel OpenVINO for Intel GPU
            try:
                from src.transcription.whisper_openvino_intel import OpenVINOWhisperTranscriber

                # Use medium model on GPU - optimal for Intel Arc A770 capabilities
                model_id = os.environ.get("WHISPER_MODEL", "openai/whisper-medium")

                print(f"   🎮 Using Intel GPU with OpenVINO ({model_id})...")
                transcriber = OpenVINOWhisperTranscriber(
                    model_id=model_id,
                    device="GPU",
                    cache_dir=self.settings.openvino_cache_dir,
                )

                result = transcriber.transcribe(
                    audio_path,
                    language="en",
                    chunk_length=self.settings.whisper_chunk_length,
                )

                transcriber.unload()

                segments = [
                    TranscriptSegment(
                        text=result["text"],
                        start=0.0,
                        duration=0.0,
                    )
                ]

                return RawTranscript(
                    video_id="",
                    segments=segments,
                    source="whisper",
                    language=result.get("language", "en"),
                )
            except Exception as e:
                print(f"   ⚠️  Intel OpenVINO failed ({e})")

        # Try faster-whisper (works on CPU)
        try:
            from faster_whisper import WhisperModel

            # Use tiny for CPU speed, or check for GPU
            import torch

            has_cuda = torch.cuda.is_available()

            model_id = os.environ.get("WHISPER_MODEL", "tiny" if not has_cuda else "base")

            # Use int8 for CPU, float16 for GPU
            compute_type = "int8" if not has_cuda else "float16"

            print(f"   🔄 Loading faster-whisper: {model_id} ({compute_type})")
            model = WhisperModel(
                model_id,
                device="auto",
                compute_type=compute_type,
            )

            print(f"   🎵 Transcribing audio...")
            segs, info = model.transcribe(
                audio_path,
                language="en",
                beam_size=5,
                vad_filter=True,
            )

            transcript_segments = []
            for segment in segs:
                transcript_segments.append(
                    TranscriptSegment(
                        text=segment.text,
                        start=segment.start,
                        duration=getattr(segment, "duration", segment.end - segment.start),
                    )
                )

            del model

            return RawTranscript(
                video_id="",
                segments=transcript_segments,
                source="whisper",
                language="en",
            )

        except Exception as e:
            print(f"   ⚠️  faster-whisper failed ({e})")

            # No more fallbacks available
            raise WhisperError(
                f"All Whisper methods failed: intel_openvino, faster-whisper={e}"
            ) from e

    def _check_intel_gpu(self) -> bool:
        """Check if Intel GPU is available."""
        try:
            import openvino as ov

            core = ov.Core()
            devices = core.available_devices
            return "GPU" in devices
        except Exception:
            return False


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
