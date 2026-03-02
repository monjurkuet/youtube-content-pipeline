"""Cookie management for YouTube video downloads with auto-extraction and caching."""

import contextlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


class YouTubeCookieManager:
    """
    Manages YouTube cookies for video downloads.

    Features:
    - Auto-extracts cookies from Chrome if not present
    - Caches cookies with configurable expiration (default: 24 hours)
    - Tracks cookie metadata for debugging
    """

    def __init__(
        self,
        cache_duration_hours: int = 24,
        auto_extract: bool = True,
        cookie_file: Path | None = None,
    ):
        """
        Initialize cookie manager.

        Args:
            cache_duration_hours: How long to keep cookies before re-extracting (default: 24)
            auto_extract: Whether to auto-extract if cookies don't exist (default: True)
            cookie_file: Custom cookie file path (default: ~/.config/yt-dlp/cookies.txt)
        """
        self.cache_duration = timedelta(hours=cache_duration_hours)
        self.auto_extract = auto_extract
        self.cookie_file = cookie_file or (Path.home() / ".config/yt-dlp/cookies.txt")
        self.metadata_file = self.cookie_file.parent / ".cookie_metadata.json"

    def ensure_cookies(self) -> bool:
        """
        Ensure valid cookies are available.

        Returns:
            True if cookies are available (existing or newly extracted)
            False if cookies unavailable and auto-extract disabled/failed
        """
        # Check if we have valid cached cookies
        if self._has_valid_cookies():
            metadata = self._load_metadata()
            age_hours = self._get_cookie_age_hours()

            if age_hours < 1:
                console.print("[dim]   Using fresh cookies from cache[/dim]")
            else:
                console.print(f"[dim]   Using cached cookies ({age_hours:.1f}h old)[/dim]")

            if metadata:
                console.print(
                    f"[dim]   Cookies: {metadata.get('youtube_count', 0)} YouTube, "
                    f"{metadata.get('google_count', 0)} Google[/dim]"
                )
            return True

        # Cookies missing or expired - try to extract
        if not self.auto_extract:
            console.print("[yellow]   Auto-extraction disabled, cookies missing/expired[/yellow]")
            return False

        console.print(
            "[yellow]   Cookies missing or expired, auto-extracting from Chrome...[/yellow]"
        )
        logger.info("Cookies missing or expired, attempting auto-extraction from Chrome...")

        try:
            success = self._extract_cookies()
            if success:
                logger.info("Successfully extracted and cached cookies")
                console.print("[green]   ✓ Successfully extracted and cached cookies[/green]")
                return True
            else:
                logger.error("Cookie extraction failed")
                console.print("[red]   ✗ Cookie extraction failed[/red]")
                return False
        except Exception as e:
            logger.error(f"Error during cookie extraction: {e}")
            console.print(f"[red]   ✗ Error during cookie extraction: {e}[/red]")
            return False

    def _has_valid_cookies(self) -> bool:
        """Check if valid non-expired cookies exist."""
        if not self.cookie_file.exists():
            return False

        # Check if cookies have expired based on cache duration
        cookie_age = self._get_cookie_age()
        if cookie_age is None:
            return False

        return cookie_age < self.cache_duration

    def _get_cookie_age(self) -> timedelta | None:
        """Get age of cookie file."""
        if not self.cookie_file.exists():
            return None

        try:
            mtime = self.cookie_file.stat().st_mtime
            file_time = datetime.fromtimestamp(mtime)
            return datetime.now() - file_time
        except Exception:
            return None

    def _get_cookie_age_hours(self) -> float:
        """Get cookie age in hours."""
        age = self._get_cookie_age()
        if age is None:
            return float("inf")
        return age.total_seconds() / 3600

    def _get_chrome_profiles(self) -> list[Path]:
        """
        Get all available Chrome profile directories.

        Returns:
            List of profile directory paths
        """
        import platform

        profiles = []

        try:
            system = platform.system()

            if system == "Linux":
                chrome_config = Path.home() / ".config" / "google-chrome"
            elif system == "Darwin":  # macOS
                chrome_config = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
            elif system == "Windows":
                chrome_config = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
            else:
                logger.warning(f"Unsupported platform: {system}")
                return profiles

            if not chrome_config.exists():
                logger.warning(f"Chrome config directory not found: {chrome_config}")
                return profiles

            # Find all profile directories
            for profile_dir in chrome_config.iterdir():
                if profile_dir.is_dir() and profile_dir.name.startswith("Profile ") or profile_dir.name == "Default":
                    # Check if this profile has a Cookies database
                    cookies_db = profile_dir / "Network" / "Cookies"
                    if not cookies_db.exists():
                        cookies_db = profile_dir / "Cookies"

                    if cookies_db.exists():
                        profiles.append(profile_dir)

        except Exception as e:
            logger.error(f"Error detecting Chrome profiles: {e}")

        logger.info(f"Found {len(profiles)} Chrome profile(s)")
        return profiles

    def _extract_cookies(self) -> bool:
        """Extract cookies from Chrome and save."""
        try:
            # Import here to avoid dependency issues
            from http.cookiejar import MozillaCookieJar

            import browser_cookie3

            # Ensure directory exists
            self.cookie_file.parent.mkdir(parents=True, exist_ok=True)

            # Get available Chrome profiles
            profiles = self._get_chrome_profiles()

            # Try each profile until we find one with auth cookies
            for profile in profiles:
                try:
                    logger.info(f"Trying Chrome profile: {profile.name}")

                    # Extract cookies from this specific profile
                    # Note: profile_dir parameter may not be supported on all platforms
                    try:
                        cj = browser_cookie3.chrome(domain_name=".youtube.com", profile_dir=str(profile))
                        cj_google = browser_cookie3.chrome(domain_name=".google.com", profile_dir=str(profile))
                    except TypeError:
                        # profile_dir not supported on this platform/browser_cookie3 version
                        logger.warning(f"profile_dir parameter not supported, falling back to default Chrome extraction")
                        console.print("[yellow]   Profile selection not supported, using default Chrome profile[/yellow]")
                        break

                    for cookie in cj_google:
                        cj.set_cookie(cookie)

                    # Check for important auth cookies
                    important = ["LOGIN_INFO", "SSID", "APISID", "SAPISID", "HSID"]
                    found_important = [c.name for c in cj if c.name in important]

                    # Count cookies
                    youtube_cookies = [c for c in cj if "youtube" in c.domain]
                    google_cookies = [c for c in cj if "google" in c.domain]

                    logger.info(f"Profile {profile.name}: {len(youtube_cookies)} YouTube cookies, {len(google_cookies)} Google cookies")

                    # Only use this profile if it has auth cookies
                    if found_important:
                        logger.info(f"Using profile '{profile.name}' with auth cookies: {found_important}")

                        # Save in Mozilla format
                        mozilla_jar = MozillaCookieJar(str(self.cookie_file))
                        for cookie in cj:
                            mozilla_jar.set_cookie(cookie)

                        mozilla_jar.save(ignore_discard=True, ignore_expires=True)

                        # Save metadata
                        metadata = {
                            "extracted_at": datetime.now().isoformat(),
                            "youtube_count": len(youtube_cookies),
                            "google_count": len(google_cookies),
                            "auth_cookies": found_important,
                            "has_auth": len(found_important) > 0,
                            "profile_used": profile.name,
                        }
                        self._save_metadata(metadata)

                        logger.info(f"Successfully extracted cookies from profile '{profile.name}'")
                        return True
                    else:
                        logger.info(f"Profile '{profile.name}' has no auth cookies, trying next profile...")
                        continue

                except Exception as e:
                    logger.warning(f"Failed to extract from profile '{profile.name}': {e}")
                    continue

            # No profile with auth cookies found, try default Chrome extraction
            logger.info("No profile with auth cookies found, trying default Chrome extraction...")
            cj = browser_cookie3.chrome(domain_name=".youtube.com")

            # Also get google.com cookies for authentication
            cj_google = browser_cookie3.chrome(domain_name=".google.com")
            for cookie in cj_google:
                cj.set_cookie(cookie)

            # Save in Mozilla format
            mozilla_jar = MozillaCookieJar(str(self.cookie_file))
            for cookie in cj:
                mozilla_jar.set_cookie(cookie)

            mozilla_jar.save(ignore_discard=True, ignore_expires=True)

            # Count and validate cookies
            youtube_cookies = [c for c in cj if "youtube" in c.domain]
            google_cookies = [c for c in cj if "google" in c.domain]

            # Check for important auth cookies
            important = ["LOGIN_INFO", "SSID", "APISID", "SAPISID", "HSID"]
            found_important = [c.name for c in cj if c.name in important]

            # Save metadata
            metadata = {
                "extracted_at": datetime.now().isoformat(),
                "youtube_count": len(youtube_cookies),
                "google_count": len(google_cookies),
                "auth_cookies": found_important,
                "has_auth": len(found_important) > 0,
                "profile_used": "default",
            }
            self._save_metadata(metadata)

            logger.info(f"Extracted {len(youtube_cookies)} YouTube cookies and {len(google_cookies)} Google cookies from default profile")
            logger.info(f"Auth cookies found: {found_important}")

            # Warn if no auth cookies
            if not found_important:
                logger.warning("No authentication cookies found - user may not be logged into YouTube")
                console.print(
                    "[yellow]   ⚠ Warning: No authentication cookies found![/yellow]\n"
                    "[yellow]      Make sure you're logged into YouTube in Chrome.[/yellow]"
                )

            return True

        except ImportError as e:
            console.print(f"[red]   Missing dependency: {e}[/red]")
            console.print("[dim]   Run: uv pip install browser-cookie3[/dim]")
            return False
        except Exception as e:
            console.print(f"[red]   Extraction error: {e}[/red]")
            return False

    def _load_metadata(self) -> dict | None:
        """Load cookie metadata."""
        try:
            if self.metadata_file.exists():
                return json.loads(self.metadata_file.read_text())
        except Exception:
            pass
        return None

    def _save_metadata(self, metadata: dict):
        """Save cookie metadata."""
        with contextlib.suppress(Exception):
            self.metadata_file.write_text(json.dumps(metadata, indent=2))

    def get_cookie_args(self) -> list:
        """
        Get yt-dlp command line arguments for cookies.

        Returns:
            List of command line arguments (empty if no cookies available)
        """
        if self._has_valid_cookies():
            return ["--cookies", str(self.cookie_file)]
        return []

    def get_cookies_from_browser_args(self, browser: str = "chrome") -> list:
        """
        Get yt-dlp command line arguments for --cookies-from-browser.

        Args:
            browser: Browser name (chrome, firefox, edge, brave, opera)

        Returns:
            List of command line arguments for browser cookie extraction
        """
        valid_browsers = ["chrome", "firefox", "edge", "brave", "opera"]
        if browser.lower() not in valid_browsers:
            console.print(f"[yellow]   Invalid browser '{browser}', using chrome[/yellow]")
            browser = "chrome"

        return ["--cookies-from-browser", browser]

    def get_cookies_dict(self) -> dict[str, str] | None:
        """
        Get cookies as a dictionary for use with requests/httpx.

        Returns:
            Dictionary of cookie name -> value, or None if cookies unavailable
        """
        if not self._has_valid_cookies():
            return None

        try:
            from http.cookiejar import MozillaCookieJar

            cookie_jar = MozillaCookieJar(str(self.cookie_file))
            cookie_jar.load(ignore_discard=True, ignore_expires=True)

            # Filter for YouTube and Google cookies
            cookies_dict = {}
            for cookie in cookie_jar:
                if "youtube" in cookie.domain or "google" in cookie.domain:
                    cookies_dict[cookie.name] = cookie.value

            return cookies_dict
        except Exception as e:
            console.print(f"[yellow]   Warning: Failed to load cookies dict: {e}[/yellow]")
            return None

    def get_cookie_string(self) -> str | None:
        """
        Get cookies as a Cookie header string for use with youtube_transcript_api.

        Returns:
            Cookie header string (e.g., "name1=value1; name2=value2"), or None if unavailable
        """
        cookies_dict = self.get_cookies_dict()
        if not cookies_dict:
            return None

        # Format as Cookie header string
        cookie_parts = [f"{name}={value}" for name, value in cookies_dict.items()]
        return "; ".join(cookie_parts)

    def invalidate_cache(self):
        """Force re-extraction on next use by removing cookie file."""
        try:
            if self.cookie_file.exists():
                self.cookie_file.unlink()
            if self.metadata_file.exists():
                self.metadata_file.unlink()
            logger.info("Cookie cache invalidated")
            console.print("[yellow]   Cookie cache invalidated[/yellow]")
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
            console.print(f"[red]   Error invalidating cache: {e}[/red]")

    def get_available_browsers(self) -> list[str]:
        """
        Check which browsers have cookies available.

        Returns:
            List of browser names that have YouTube/Google cookies
        """
        available = []
        browsers_to_check = ["chrome", "firefox", "edge", "brave", "opera"]

        try:
            import browser_cookie3

            for browser in browsers_to_check:
                try:
                    # Try to get cookies from this browser
                    if browser == "chrome":
                        cj = browser_cookie3.chrome(domain_name=".youtube.com")
                    elif browser == "firefox":
                        cj = browser_cookie3.firefox(domain_name=".youtube.com")
                    elif browser == "edge":
                        cj = browser_cookie3.edge(domain_name=".youtube.com")
                    elif browser == "brave":
                        cj = browser_cookie3.brave(domain_name=".youtube.com")
                    elif browser == "opera":
                        cj = browser_cookie3.opera(domain_name=".youtube.com")
                    else:
                        continue

                    # Check if we have any YouTube cookies
                    youtube_cookies = [c for c in cj if "youtube" in c.domain]
                    if youtube_cookies:
                        available.append(browser)
                except Exception:
                    # Browser not installed or no cookies
                    pass
        except ImportError:
            pass

        return available

    def get_status(self) -> dict:
        """Get current cookie status for debugging."""
        status = {
            "cookie_file_exists": self.cookie_file.exists(),
            "metadata_file_exists": self.metadata_file.exists(),
            "auto_extract_enabled": self.auto_extract,
            "cache_duration_hours": self.cache_duration.total_seconds() / 3600,
        }

        if status["cookie_file_exists"]:
            age = self._get_cookie_age()
            status["cookie_age_hours"] = age.total_seconds() / 3600 if age else None
            status["is_fresh"] = self._has_valid_cookies()

        metadata = self._load_metadata()
        if metadata:
            status["last_extracted"] = metadata.get("extracted_at")
            status["youtube_cookies"] = metadata.get("youtube_count", 0)
            status["google_cookies"] = metadata.get("google_count", 0)
            status["has_auth"] = metadata.get("has_auth", False)

        return status


def get_cookie_manager(cache_duration_hours: int = 24) -> YouTubeCookieManager:
    """Get default cookie manager instance."""
    return YouTubeCookieManager(cache_duration_hours=cache_duration_hours)


if __name__ == "__main__":
    # CLI usage for testing/debugging
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        manager = get_cookie_manager()
        status = manager.get_status()
        print("\nYouTube Cookie Status:")
        print("=" * 50)
        for key, value in status.items():
            print(f"  {key}: {value}")
        print()
    elif len(sys.argv) > 1 and sys.argv[1] == "--invalidate":
        manager = get_cookie_manager()
        manager.invalidate_cache()
    else:
        manager = get_cookie_manager()
        success = manager.ensure_cookies()
        sys.exit(0 if success else 1)
