"""Channel handle resolver - converts @handle to channel ID."""

import json
import re

from rich.console import Console

from src.core.http_session import get

console = Console()


def resolve_channel_handle(handle: str) -> tuple[str, str]:
    """
    Resolve YouTube channel handle to channel ID and URL.

    Args:
        handle: Channel handle (e.g., "@ChartChampions" or "https://www.youtube.com/@ChartChampions")

    Returns:
        Tuple of (channel_id, channel_url)

    Raises:
        ValueError: If channel cannot be resolved
    """
    # Extract handle from URL if full URL provided
    if handle.startswith("http"):
        match = re.search(r"@([a-zA-Z0-9_-]+)", handle)
        if match:
            handle = "@" + match.group(1)
        else:
            # Try to extract channel ID from URL
            match = re.search(r"/channel/([a-zA-Z0-9_-]+)", handle)
            if match:
                channel_id = match.group(1)
                channel_url = f"https://www.youtube.com/channel/{channel_id}"
                return channel_id, channel_url
            raise ValueError(f"Could not extract handle from URL: {handle}")

    # Ensure handle starts with @
    if not handle.startswith("@"):
        handle = "@" + handle

    console.print(f"[dim]Resolving channel handle: {handle}...[/dim]")

    # Method 1: Try RSS feed (fastest, most reliable)
    channel_id = _try_rss_feed(handle)
    if channel_id:
        channel_url = f"https://www.youtube.com/channel/{channel_id}"
        console.print(f"[green]✓ Resolved to channel ID: {channel_id}[/green]")
        return channel_id, channel_url

    # Method 2: Try yt-dlp
    channel_id = _try_ytdlp(handle)
    if channel_id:
        channel_url = f"https://www.youtube.com/channel/{channel_id}"
        console.print(f"[green]✓ Resolved to channel ID: {channel_id}[/green]")
        return channel_id, channel_url

    raise ValueError(
        f"Could not resolve channel handle: {handle}\n"
        "Please verify the handle is correct and the channel is public."
    )


def _try_rss_feed(handle: str) -> str | None:
    """Try to get channel ID from RSS feed."""
    # First, we need to get the channel ID by trying common patterns
    # RSS feed requires channel_id, so we'll try yt-dlp first to get it
    return None  # RSS needs channel_id, can't use handle directly


def _try_ytdlp(handle: str) -> str | None:
    """Use yt-dlp to resolve channel handle to channel ID."""
    import json
    import subprocess

    from src.video.cookie_manager import YouTubeCookieManager

    channel_url = f"https://www.youtube.com/{handle}/videos"

    # Ensure cookies are available
    cookie_manager = YouTubeCookieManager(auto_extract=True)
    cookie_manager.ensure_cookies()
    cookie_args = cookie_manager.get_cookie_args()

    try:
        # Use yt-dlp to get channel info
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--playlist-end",
            "1",  # Just get first video to extract channel info
            "--dump-json",
            "--no-warnings",
            "--quiet",
        ]
        cmd.extend(cookie_args)  # Add cookies if available
        cmd.append(channel_url)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and result.stdout.strip():
            # Parse JSON output
            try:
                data = json.loads(result.stdout.strip())
                channel_id = data.get("channel_id")
                if channel_id:
                    return channel_id
            except json.JSONDecodeError:
                pass

        # Fallback: try to extract from stderr or use different approach
        # Try fetching the channel page and extracting channel ID
        return _extract_channel_id_from_page(channel_url)

    except subprocess.TimeoutExpired:
        console.print("[yellow]yt-dlp timeout, trying alternative method...[/yellow]")
        return _extract_channel_id_from_page(channel_url)
    except Exception as e:
        console.print(f"[yellow]yt-dlp failed: {e}, trying alternative...[/yellow]")
        return _extract_channel_id_from_page(channel_url)


def _extract_channel_id_from_page(channel_url: str) -> str | None:
    """Extract channel ID from YouTube channel page."""
    try:
        # Try RSS feed with common channel ID patterns
        # First, get the actual channel URL by following redirects
        response = get(channel_url, timeout=10, allow_redirects=True)

        # Look for channel ID in the response
        # Pattern 1: channel_id in URL redirects
        if "channel/" in response.url:
            match = re.search(r"/channel/([a-zA-Z0-9_-]{24})", response.url)
            if match:
                return match.group(1)

        # Pattern 2: externalId in page content
        match = re.search(r'"externalId"\s*:\s*"([a-zA-Z0-9_-]+)"', response.text)
        if match:
            return match.group(1)

        # Pattern 3: channel_id in meta tags
        match = re.search(r'"channelId"\s*:\s*"([a-zA-Z0-9_-]+)"', response.text)
        if match:
            return match.group(1)

        # Pattern 4: Try to find in YouTube's JSON data
        match = re.search(r"ytInitialData[^{]*({.+?});", response.text)
        if match:
            try:
                data = json.loads(match.group(1))
                # Navigate to find channel ID
                if "header" in data:
                    header = data["header"]
                    if "c4TabbedHeaderRenderer" in header:
                        channel_id = header["c4TabbedHeaderRenderer"].get("channelId")
                        if channel_id:
                            return channel_id
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    except Exception as e:
        console.print(f"[yellow]Page extraction failed: {e}[/yellow]")
        return None


def get_channel_id_from_rss(channel_id: str) -> str | None:
    """
    Verify channel ID by fetching RSS feed.

    Args:
        channel_id: YouTube channel ID

    Returns:
        Verified channel ID or None if invalid
    """
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    try:
        response = get(rss_url, timeout=10)
        if response.status_code == 200:
            # Parse XML to verify and get canonical channel ID
            import xml.etree.ElementTree as ET

            root = ET.fromstring(response.content)

            # YouTube uses Atom namespace
            ns = {"yt": "http://www.youtube.com/xml/schemas/2015"}
            channel_elem = root.find("yt:channelId", ns)
            if channel_elem is not None:
                return channel_elem.text

            # Fallback to the ID we used
            return channel_id
        return None
    except Exception:
        return None
