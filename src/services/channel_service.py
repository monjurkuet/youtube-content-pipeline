"""Channel tracking and management services."""

import logging
from typing import Any, Literal

from src.channel.resolver import resolve_channel_from_video, resolve_channel_handle
from src.channel.schemas import ChannelDocument
from src.channel.sync import sync_channel_async
from src.core.utils import extract_video_id
from src.database.manager import MongoDBManager

logger = logging.getLogger(__name__)


async def add_channels_from_videos_service(
    video_urls: list[str],
    db_manager: MongoDBManager,
    auto_sync: bool = True,
    sync_mode: Literal["recent", "all"] = "recent",
    sync_max_videos_per_channel: int | None = None,
) -> dict[str, Any]:
    """
    Add YouTube channels from a list of video URLs.

    Args:
        video_urls: List of YouTube video URLs
        db_manager: MongoDB manager instance
        auto_sync: Whether to automatically sync videos after adding a channel
        sync_mode: Mode for syncing videos ("recent" or "all")
        sync_max_videos_per_channel: Maximum videos to fetch per channel when
            running full channel syncs.

    Returns:
        Dictionary with results for each URL and summary stats
    """
    processed_channels: set[str] = set()
    results = {
        "added": [],
        "skipped_duplicate": [],
        "skipped_existing": [],
        "failed": [],
    }

    for url in video_urls:
        video_id = extract_video_id(url)
        if not video_id:
            results["failed"].append({"url": url, "video_id": None, "error": "Invalid YouTube URL"})
            continue

        resolution = resolve_channel_from_video(video_id)
        if not resolution.success or not resolution.channel_id:
            results["failed"].append(
                {
                    "url": url,
                    "video_id": video_id,
                    "error": resolution.error_message or "Could not fetch channel info",
                    "error_stage": resolution.error_stage or resolution.source or "resolver",
                    "retryable": resolution.retryable,
                    "resolution_source": resolution.source,
                }
            )
            continue

        channel_id = resolution.channel_id
        channel_handle = resolution.channel_handle or resolution.channel_title or ""

        # Check if already processed in this batch
        if channel_id in processed_channels:
            results["skipped_duplicate"].append(
                {
                    "url": url,
                    "channel_id": channel_id,
                    "channel_handle": channel_handle,
                }
            )
            continue

        # Check if channel already exists in database
        existing_channel = await db_manager.get_channel(channel_id)
        if existing_channel:
            results["skipped_existing"].append(
                {
                    "url": url,
                    "channel_id": channel_id,
                    "channel_handle": existing_channel.get("channel_handle"),
                }
            )
            processed_channels.add(channel_id)
            continue

        try:
            # Resolve channel handle to get proper channel URL
            normalized_handle = "".join(c for c in channel_handle if c.isalnum())[:30]
            
            # Using resolved channel URL is better for display
            try:
                # Try to get more accurate info via resolver
                _, channel_url = resolve_channel_handle(channel_id)
            except Exception:
                # Fallback to direct URL if resolver fails
                channel_url = f"https://www.youtube.com/channel/{channel_id}"

            # Save channel to database
            channel_doc = ChannelDocument(
                channel_id=channel_id,
                channel_handle=normalized_handle,
                channel_title=channel_handle,
                channel_url=channel_url,
                sync_mode=sync_mode,
            )

            doc_id = await db_manager.save_channel(channel_doc)

            result_entry: dict[str, Any] = {
                "url": url,
                "channel_id": channel_id,
                "channel_handle": normalized_handle,
                "channel_title": channel_doc.channel_title,
                "database_id": str(doc_id),
                "resolution_source": resolution.source,
            }

            # Auto-sync if requested
            if auto_sync:
                try:
                    sync_result = await sync_channel_async(
                        channel_id=channel_id,
                        channel_url=channel_url,
                        mode=sync_mode,
                        db_manager=db_manager,
                        max_videos=sync_max_videos_per_channel,
                    )
                    result_entry["sync_videos_fetched"] = sync_result.videos_fetched
                    result_entry["sync_videos_new"] = sync_result.videos_new
                except Exception as sync_error:
                    logger.error("Auto-sync failed for %s: %s", channel_id, sync_error)
                    result_entry["sync_error"] = str(sync_error)

            results["added"].append(result_entry)
            processed_channels.add(channel_id)

        except Exception as e:
            logger.error("Failed to process URL %s: %s", url, e)
            results["failed"].append({"url": url, "video_id": video_id, "error": str(e)})

    return {
        "success": True,
        "added": results["added"],
        "skipped_duplicate": results["skipped_duplicate"],
        "skipped_existing": results["skipped_existing"],
        "failed": results["failed"],
        "total_processed": len(video_urls),
        "total_added": len(results["added"]),
        "total_skipped": len(results["skipped_duplicate"]) + len(results["skipped_existing"]),
        "total_failed": len(results["failed"]),
    }
