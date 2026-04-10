"""High-level channel resolver orchestration."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from .models import StrategyResult, VideoChannelResolution
from .strategies import (
    resolve_channel_handle,
    resolve_video_channel_via_innertube,
    resolve_video_channel_via_watch_page,
    resolve_video_channel_via_ytdlp,
)

logger = logging.getLogger(__name__)

__all__ = ["resolve_channel_handle", "resolve_channel_from_video"]


def resolve_channel_from_video(video_id: str) -> VideoChannelResolution:
    """Resolve a YouTube video ID to channel metadata using multiple strategies."""
    if not video_id or not re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
        return VideoChannelResolution(
            success=False,
            source="validation",
            error_stage="video_id_validation",
            error_message=f"Invalid YouTube video ID: {video_id!r}",
            retryable=False,
        )

    strategies: list[tuple[str, Callable[[str], StrategyResult]]] = [
        ("yt-dlp", resolve_video_channel_via_ytdlp),
        ("watch_page", resolve_video_channel_via_watch_page),
        ("innertube", resolve_video_channel_via_innertube),
    ]

    failures: list[dict[str, object]] = []
    for source_name, strategy in strategies:
        try:
            result = strategy(video_id)
        except Exception as exc:  # pragma: no cover - defensive guard around external calls
            failures.append(
                {
                    "source": source_name,
                    "error_stage": source_name,
                    "error_message": str(exc),
                    "retryable": True,
                }
            )
            logger.warning("Video resolution strategy %s failed: %s", source_name, exc)
            continue

        if result.success and result.channel_id:
            return VideoChannelResolution(
                success=True,
                channel_id=result.channel_id,
                channel_handle=result.channel_handle,
                channel_title=result.channel_title,
                source=result.source or source_name,
                metadata=result.metadata,
            )

        failures.append(
            {
                "source": source_name,
                "error_stage": result.source or source_name,
                "error_message": result.error_message or "Unknown resolution failure",
                "retryable": result.retryable,
            }
        )

    return VideoChannelResolution(
        success=False,
        source="structured_failure",
        error_stage="all_strategies_failed",
        error_message="Could not resolve channel info from video using yt-dlp, watch page, or Innertube",
        retryable=any(item.get("retryable", False) for item in failures),
        metadata={"failures": failures},
    )
