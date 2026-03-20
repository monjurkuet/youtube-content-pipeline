"""YouTube video downloader using yt-dlp with cookie management and fallbacks."""

import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from rich.console import Console

from src.video.cookie_manager import get_cookie_manager

console = Console()
logger = logging.getLogger(__name__)

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

# JS Runtime paths
BUN_PATH = "/root/.bun/bin/bun"
DENO_PATH = "/root/.deno/bin/deno"


def _find_js_runtime(preferred: str = "bun") -> tuple[str, str] | None:
    """Find available JS runtime."""
    if preferred == "bun":
        if os.path.isfile(BUN_PATH) and os.access(BUN_PATH, os.X_OK):
            return "bun", BUN_PATH
        path = shutil.which("bun")
        if path:
            return "bun", path

    if os.path.isfile(DENO_PATH) and os.access(DENO_PATH, os.X_OK):
        return "deno", DENO_PATH
    path = shutil.which("deno")
    if path:
        return "deno", path

    if preferred == "deno":
        if os.path.isfile(BUN_PATH) and os.access(BUN_PATH, os.X_OK):
            return "bun", BUN_PATH
        path = shutil.which("bun")
        if path:
            return "bun", path

    return None


def _ensure_js_runtime() -> tuple[bool, str]:
    """Check if a JS runtime is available."""
    runtime = _find_js_runtime()
    if runtime:
        return True, f"Found {runtime[0]} at {runtime[1]}"
    return False, "No JS runtime (bun/deno) found. yt-dlp might fail on some videos."


def _get_yt_dlp_base_cmd(output_path: Path) -> list[str]:
    """Build base yt-dlp command with recommended args for audio extraction."""
    # Use system yt-dlp (2026.03.17+) which has better JS challenge support
    yt_dlp_cmd = "/usr/local/bin/yt-dlp"
    if not os.path.isfile(yt_dlp_cmd):
        yt_dlp_cmd = "yt-dlp"  # Fallback to PATH version

    cmd = [
        yt_dlp_cmd,
        "--quiet",
        "--no-warnings",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", str(output_path),
        "--no-playlist",
        # Enable remote components for JS challenge solving (fixes 403 errors)
        "--remote-components", "ejs:github",
    ]

    # Use bun as JS runtime for better YouTube challenge solving
    js_runtime = _find_js_runtime("bun")
    if js_runtime:
        cmd.extend(["--js-runtimes", f"{js_runtime[0]}:{js_runtime[1]}"])

    # Use modern extractor args
    cmd.extend([
        "--extractor-args", "youtube:player-client=web,android",
    ])

    return cmd


class YouTubeDownloader:
    """Handles YouTube video/audio downloads with cookie management and fallbacks."""

    def __init__(self, work_dir: Path, cookie_manager=None):
        self.work_dir = work_dir
        self.cookie_manager = cookie_manager or get_cookie_manager()

    def check_video_availability(self, video_id: str) -> tuple[bool, str, ErrorCategory]:
        """Check if video is available for transcription using yt-dlp.
        
        Note: We don't use cookies here because yt-dlp with cookies causes
        "Requested format is not available" errors with --flat-playlist.
        Video metadata is public and doesn't require authentication.
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
            # Note: No cookies - video metadata is public

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

            if result.returncode != 0:
                error_detail = result.stderr.strip()
                return False, *self.classify_error(error_detail)

            if not result.stdout.strip():
                return False, "No video metadata", "unavailable"

            data = json.loads(result.stdout.strip())

            # Check for live stream
            live_status = data.get("live_status")
            if live_status in ["is_live", "is_upcoming", "post_live"]:
                return False, f"Live stream ({live_status})", "live_stream"

            # Check availability
            availability = data.get("availability")
            if availability == "private":
                return False, "Video is private", "private"
            elif availability == "unavailable":
                return False, "Video unavailable", "unavailable"

            if not data.get("title"):
                return False, "Missing video title", "unavailable"

            return True, "Available", "unknown"

        except subprocess.TimeoutExpired:
            return False, "Timeout checking video", "unknown"
        except Exception as e:
            return False, f"Check failed: {str(e)[:50]}", "unknown"

    def classify_error(self, error_detail: str) -> tuple[str, ErrorCategory]:
        """Classify yt-dlp error into structured categories."""
        error_msg = error_detail.lower()

        if "live event" in error_msg or "upcoming" in error_msg:
            return "Live stream (upcoming)", "live_stream"
        elif "private" in error_msg:
            return "Video is private", "private"
        elif "unavailable" in error_msg or "not available" in error_msg:
            return "Video unavailable", "unavailable"
        elif "members-only" in error_msg or "join" in error_msg:
            return "Members-only video", "members_only"
        elif "age" in error_msg and "restricted" in error_msg:
            return "Age-restricted", "age_restricted"
        elif "geo" in error_msg or "country" in error_msg or "not available in your region" in error_msg:
            return "Geo-restricted", "geo_restricted"
        elif "403" in error_msg and "forbidden" in error_msg:
            return "Access forbidden (likely temporary IP block)", "temporary_block"
        else:
            return f"Video error: {error_detail[:50]}", "unknown"

    def download_audio(self, video_id: str) -> Path:
        """Download audio from YouTube video."""
        # Pre-flight check
        is_available, reason, error_category = self.check_video_availability(video_id)
        if not is_available:
            from src.core.exceptions import WhisperError
            raise WhisperError(f"Pre-flight check failed: {reason}")

        output_path = self.work_dir / f"{video_id}_audio.mp3"
        url = f"https://www.youtube.com/watch?v={video_id}"

        _ensure_js_runtime()

        format_options = ["bestaudio/best", "bestaudio", "m4a/mp3/aac/opus/m4r/flac/wav"]
        consecutive_403_errors = 0

        for format_option in format_options:
            cmd = _get_yt_dlp_base_cmd(output_path)
            cmd.insert(2, "-f")
            cmd.insert(3, format_option)
            cmd.append(url)

            try:
                subprocess.run(cmd, check=True, timeout=300, capture_output=True, text=True)
                return self._find_audio_file(video_id, output_path)

            except subprocess.CalledProcessError as e:
                error_detail = e.stderr if e.stderr else str(e)
                reason, category = self.classify_error(error_detail)

                if category == "temporary_block":
                    consecutive_403_errors += 1
                    timestamp = datetime.now(timezone.utc).isoformat()
                    logger.warning(f"403 error detected at {timestamp} (consecutive: {consecutive_403_errors})")
                    # Retry with cookies for 403 errors
                    self.cookie_manager.invalidate_cache()
                    time.sleep(5)
                    self.cookie_manager.ensure_cookies()
                    cookie_args = self.cookie_manager.get_cookie_args()
                    if cookie_args:
                        cmd_with_cookies = _get_yt_dlp_base_cmd(output_path)
                        cmd_with_cookies.insert(2, "-f")
                        cmd_with_cookies.insert(3, format_option)
                        cmd_with_cookies.extend(cookie_args)
                        cmd_with_cookies.append(url)
                        try:
                            subprocess.run(cmd_with_cookies, check=True, timeout=300, capture_output=True, text=True)
                            return self._find_audio_file(video_id, output_path)
                        except Exception:
                            continue

                if category in ["private", "members_only", "age_restricted", "geo_restricted", "live_stream", "unavailable"]:
                    from src.core.exceptions import WhisperError
                    raise WhisperError(f"Permanent error: {error_detail}")

                if "Requested format is not available" in error_detail:
                    continue

        # Last try without cookies
        final_cmd = _get_yt_dlp_base_cmd(output_path)
        final_cmd.insert(2, "-f")
        final_cmd.insert(3, "bestaudio/best")
        final_cmd.append(url)
        try:
            subprocess.run(final_cmd, check=True, timeout=300, capture_output=True, text=True)
            return self._find_audio_file(video_id, output_path)
        except Exception as e:
            from src.core.exceptions import WhisperError
            raise WhisperError(f"Audio download failed after all attempts: {e}")

    def _find_audio_file(self, video_id: str, base_path: Path) -> Path:
        """Find the actually downloaded file."""
        for ext in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
            candidate = base_path.with_suffix(ext)
            if candidate.exists():
                return candidate
        for f in self.work_dir.glob(f"{video_id}_audio.*"):
            if f.suffix in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                return f
        from src.core.exceptions import WhisperError
        raise WhisperError(f"Download completed but file not found for {video_id}")
