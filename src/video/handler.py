"""Video download and frame extraction utilities."""

import subprocess
from pathlib import Path

from src.core.config import get_settings
from src.core.exceptions import VideoDownloadError
from src.core.schemas import FrameExtractionPlan
from src.video.cookie_manager import get_cookie_manager


class VideoHandler:
    """Handle video download and frame extraction."""

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
        self._video_cache_dir = self.work_dir / ".video_cache"
        self._video_cache_dir.mkdir(exist_ok=True)
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

    def _get_video_cache_path(self, source: str, source_type: str) -> Path:
        """Get path for cached video file."""
        # For YouTube, use video ID; for URLs, hash the URL; for local, use original path
        if source_type == "youtube":
            return self._video_cache_dir / f"youtube_{source}.mp4"
        elif source_type == "url":
            import hashlib

            url_hash = hashlib.md5(source.encode()).hexdigest()[:12]
            return self._video_cache_dir / f"url_{url_hash}.mp4"
        else:  # local
            # For local files, we can't really cache them but we can store a reference
            return Path(source)

    def download_video(self, source: str, source_type: str) -> Path:
        """
        Download video from source.

        Args:
            source: URL or path
            source_type: "youtube", "url", or "local"

        Returns:
            Path to downloaded video
        """
        if source_type == "local":
            return Path(source)

        if source_type == "youtube":
            return self._download_youtube_video(source)

        return self._download_url_video(source)

    def _download_youtube_video(self, video_id: str) -> Path:
        """Download YouTube video with automatic cookie management."""
        output_path = self._get_video_cache_path(video_id, "youtube")

        # Check cache
        if output_path.exists():
            print(f"Using cached video: {output_path}")
            return output_path

        url = f"https://www.youtube.com/watch?v={video_id}"

        # Build command with authentication options
        cmd = [
            "yt-dlp",
            "-f",
            self.settings.video_format,
            "-o",
            str(output_path),
            "--no-playlist",
            "--quiet",
            "--no-warnings",
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
        cmd.extend(
            [
                "--user-agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ]
        )

        cmd.append(url)

        try:
            print("Downloading video from YouTube...")
            result = subprocess.run(cmd, check=True, timeout=300, capture_output=True, text=True)

            if output_path.exists():
                size_mb = output_path.stat().st_size / (1024 * 1024)
                print(f"Downloaded: {size_mb:.1f} MB")
                return output_path
            else:
                raise VideoDownloadError("Download completed but file not found")

        except subprocess.TimeoutExpired:
            raise VideoDownloadError("Download timeout (5 minutes)")
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
                    "  - Using a local video file instead"
                )
            raise VideoDownloadError(f"Download failed: {error_msg}")

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

    def _download_url_video(self, url: str) -> Path:
        """Download video from direct URL."""
        output_path = self._get_video_cache_path(url, "url")

        # Check cache
        if output_path.exists():
            print(f"Using cached video: {output_path}")
            return output_path

        cmd = [
            "yt-dlp",
            "-f",
            self.settings.video_format,
            "-o",
            str(output_path),
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            url,
        ]

        try:
            print("Downloading video from URL...")
            subprocess.run(cmd, check=True, timeout=600, capture_output=True)

            if output_path.exists():
                size_mb = output_path.stat().st_size / (1024 * 1024)
                print(f"Downloaded: {size_mb:.1f} MB")
                return output_path
            else:
                raise VideoDownloadError("Download completed but file not found")
        except subprocess.TimeoutExpired:
            raise VideoDownloadError("Download timeout")
        except subprocess.CalledProcessError as e:
            raise VideoDownloadError(f"Download failed: {e}")

    def extract_frames(
        self,
        video_path: Path,
        extraction_plan: FrameExtractionPlan,
    ) -> list[Path]:
        """
        Extract frames based on LLM's extraction plan.

        Args:
            video_path: Path to video file
            extraction_plan: LLM-generated extraction plan

        Returns:
            List of frame file paths
        """
        frames_dir = self.work_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        # Clean old frames
        for f in frames_dir.glob("*.jpg"):
            f.unlink()

        # Collect timestamps
        timestamps = []

        # Add LLM-suggested key moments
        for moment in extraction_plan.key_moments:
            timestamps.append(moment.time)

        # Add regular coverage intervals
        duration = self._get_video_duration(video_path)
        interval = extraction_plan.coverage_interval_seconds
        for t in range(0, int(duration), interval):
            timestamps.append(t)

        # Remove duplicates and sort
        timestamps = sorted(set(timestamps))

        # Limit to max frames
        max_frames = self.settings.max_frames_to_extract
        if len(timestamps) > max_frames:
            # Sample evenly
            step = len(timestamps) / max_frames
            timestamps = [timestamps[int(i * step)] for i in range(max_frames)]

        print(f"Extracting {len(timestamps)} frames...")

        # Extract frames
        frames = []
        for i, ts in enumerate(timestamps, 1):
            output_file = frames_dir / f"frame_{i:04d}_at_{int(ts):04d}s.jpg"

            cmd = [
                "ffmpeg",
                "-ss",
                str(ts),
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-q:v",
                str(self.settings.video_frame_quality),
                "-y",
                str(output_file),
            ]

            try:
                subprocess.run(cmd, capture_output=True, timeout=30)
                if output_file.exists():
                    frames.append(output_file)
            except subprocess.TimeoutExpired:
                print(f"  Frame {i} timeout, skipping")
                continue

        print(f"Extracted {len(frames)} frames")
        return frames

    def _get_video_duration(self, video_path: Path) -> float:
        """Get video duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception:
            return 0.0
