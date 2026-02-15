"""Audio download utilities for transcription pipeline."""

import subprocess
from pathlib import Path

from src.core.config import get_settings
from src.core.exceptions import VideoDownloadError
from src.video.cookie_manager import get_cookie_manager


class AudioHandler:
    """Handle audio download for transcription."""

    def __init__(
        self,
        work_dir: Path | None = None,
        use_browser_cookies: bool = True,
        auto_extract_cookies: bool = True,
        cookie_cache_hours: int = 24,
    ):
        self.settings = get_settings()
        self.work_dir = work_dir or self.settings.work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._audio_cache_dir = self.work_dir / ".audio_cache"
        self._audio_cache_dir.mkdir(exist_ok=True)
        self.use_browser_cookies = use_browser_cookies
        self._js_runtime = self._detect_js_runtime()

        # Initialize cookie manager for YouTube downloads
        self._cookie_manager = get_cookie_manager(cache_duration_hours=cookie_cache_hours)
        self._auto_extract_cookies = auto_extract_cookies

    def _detect_js_runtime(self) -> str | None:
        """Detect available JavaScript runtime for yt-dlp."""
        # Check for Deno
        try:
            result = subprocess.run(["deno", "--version"], capture_output=True, timeout=5)
            if result.returncode == 0:
                return "deno"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Check for Node.js
        try:
            result = subprocess.run(["node", "--version"], capture_output=True, timeout=5)
            if result.returncode == 0:
                return "node"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    def _get_audio_cache_path(self, source: str, source_type: str) -> Path:
        """Get path for cached audio file."""
        # For YouTube, use video ID; for URLs, hash the URL; for local, use original path
        if source_type == "youtube":
            return self._audio_cache_dir / f"youtube_{source}.{self.settings.audio_format}"
        elif source_type == "url":
            import hashlib

            url_hash = hashlib.md5(source.encode()).hexdigest()[:12]
            return self._audio_cache_dir / f"url_{url_hash}.{self.settings.audio_format}"
        else:  # local
            # For local files, we can't really cache them but we can store a reference
            return Path(source)

    def download_audio(self, source: str, source_type: str) -> Path:
        """
        Download audio from source.

        Args:
            source: URL or path
            source_type: "youtube", "url", or "local"

        Returns:
            Path to downloaded audio file
        """
        if source_type == "local":
            return Path(source)

        if source_type == "youtube":
            return self._download_youtube_audio(source)

        return self._download_url_audio(source)

    def _download_youtube_audio(self, video_id: str) -> Path:
        """Download YouTube audio with automatic cookie management."""
        output_path = self._get_audio_cache_path(video_id, "youtube")

        # Check cache
        if output_path.exists():
            print(f"Using cached audio: {output_path}")
            return output_path

        url = f"https://www.youtube.com/watch?v={video_id}"

        # Build command with authentication options
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
            str(output_path),
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--js-runtimes",
            "node",
        ]

        # Add JS runtime if available (required for challenge solving)
        if self._js_runtime:
            cmd.extend(["--js-runtimes", self._js_runtime])
            cmd.append("--remote-components")
            cmd.append("ejs:github")

        # Ensure cookies are available (auto-extract if needed)
        cookies_available = False
        if self._auto_extract_cookies:
            cookies_available = self._cookie_manager.ensure_cookies()

        if cookies_available:
            # Use managed cookies
            cookie_args = self._cookie_manager.get_cookie_args()
            if cookie_args:
                cmd.extend(cookie_args)
        elif self.use_browser_cookies:
            # Fallback to direct browser extraction
            browser = self._detect_available_browser()
            if browser:
                cmd.extend(["--cookies-from-browser", browser])
                print(f"Using browser cookies: {browser}")

        # Add user agent to appear more like a real browser
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        cmd.extend(["--user-agent", user_agent])

        cmd.append(url)

        try:
            print("Downloading audio from YouTube...")
            subprocess.run(cmd, check=True, timeout=300, capture_output=True, text=True)

            # Find the downloaded file (may have different extension)
            for ext in [f".{self.settings.audio_format}", ".m4a", ".mp3", ".wav"]:
                candidate = output_path.with_suffix(ext)
                if candidate.exists():
                    size_mb = candidate.stat().st_size / (1024 * 1024)
                    print(f"Downloaded: {size_mb:.1f} MB")
                    return candidate

            raise VideoDownloadError("Download completed but file not found")

        except subprocess.TimeoutExpired as e:
            raise VideoDownloadError("Download timeout (5 minutes)") from e
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            if "403" in error_msg:
                raise VideoDownloadError(
                    "YouTube blocked the download (HTTP 403). "
                    "This usually means:\n"
                    "  1. YouTube requires authentication (PO token)\n"
                    "  2. The IP address may be rate-limited\n"
                    "  3. The video may be age-restricted or private\n"
                    "Try:\n"
                    "  - Logging into YouTube in Chrome\n"
                    "  - Manually running: uv run python -m src.video.cookie_manager\n"
                    "  - Using a local audio file instead"
                ) from e
            raise VideoDownloadError(f"Download failed: {error_msg}") from e

    def _detect_available_browser(self) -> str | None:
        """Detect Chrome/Chromium for fallback cookie extraction."""
        browsers = ["chrome", "chromium"]

        for browser in browsers:
            try:
                # Check if browser cookies exist
                if browser == "chrome":
                    cookie_path = Path.home() / ".config/google-chrome/Default/Cookies"
                    if cookie_path.exists():
                        return "chrome"
                elif browser == "chromium":
                    cookie_path = Path.home() / ".config/chromium/Default/Cookies"
                    if cookie_path.exists():
                        return "chromium"
            except Exception:
                continue

        return None

    def _download_url_audio(self, url: str) -> Path:
        """Download audio from direct URL."""
        output_path = self._get_audio_cache_path(url, "url")

        # Check cache
        if output_path.exists():
            print(f"Using cached audio: {output_path}")
            return output_path

        cmd = [
            "yt-dlp",
            "-f",
            "bestaudio",
            "--extract-audio",
            "--audio-format",
            self.settings.audio_format,
            "--audio-quality",
            self.settings.audio_bitrate,
            "-o",
            str(output_path),
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            url,
        ]

        try:
            print("Downloading audio from URL...")
            subprocess.run(cmd, check=True, timeout=600, capture_output=True)

            # Find the downloaded file
            for ext in [f".{self.settings.audio_format}", ".m4a", ".mp3", ".wav"]:
                candidate = output_path.with_suffix(ext)
                if candidate.exists():
                    size_mb = candidate.stat().st_size / (1024 * 1024)
                    print(f"Downloaded: {size_mb:.1f} MB")
                    return candidate

            raise VideoDownloadError("Download completed but file not found")
        except subprocess.TimeoutExpired as e:
            raise VideoDownloadError("Download timeout") from e
        except subprocess.CalledProcessError as e:
            raise VideoDownloadError(f"Download failed: {e}") from e


# Backwards compatibility alias
VideoHandler = AudioHandler
