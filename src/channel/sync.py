"""Channel sync module - syncs channel videos to database."""

import asyncio
import logging
from datetime import datetime, timezone

from rich.console import Console

from src.core.schemas import SyncResult
from src.database.manager import MongoDBManager
from src.services.video_service import (
    get_failed_videos,
    get_pending_videos,
    get_restricted_videos,
    mark_video_transcription_failed,
    mark_video_transcribed,
    requeue_retryable_failed,
    reset_failed_transcription,
)
from src.video.cookie_manager import get_cookie_manager

from .feed_fetcher import fetch_videos, _get_cookie_manager
from .resolver import resolve_channel_handle
from .schemas import ChannelDocument, VideoMetadataDocument

console = Console()
logger = logging.getLogger(__name__)


async def sync_channel_async(
    handle: str | None = None,
    mode: str = "recent",
    db_manager: MongoDBManager | None = None,
    max_videos: int | None = None,
    incremental: bool = False,
    channel_id: str | None = None,
    channel_url: str | None = None,
) -> SyncResult:
    """Async-native channel sync — the primary implementation.

    This is the canonical implementation used by both CLI and API.
    No thread-pool hacks; all DB operations are async.
    """
    console.print(f"\n[bold blue]Syncing channel: {handle or channel_id or channel_url}[/bold blue]")

    # 1. Resolve channel metadata
    if not (channel_id and channel_url):
        resolved_id, resolved_url = resolve_channel_handle(
            handle or channel_id or channel_url
        )
        channel_id = resolved_id
        channel_url = resolved_url

    # 2. Fetch videos from YouTube
    console.print(f"[dim]Mode: {mode}[/dim]")

    if mode == "recent":
        videos_fetched = fetch_videos(channel_id, channel_url, mode="recent")
    elif incremental:
        videos_fetched = await _fetch_new_videos_only_async(
            channel_id=channel_id,
            channel_url=channel_url,
            db=db_manager,
            max_videos=max_videos,
        )
    else:
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
    async with (db_manager or MongoDBManager()) as db:
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

        new_count = 0
        existing_count = 0
        for video in videos_fetched:
            video_doc = VideoMetadataDocument(
                video_id=video.video_id,
                channel_id=channel_id,
                title=video.title,
                description=video.description,
                thumbnail_url=video.thumbnail_url,
                duration_seconds=video.duration_seconds,
                view_count=video.view_count,
                published_at=video.published_at,
                availability=video.availability,
            )

            existing = await db.video_metadata.find_one({"video_id": video.video_id})
            if existing:
                existing_count += 1
            else:
                await db.save_video_metadata(video_doc)
                new_count += 1

    console.print(f"[green]✓ Sync complete: {new_count} new, {existing_count} existing[/green]\n")

    return SyncResult(
        channel_id=channel_id,
        channel_handle=handle or channel_id,
        channel_title=handle or channel_id,
        videos_fetched=len(videos_fetched),
        videos_new=new_count,
        videos_existing=existing_count,
    )


def sync_channel(
    handle: str | None = None,
    mode: str = "recent",
    db_manager: MongoDBManager | None = None,
    max_videos: int | None = None,
    incremental: bool = False,
    channel_id: str | None = None,
    channel_url: str | None = None,
) -> SyncResult:
    """Synchronous wrapper for CLI usage.

    Calls the async-native sync_channel_async via asyncio.run().
    """
    return asyncio.run(
        sync_channel_async(
            handle=handle,
            mode=mode,
            db_manager=db_manager,
            max_videos=max_videos,
            incremental=incremental,
            channel_id=channel_id,
            channel_url=channel_url,
        )
    )


async def _fetch_new_videos_only_async(
    channel_id: str,
    channel_url: str,
    db: MongoDBManager | None = None,
    max_videos: int | None = None,
):
    """Async helper for incremental sync with yt-dlp."""
    import subprocess
    import json

    from .feed_fetcher import VideoMetadata

    # Use provided db or create a new one
    if db is None:
        async with MongoDBManager() as db:
            return await _fetch_new_videos_only_async(
                channel_id=channel_id,
                channel_url=channel_url,
                db=db,
                max_videos=max_videos,
            )

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

    videos = []
    cookie_manager = _get_cookie_manager()
    cookie_manager.ensure_cookies()
    cookie_args = cookie_manager.get_cookie_args()

    batch_size = 10
    for i in range(0, len(new_ids), batch_size):
        batch = new_ids[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(new_ids) + batch_size - 1) // batch_size

        console.print(f"[dim] Batch {batch_num}/{total_batches}: fetching {len(batch)} videos...[/dim]")

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
                    console.print(f"[dim] Parsed: {data.get('id')}, {data.get('title')[:30] if data.get('title') else 'No title'}[/dim]")

                    published_at = None
                    upload_date = data.get("upload_date")
                    if upload_date:
                        try:
                            from datetime import datetime as dt
                            published_at = dt.strptime(upload_date, "%Y%m%d")
                        except ValueError:
                            pass

                    from src.core.constants import YTDLP_AVAILABILITY_MAP
                    raw_availability = data.get("availability", "unknown") or "unknown"
                    availability = YTDLP_AVAILABILITY_MAP.get(raw_availability, "unknown")

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
                        availability=availability,
                    ))
            except Exception as e:
                console.print(f"[yellow] Warning: failed to fetch {video_id}: {e}[/yellow]")
                continue

    console.print(f"[green]✓ Fetched metadata for {len(videos)} new videos[/green]")
    return videos
