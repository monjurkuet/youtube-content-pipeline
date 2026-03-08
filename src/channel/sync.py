"""Channel sync module - syncs channel videos to database."""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from src.core.config import get_settings_with_yaml
from src.core.schemas import SyncResult
from src.database.manager import MongoDBManager
from src.video.cookie_manager import get_cookie_manager, YouTubeCookieManager

from .feed_fetcher import fetch_videos, _get_cookie_manager
from .resolver import resolve_channel_handle
from .schemas import ChannelDocument, VideoMetadataDocument

# Re-export for compatibility
from src.services.video_service import (
    get_pending_videos,
    get_failed_videos,
    reset_failed_transcription,
    mark_video_transcribed,
)

console = Console()
logger = logging.getLogger(__name__)

# Persistent event loop for sync_all operations
_sync_loop: asyncio.AbstractEventLoop | None = None


def _get_event_loop() -> asyncio.AbstractEventLoop:
    """Get or create a persistent event loop for sync operations."""
    global _sync_loop
    if _sync_loop is None or _sync_loop.is_closed():
        _sync_loop = asyncio.new_event_loop()
    return _sync_loop


def _run_async(coro):
    """Run an async coroutine using the persistent event loop."""
    loop = _get_event_loop()
    return loop.run_until_complete(coro)


def sync_channel(
    handle: str | None = None,
    mode: str = "recent",
    db_manager: MongoDBManager | None = None,
    max_videos: int | None = None,
    incremental: bool = False,
    channel_id: str | None = None,
    channel_url: str | None = None,
) -> SyncResult:
    """
    Sync channel videos to database.

    Args:
        handle: Channel handle (e.g., "@ChartChampions")
        mode: "recent" (RSS) or "all" (yt-dlp)
        db_manager: MongoDBManager instance
        max_videos: Maximum videos to fetch
        incremental: Whether to only fetch new videos
        channel_id: Channel ID (alternative to handle)
        channel_url: Channel URL (alternative to handle)
    """
    console.print(f"\n[bold blue]Syncing channel: {handle or channel_id or channel_url}[/bold blue]")

    # 1. Resolve channel metadata
    if not (channel_id and channel_url):
        # Need to resolve handle or partial info
        resolved_id, resolved_url = resolve_channel_handle(
            handle or channel_id or channel_url
        )
        channel_id = resolved_id
        channel_url = resolved_url

    # 2. Fetch videos from YouTube
    console.print(f"[dim]Mode: {mode}[/dim]")
    
    # Use feed_fetcher for recent or yt-dlp for all
    if mode == "recent":
        # RSS feed limit is ~15
        videos_fetched = fetch_videos(channel_id, channel_url, mode="recent")
    elif incremental:
        # Incremental sync - only new videos
        async def _fetch_all():
            async with (db_manager or MongoDBManager()) as db:
                return await _fetch_new_videos_only_async(
                    channel_id=channel_id,
                    channel_url=channel_url,
                    db=db,
                    max_videos=max_videos
                )
        videos_fetched = _run_async(_fetch_all())
    else:
        # Full sync - all videos using feed_fetcher
        videos_fetched = fetch_videos(channel_id, channel_url, mode="all", max_videos=max_videos)

    if not videos_fetched:
        console.print("[yellow]! No videos found[/yellow]")
        return SyncResult(
            channel_id=channel_id,
            channel_handle=handle or channel_id,
            channel_title=handle or channel_id,
            videos_fetched=0,
            videos_new=0,
            videos_existing=0,
        )

    # 3. Save to database
    async def _save():
        async with (db_manager or MongoDBManager()) as db:
            # Save channel info
            channel_doc = ChannelDocument(
                channel_id=channel_id,
                channel_handle=handle.lstrip("@") if handle else channel_id,
                channel_title=videos_fetched[0].channel_title or handle or channel_id,
                channel_url=channel_url,
                last_synced=datetime.now(timezone.utc),
                total_videos_tracked=len(videos_fetched),
                sync_mode=mode,
            )
            await db.save_channel(channel_doc)

            # Save videos
            new_count = 0
            existing_count = 0
            for video in videos_fetched:
                # Basic check - normally we would check before fetching full metadata
                # but for RSS it doesn't matter much.
                video_doc = VideoMetadataDocument(
                    video_id=video.video_id,
                    channel_id=channel_id,
                    title=video.title,
                    description=video.description,
                    thumbnail_url=video.thumbnail_url,
                    duration_seconds=video.duration_seconds,
                    view_count=video.view_count,
                    published_at=video.published_at,
                )
                
                # Check if exists
                existing = await db.video_metadata.find_one({"video_id": video.video_id})
                if existing:
                    existing_count += 1
                else:
                    await db.save_video_metadata(video_doc)
                    new_count += 1
            
            return new_count, existing_count

    new_count, exist_count = _run_async(_save())

    console.print(f"[green]✓ Sync complete: {new_count} new, {exist_count} existing[/green]\n")

    return SyncResult(
        channel_id=channel_id,
        channel_handle=handle or channel_id,
        channel_title=handle or channel_id,
        videos_fetched=len(videos_fetched),
        videos_new=new_count,
        videos_existing=exist_count,
    )


async def _fetch_new_videos_only_async(
    channel_id: str,
    channel_url: str,
    db,
    max_videos: int | None = None,
):
    """Async helper for full sync with yt-dlp."""
    # This logic is quite complex, it uses subprocess to call yt-dlp
    # For now let's keep the existing logic but refactored for async
    from .feed_fetcher import VideoMetadata
    import subprocess
    import json

    # 1. Get existing IDs from DB
    cursor = db.video_metadata.find({"channel_id": channel_id}, {"video_id": 1})
    docs = await cursor.to_list(length=None)
    existing_ids = {doc["video_id"] for doc in docs}

    # 2. Get all IDs from channel using yt-dlp --flat-playlist
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--get-id",
        "--no-warnings",
        "--quiet",
        channel_url,
    ]
    
    # Add cookies if available
    cookie_manager = get_cookie_manager()
    cookie_manager.ensure_cookies()
    cmd.extend(cookie_manager.get_cookie_args())

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        all_ids = stdout.decode().strip().splitlines()
    except Exception as e:
        logger.error(f"yt-dlp failed to fetch IDs: {e}")
        return []

    if max_videos:
        all_ids = all_ids[:max_videos]

    # 3. Filter for NEW IDs
    new_ids = [vid for vid in all_ids if vid not in existing_ids]
    if not new_ids:
        return []

    # 4. Fetch full metadata for NEW IDs
    console.print(f"[dim]Fetching metadata for {len(new_ids)} new videos...[/dim]")
    
    import subprocess
    import json
    
    videos = []
    # Get cookie args
    cookie_manager = _get_cookie_manager()
    cookie_manager.ensure_cookies()
    cookie_args = cookie_manager.get_cookie_args()
    
    # Process in batches to show progress
    batch_size = 10
    for i in range(0, len(new_ids), batch_size):
        batch = new_ids[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(new_ids) + batch_size - 1) // batch_size
        
        console.print(f"[dim]   Batch {batch_num}/{total_batches}: fetching {len(batch)} videos...[/dim]")
        
        for video_id in batch:
            cmd = [
                "yt-dlp",
                "--simulate",
                "--dump-json",
                "--no-warnings",
            ]
            cmd.extend(cookie_args)
            cmd.append(f"https://www.youtube.com/watch?v={video_id}")
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout.strip())
                    console.print(f"[dim]      Parsed: {data.get('id')}, {data.get('title')[:30] if data.get('title') else 'No title'}[/dim]")
                    
                    # Parse upload date
                    published_at = None
                    upload_date = data.get("upload_date")
                    if upload_date:
                        try:
                            from datetime import datetime
                            published_at = datetime.strptime(upload_date, "%Y%m%d")
                        except ValueError:
                            pass
                    
                    videos.append(VideoMetadata(
                        video_id=data.get("id", ""),
                        title=data.get("title", ""),
                        description=data.get("description", ""),
                        channel_id=channel_id,
                        channel_title=data.get("channel", ""),
                        thumbnail_url=data.get("thumbnail", ""),
                        duration_seconds=data.get("duration"),
                        view_count=data.get("view_count"),
                        published_at=published_at,
                    ))
            except Exception as e:
                console.print(f"[yellow]   Warning: failed to fetch {video_id}: {e}[/yellow]")
                continue
    
    console.print(f"[green]✓ Fetched metadata for {len(videos)} new videos[/green]")
    return videos
