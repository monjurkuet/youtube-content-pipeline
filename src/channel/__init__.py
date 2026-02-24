"""Channel tracking module for YouTube channels."""

from .feed_fetcher import fetch_all_with_ytdlp, fetch_latest_from_rss, fetch_videos
from .resolver import resolve_channel_handle
from .schemas import ChannelDocument, SyncResult, VideoMetadata, VideoMetadataDocument
from .sync import get_pending_videos, mark_video_transcribed, sync_channel

__all__ = [
    # Resolver
    "resolve_channel_handle",
    # Feed fetcher
    "fetch_latest_from_rss",
    "fetch_all_with_ytdlp",
    "fetch_videos",
    # Schemas
    "ChannelDocument",
    "VideoMetadata",
    "VideoMetadataDocument",
    "SyncResult",
    # Sync
    "sync_channel",
    "get_pending_videos",
    "mark_video_transcribed",
]
