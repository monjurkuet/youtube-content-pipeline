"""Channel resolution strategies for YouTube videos."""

from __future__ import annotations

import json
import logging
import re
import subprocess

from src.core.http_session import get, post
from src.video.cookie_manager import get_cookie_manager

from .models import StrategyResult

logger = logging.getLogger(__name__)


def resolve_channel_handle(handle: str) -> tuple[str, str]:
    """Resolve a YouTube channel handle, ID, or URL to a channel ID and URL.

    This function is intentionally conservative and is shared by the CLI, MCP,
    and sync pipeline.
    """
    if handle.startswith("http"):
        match = re.search(r"@([a-zA-Z0-9_-]+)", handle)
        if match:
            handle = "@" + match.group(1)
        else:
            match = re.search(r"/channel/([a-zA-Z0-9_-]+)", handle)
            if match:
                channel_id = match.group(1)
                return channel_id, f"https://www.youtube.com/channel/{channel_id}"
            raise ValueError(f"Could not extract handle from URL: {handle}")

    if handle.startswith("UC") and len(handle) == 24:
        return handle, f"https://www.youtube.com/channel/{handle}"

    raw_handle = handle.lstrip("@")
    if raw_handle.startswith("UC") and len(raw_handle) == 24:
        return raw_handle, f"https://www.youtube.com/channel/{raw_handle}"

    if not handle.startswith("@"):
        handle = "@" + handle

    channel_id = _try_ytdlp_handle(handle)
    if channel_id:
        return channel_id, f"https://www.youtube.com/channel/{channel_id}"

    custom_url = f"https://www.youtube.com/{handle}/videos"
    channel_id = _extract_channel_id_from_page(custom_url)
    if channel_id:
        return channel_id, f"https://www.youtube.com/channel/{channel_id}"

    raise ValueError(
        f"Could not resolve channel handle: {handle}\n"
        "Please verify the handle is correct and the channel is public."
    )


def resolve_video_channel_via_ytdlp(video_id: str) -> StrategyResult:
    """Resolve channel metadata from yt-dlp JSON output."""
    try:
        # NOTE: Do NOT use cookies for channel metadata extraction.
        # Cookies cause "Requested format is not available" errors because
        # yt-dlp tries to match format preferences. For metadata extraction,
        # we only need the public video info which is available without cookies.
        # Cookies are only needed for age-restricted content download.
        cmd = ["yt-dlp", "--dump-json", "--no-warnings", "--quiet", "--no-check-formats"]
        cmd.append(f"https://www.youtube.com/watch?v={video_id}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Check for JSON output first - yt-dlp may return data even on error
        if result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                # No valid JSON, check stderr
                stderr = result.stderr.strip()
                return StrategyResult(
                    success=False,
                    source="yt-dlp",
                    error_message=stderr or "yt-dlp returned no valid JSON",
                    retryable=_is_transient_error(stderr),
                )
        else:
            # No output at all
            stderr = result.stderr.strip()
            return StrategyResult(
                success=False,
                source="yt-dlp",
                error_message=stderr or "yt-dlp returned no data",
                retryable=_is_transient_error(stderr),
            )
        channel_id = data.get("channel_id") or data.get("playlist_channel_id")
        channel_handle = data.get("channel") or data.get("uploader") or data.get("uploader_id")
        channel_title = data.get("channel") or data.get("uploader") or data.get("uploader_id")

        if channel_id:
            return StrategyResult(
                success=True,
                channel_id=channel_id,
                channel_handle=channel_handle,
                channel_title=channel_title,
                source="yt-dlp",
                metadata={"video_id": data.get("id", video_id)},
            )

        return StrategyResult(
            success=False,
            source="yt-dlp",
            error_message="yt-dlp metadata did not include a channel ID",
            retryable=False,
            metadata={"keys": list(data.keys())[:50]},
        )
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timed out while resolving video %s", video_id)
        return StrategyResult(
            success=False,
            source="yt-dlp",
            error_message="yt-dlp timed out while resolving video channel",
            retryable=True,
        )
    except json.JSONDecodeError as exc:
        logger.warning("yt-dlp returned invalid JSON for %s: %s", video_id, exc)
        return StrategyResult(
            success=False,
            source="yt-dlp",
            error_message=f"yt-dlp returned invalid JSON: {exc}",
            retryable=True,
        )
    except Exception as exc:
        logger.warning("yt-dlp failed for %s: %s", video_id, exc)
        return StrategyResult(
            success=False,
            source="yt-dlp",
            error_message=str(exc),
            retryable=True,
        )


def resolve_video_channel_via_watch_page(video_id: str) -> StrategyResult:
    """Resolve channel metadata from the public YouTube watch page."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        response = get(watch_url, timeout=15, allow_redirects=True)
        if response.status_code >= 400:
            return StrategyResult(
                success=False,
                source="watch_page",
                error_message=f"HTTP {response.status_code} while fetching watch page",
                retryable=response.status_code in {429, 500, 502, 503, 504},
                metadata={"url": watch_url},
            )

        text = response.text
        channel_id = _extract_channel_id_from_watch_page(text)
        channel_title = _extract_channel_title_from_watch_page(text)
        if channel_id:
            return StrategyResult(
                success=True,
                channel_id=channel_id,
                channel_handle=channel_title,
                channel_title=channel_title,
                source="watch_page",
                metadata={"url": str(response.url)},
            )

        return StrategyResult(
            success=False,
            source="watch_page",
            error_message="Could not locate a channel ID on the watch page",
            retryable=True,
            metadata={"url": str(response.url)},
        )
    except Exception as exc:
        logger.warning("Watch page resolution failed for %s: %s", video_id, exc)
        return StrategyResult(
            success=False,
            source="watch_page",
            error_message=str(exc),
            retryable=True,
        )


def resolve_video_channel_via_innertube(video_id: str) -> StrategyResult:
    """Resolve channel metadata via the Innertube player API."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        page = get(watch_url, timeout=15, allow_redirects=True)
        if page.status_code >= 400:
            return StrategyResult(
                success=False,
                source="innertube",
                error_message=f"HTTP {page.status_code} while preparing Innertube request",
                retryable=page.status_code in {429, 500, 502, 503, 504},
            )

        api_key = _extract_innertube_api_key(page.text)
        client_version = _extract_innertube_client_version(page.text)
        if not api_key or not client_version:
            return StrategyResult(
                success=False,
                source="innertube",
                error_message="Could not extract Innertube configuration from watch page",
                retryable=True,
            )

        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": client_version,
                    "hl": "en",
                    "gl": "US",
                }
            },
            "videoId": video_id,
            "playbackContext": {
                "contentPlaybackContext": {"html5Preference": "HTML5_PREF_WANTS"}
            },
            "racyCheckOk": True,
            "contentCheckOk": True,
        }

        headers = {
            "content-type": "application/json",
            "x-youtube-client-name": "1",
            "x-youtube-client-version": client_version,
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        response = post(
            f"https://www.youtube.com/youtubei/v1/player?key={api_key}",
            timeout=15,
            headers=headers,
            json=payload,
        )

        if response.status_code >= 400:
            return StrategyResult(
                success=False,
                source="innertube",
                error_message=f"HTTP {response.status_code} from Innertube player API",
                retryable=response.status_code in {429, 500, 502, 503, 504},
            )

        data = response.json()
        video_details = data.get("videoDetails") or {}
        channel_id = video_details.get("channelId")
        channel_title = video_details.get("author") or video_details.get("channelTitle")
        if channel_id:
            return StrategyResult(
                success=True,
                channel_id=channel_id,
                channel_handle=channel_title,
                channel_title=channel_title,
                source="innertube",
                metadata={"video_id": video_id},
            )

        return StrategyResult(
            success=False,
            source="innertube",
            error_message="Innertube response did not include a channel ID",
            retryable=False,
            metadata={"keys": list(data.keys())[:50]},
        )
    except json.JSONDecodeError as exc:
        logger.warning("Innertube returned invalid JSON for %s: %s", video_id, exc)
        return StrategyResult(
            success=False,
            source="innertube",
            error_message=f"Innertube returned invalid JSON: {exc}",
            retryable=True,
        )
    except Exception as exc:
        logger.warning("Innertube resolution failed for %s: %s", video_id, exc)
        return StrategyResult(
            success=False,
            source="innertube",
            error_message=str(exc),
            retryable=True,
        )


def _extract_channel_title_from_watch_page(text: str) -> str | None:
    """Extract a channel title/handle from a YouTube watch page."""
    for pattern in [
        r'"ownerChannelName"\s*:\s*"([^"]+)"',
        r'"author"\s*:\s*"([^"]+)"',
        r'"channelTitle"\s*:\s*"([^"]+)"',
    ]:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _extract_channel_id_from_watch_page(text: str) -> str | None:
    """Extract a channel ID from a YouTube watch page."""
    for pattern in [
        r'"channelId"\s*:\s*"([a-zA-Z0-9_-]{24})"',
        r'"externalId"\s*:\s*"([a-zA-Z0-9_-]{24})"',
    ]:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _extract_innertube_api_key(text: str) -> str | None:
    """Extract the Innertube API key from a YouTube page."""
    match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match else None


def _extract_innertube_client_version(text: str) -> str | None:
    """Extract the Innertube client version from a YouTube page."""
    match = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match else None


def _is_transient_error(stderr: str) -> bool:
    """Check whether stderr suggests a transient failure."""
    stderr_lower = stderr.lower()
    return any(
        marker in stderr_lower
        for marker in ["timeout", "timed out", "429", "rate limit", "temporarily", "unavailable", "connection", "reset"]
    )


def _try_ytdlp_handle(handle: str) -> str | None:
    """Use yt-dlp to resolve a channel handle to channel ID."""
    channel_url = f"https://www.youtube.com/{handle}/videos"
    cookie_manager = get_cookie_manager(auto_extract=True)
    cookie_manager.ensure_cookies()
    cookie_args = cookie_manager.get_cookie_args()

    try:
        cmd = ["yt-dlp", "--flat-playlist", "--playlist-end", "1", "--dump-json", "--no-warnings", "--quiet"]
        cmd.extend(cookie_args)
        cmd.append(channel_url)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip())
                channel_id = data.get("channel_id") or data.get("playlist_channel_id") or data.get("channel")
                if channel_id:
                    return channel_id
            except json.JSONDecodeError:
                pass

        return _extract_channel_id_from_page(channel_url)
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timed out while resolving handle %s", handle)
        return _extract_channel_id_from_page(channel_url)
    except Exception as exc:
        logger.warning("yt-dlp failed for handle %s: %s", handle, exc)
        return _extract_channel_id_from_page(channel_url)


def _extract_channel_id_from_page(channel_url: str) -> str | None:
    """Extract channel ID from a YouTube channel page."""
    try:
        response = get(channel_url, timeout=10, allow_redirects=True)
        if "channel/" in response.url:
            match = re.search(r"/channel/([a-zA-Z0-9_-]{24})", response.url)
            if match:
                return match.group(1)

        for pattern in [
            r'"externalId"\s*:\s*"([a-zA-Z0-9_-]+)"',
            r'"channelId"\s*:\s*"([a-zA-Z0-9_-]+)"',
        ]:
            match = re.search(pattern, response.text)
            if match:
                return match.group(1)

        match = re.search(r"ytInitialData[^{]*({.+?});", response.text)
        if match:
            try:
                data = json.loads(match.group(1))
                if "header" in data:
                    header = data["header"]
                    if "c4TabbedHeaderRenderer" in header:
                        channel_id = header["c4TabbedHeaderRenderer"].get("channelId")
                        if channel_id:
                            return channel_id
            except (json.JSONDecodeError, KeyError):
                pass

        return None
    except Exception as exc:
        logger.warning("Channel page extraction failed for %s: %s", channel_url, exc)
        return None
