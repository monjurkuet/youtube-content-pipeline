"""Video feed fetcher - fetches videos from RSS feeds and yt-dlp."""

import subprocess
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Literal

import requests
from rich.console import Console

from .schemas import VideoMetadata

console = Console()


def fetch_latest_from_rss(channel_id: str, limit: int = 15) -> list[VideoMetadata]:
    """
    Fetch latest videos from YouTube RSS feed.

    Args:
        channel_id: YouTube channel ID
        limit: Maximum number of videos to fetch (RSS typically returns ~15)

    Returns:
        List of VideoMetadata objects
    """
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    console.print(f"[dim]Fetching RSS feed: {rss_url}[/dim]")

    try:
        response = requests.get(rss_url, timeout=15)
        response.raise_for_status()

        # Parse XML
        root = ET.fromstring(response.content)

        # YouTube uses Atom namespace
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/",
        }

        videos = []
        entries = root.findall("atom:entry", ns)

        for entry in entries[:limit]:
            try:
                # Extract video ID
                video_id_elem = entry.find("yt:videoId", ns)
                video_id = video_id_elem.text if video_id_elem is not None else None

                if not video_id:
                    continue

                # Extract title
                title_elem = entry.find("atom:title", ns)
                title = (
                    str(title_elem.text)
                    if title_elem is not None and title_elem.text is not None
                    else "Unknown"
                )

                # Extract description
                desc_group = entry.find("media:group", ns)
                description = None
                if desc_group is not None:
                    desc_elem = desc_group.find("media:description", ns)
                    description = desc_elem.text if desc_elem is not None else None

                # Extract thumbnail URL
                thumbnail = None
                if desc_group is not None:
                    thumb_elem = desc_group.find("media:thumbnail", ns)
                    if thumb_elem is not None:
                        thumbnail = thumb_elem.get("url")

                # Extract published date
                published_elem = entry.find("atom:published", ns)
                published_at = None
                if published_elem is not None and published_elem.text:
                    try:
                        # Parse ISO 8601 date
                        published_at = datetime.fromisoformat(
                            published_elem.text.replace("Z", "+00:00")
                        )
                        # Make timezone-naive
                        if published_at.tzinfo is not None:
                            published_at = published_at.replace(tzinfo=None)
                    except ValueError:
                        pass

                # Extract author/channel name
                author_elem = entry.find("atom:author/atom:name", ns)
                channel_title = author_elem.text if author_elem is not None else None

                videos.append(
                    VideoMetadata(
                        video_id=video_id,
                        title=title,
                        description=description,
                        thumbnail_url=thumbnail,
                        published_at=published_at,
                        channel_id=channel_id,
                        channel_title=channel_title,
                    )
                )

            except Exception as e:
                console.print(f"[yellow]Warning: Error parsing entry: {e}[/yellow]")
                continue

        console.print(f"[green]✓ Fetched {len(videos)} videos from RSS[/green]")
        return videos

    except requests.RequestException as e:
        console.print(f"[red]Error fetching RSS feed: {e}[/red]")
        return []


def fetch_all_with_ytdlp(
    channel_url: str, progress_callback=None, max_videos: int | None = None
) -> list[VideoMetadata]:
    """
    Fetch ALL videos from channel using yt-dlp WITH full metadata.

    Uses --simulate to get complete metadata (upload_date, duration, etc.)
    without downloading video files. This is slower than --flat-playlist
    but ensures EVERY video has complete metadata.

    Args:
        channel_url: YouTube channel URL (e.g., https://www.youtube.com/@Handle/videos)
        progress_callback: Optional callback for progress updates
        max_videos: Maximum videos to fetch (None = fetch ALL videos)

    Returns:
        List of VideoMetadata objects
    """
    limit_msg = f"Limit: {max_videos} videos" if max_videos else "Fetching ALL videos"
    console.print(f"[dim]Fetching videos with full metadata: {channel_url}[/dim]")
    console.print(f"[dim]   {limit_msg}[/dim]")
    console.print(f"[dim]   This may take a while...[/dim]")

    videos = []
    seen_ids = set()

    try:
        # Use yt-dlp with --simulate to get full metadata without downloading
        # This extracts upload_date, duration, view_count, etc. for EVERY video
        cmd = [
            "yt-dlp",
            "--simulate",  # Metadata only, no download
            "--dump-json",
            "--no-warnings",
            "--quiet",
        ]

        # Only add playlist-end if specified
        if max_videos is not None:
            cmd.append(f"--playlist-end={max_videos}")

        cmd.append(channel_url)

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        line_count = 0
        if process.stdout is None:
            console.print("[red]Error: yt-dlp produced no output[/red]")
            return []

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            line_count += 1
            if progress_callback and line_count % 50 == 0:
                progress_callback(line_count)

            try:
                data = json.loads(line)

                video_id = data.get("id")
                if not video_id or video_id in seen_ids:
                    continue

                seen_ids.add(video_id)

                # Extract metadata
                title = data.get("title", "Unknown")
                duration = data.get("duration")  # in seconds
                view_count = data.get("view_count")

                # Try multiple sources for channel info
                channel_id = data.get("channel_id") or data.get("playlist_channel_id")
                channel = (
                    data.get("channel")
                    or data.get("playlist_channel")
                    or data.get("uploader")
                    or ""
                )

                # Try multiple date sources (yt-dlp provides upload_date)
                upload_date = data.get("upload_date")  # YYYYMMDD format
                timestamp = data.get("timestamp")  # Unix timestamp
                release_date = data.get("release_date")  # YYYYMMDD format

                # Parse upload date from various sources
                published_at = None
                if upload_date:
                    try:
                        published_at = datetime.strptime(upload_date, "%Y%m%d")
                    except ValueError:
                        pass
                elif timestamp:
                    try:
                        published_at = datetime.fromtimestamp(timestamp)
                    except (ValueError, OSError):
                        pass
                elif release_date:
                    try:
                        published_at = datetime.strptime(release_date, "%Y%m%d")
                    except ValueError:
                        pass

                # Ensure datetime is timezone-naive for consistency
                if published_at and published_at.tzinfo is not None:
                    published_at = published_at.replace(tzinfo=None)

                # Extract thumbnail URL (may be a list or string)
                thumbnail = data.get("thumbnail")
                if not thumbnail:
                    thumbnails = data.get("thumbnails", [])
                    if thumbnails and isinstance(thumbnails, list):
                        # Get the highest quality thumbnail
                        thumbnail = thumbnails[-1].get("url") if thumbnails else None

                # Extract description (available in full metadata mode)
                description = data.get("description")

                videos.append(
                    VideoMetadata(
                        video_id=video_id,
                        title=title,
                        description=description,
                        thumbnail_url=thumbnail,
                        duration_seconds=int(duration) if duration else None,
                        view_count=int(view_count) if view_count else None,
                        published_at=published_at,
                        channel_id=channel_id,
                        channel_title=channel,
                    )
                )

            except json.JSONDecodeError as e:
                console.print(f"[yellow]Warning: JSON parse error: {e}[/yellow]")
                continue
            except Exception as e:
                console.print(f"[yellow]Warning: Error processing video: {e}[/yellow]")
                continue

        # Wait for process to complete
        process.wait()

        if process.returncode != 0:
            stderr = process.stderr.read()
            console.print(f"[yellow]yt-dlp completed with warnings: {stderr}[/yellow]")

        # Sort by published date (newest first)
        videos.sort(key=lambda v: v.published_at or datetime.min, reverse=True)

        # Report date coverage
        videos_with_dates = sum(1 for v in videos if v.published_at)
        console.print(
            f"[green]✓ Fetched {len(videos)} videos ({videos_with_dates} with dates)[/green]"
        )
        return videos

    except subprocess.SubprocessError as e:
        console.print(f"[red]Error running yt-dlp: {e}[/red]")
        return []
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        return []


def fetch_videos(
    channel_id: str,
    channel_url: str,
    mode: Literal["recent", "all"] = "recent",
    max_videos: int | None = None,
) -> list[VideoMetadata]:
    """
    Fetch videos from channel using appropriate method.

    Args:
        channel_id: YouTube channel ID
        channel_url: YouTube channel URL
        mode: "recent" for RSS (~15 videos) or "all" for yt-dlp (all videos)
        max_videos: Maximum videos to fetch (None = all)

    Returns:
        List of VideoMetadata objects
    """
    if mode == "recent":
        return fetch_latest_from_rss(channel_id)
    else:
        return fetch_all_with_ytdlp(channel_url, max_videos=max_videos)


def _extract_channel_id_from_url(channel_url: str) -> str | None:
    """Extract channel ID from YouTube channel URL."""
    import re

    # Pattern 1: /channel/XXXXXXXXXX
    match = re.search(r"/channel/([a-zA-Z0-9_-]+)", channel_url)
    if match:
        return match.group(1)

    # Pattern 2: Already a channel ID
    if channel_url.startswith("UC") and len(channel_url) == 24:
        return channel_url

    return None
