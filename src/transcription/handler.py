"""Source-agnostic transcription handler with fallback chain."""

import json
import os
import random
import re
import subprocess
import time
from pathlib import Path
from typing import Literal

import torch
from rich.console import Console

from src.core.config import get_settings_with_yaml
from src.core.exceptions import TranscriptError, WhisperError, YouTubeAPIError
from src.core.schemas import RawTranscript, TranscriptSegment
from src.video.cookie_manager import get_cookie_manager

console = Console()

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

            # Add cookies if available
            if self.cookie_manager.ensure_cookies():
                cookie_args = self.cookie_manager.get_cookie_args()
                if cookie_args:
                    cmd.extend(cookie_args)

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
                # Default: treat as geo-restriction (permanent) to avoid wasting retries
                # Most 403s without explicit temporary indicators are permanent
                return "Access forbidden (likely geo-restricted)", "geo_restricted"

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
        # Apply rate limiting
        self._apply_rate_limiting()

        # PRE-FLIGHT CHECK: Check video availability before attempting download
        console.print("[dim]   Checking video availability...[/dim]")
        is_available, reason, error_category = self._check_video_availability(video_id)

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

        # Define format fallback options
        format_options = [
            "bestaudio/best",  # Primary option
            "bestaudio",       # Fallback without /best restriction
            "m4a/mp3/aac/opus/m4r/flac/wav",  # Specific audio formats
        ]

        # Try different format options with cookies first
        last_error = None
        last_error_category: ErrorCategory = "unknown"

        for format_option in format_options:
            # Build command with current format option
            cmd = [
                "yt-dlp",
                "-f",
                format_option,
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

                # Check if this is a format availability error
                if "Requested format is not available" in error_detail or "format is not available" in error_detail:
                    console.print(f"[dim]   Format '{format_option}' not available, trying next option...[/dim]")
                    continue

                # Classify and handle the error
                reason, category = self._classify_error(error_detail)

                # Permanent errors - don't retry
                if category in ["private", "members_only", "age_restricted", "geo_restricted", "live_stream", "unavailable"]:
                    raise WhisperError(f"{reason}: {error_detail}") from e

                # Temporary 403 - might be retryable with different cookies
                if category == "temporary_block":
                    console.print(f"[dim]   Temporary block detected, will retry with fresh cookies...[/dim]")
                    continue

                # Some other error, don't retry
                raise WhisperError(f"Audio download failed: {error_detail}") from e

            except subprocess.TimeoutExpired:
                raise WhisperError("Audio download timeout")

        # If all format options with cookies failed, try --cookies-from-browser
        console.print("[dim]   Cookie file approach failed, trying --cookies-from-browser...[/dim]")

        # Try --cookies-from-browser with available browsers
        browsers_to_try = self.cookie_manager.get_available_browsers()
        if not browsers_to_try:
            browsers_to_try = ["chrome"]  # Default fallback

        for browser in browsers_to_try:
            try:
                browser_cmd = [
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
                    "--cookies-from-browser",
                    browser,
                ]

                browser_cmd.append(url)
                console.print(f"[dim]   Trying --cookies-from-browser={browser}...[/dim]")

                subprocess.run(browser_cmd, check=True, timeout=300, capture_output=True, text=True)

                # Find the downloaded file
                for ext in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                    candidate = output_path.with_suffix(ext)
                    if candidate.exists():
                        console.print(f"[green]   Success with --cookies-from-browser={browser}![/green]")
                        return candidate

                # Check for any audio file in work_dir
                for f in self.work_dir.glob(f"{video_id}_audio.*"):
                    if f.suffix in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                        console.print(f"[green]   Success with --cookies-from-browser={browser}![/green]")
                        return f

            except subprocess.CalledProcessError as e:
                console.print(f"[dim]   --cookies-from-browser={browser} failed, trying next...[/dim]")
                continue
            except subprocess.TimeoutExpired:
                console.print(f"[dim]   --cookies-from-browser={browser} timed out...[/dim]")
                continue

        # Final attempt without cookies
        console.print("[dim]   --cookies-from-browser failed, trying without cookies...[/dim]")

        final_cmd = [
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

        final_cmd.append(url)  # No cookies added

        try:
            subprocess.run(final_cmd, check=True, timeout=300, capture_output=True, text=True)

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

        except subprocess.TimeoutExpired:
            raise WhisperError("Audio download timeout")
        except subprocess.CalledProcessError as e:
            error_detail = e.stderr if e.stderr else str(e)

            # Classify the error
            reason, category = self._classify_error(error_detail)

            # Permanent errors
            if category in ["private", "members_only", "age_restricted", "geo_restricted", "live_stream", "unavailable"]:
                raise WhisperError(f"{reason}: {error_detail}") from e

            # If even the no-cookies attempt failed, raise the original error
            if last_error:
                raise WhisperError(
                    f"Audio download failed: {last_error} "
                    f"(also tried without cookies: {error_detail})"
                ) from e
            else:
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
