"""Data models for channel resolution."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class VideoChannelResolution:
    """Structured result for resolving a YouTube video to its channel."""

    success: bool
    channel_id: str | None = None
    channel_handle: str | None = None
    channel_title: str | None = None
    source: str | None = None
    error_stage: str | None = None
    error_message: str | None = None
    retryable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StrategyResult:
    """Structured result for a single resolution strategy."""

    success: bool
    channel_id: str | None = None
    channel_handle: str | None = None
    channel_title: str | None = None
    source: str | None = None
    error_message: str | None = None
    retryable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
