"""Structured logging configuration for the transcription pipeline."""

import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

console = Console()

# Module-level logger
logger: logging.Logger | None = None


def setup_logging(
    level: str = "INFO",
    log_file: Path | str | None = None,
    rich_tracebacks: bool = True,
) -> logging.Logger:
    """
    Configure structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        rich_tracebacks: Enable rich traceback formatting

    Returns:
        Configured logger instance
    """
    global logger

    # Create logger
    logger = logging.getLogger("youtube_pipeline")
    logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    logger.handlers.clear()

    # Rich console handler (for CLI output)
    rich_handler = RichHandler(
        console=console,
        rich_tracebacks=rich_tracebacks,
        tracebacks_show_locals=(level.upper() == "DEBUG"),
        markup=True,
    )
    rich_handler.setLevel(logging.INFO)

    # Format for rich handler
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(rich_handler)

    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)

    # Prevent logging to root logger
    logger.propagate = False

    logger.info(f"📝 Logging initialized (level={level})")

    return logger


def get_logger(name: str = "youtube_pipeline") -> logging.Logger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name (default: youtube_pipeline)

    Returns:
        Logger instance
    """
    global logger

    if logger is None:
        # Auto-setup with defaults if not configured
        logger = setup_logging()

    if name == "youtube_pipeline":
        return logger

    # Child logger inherit from main logger
    child_logger = logging.getLogger(f"youtube_pipeline.{name}")
    child_logger.setLevel(logger.level)
    return child_logger


def log_api_request(
    logger_instance: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_ip: str | None = None,
) -> None:
    """
    Log HTTP API request in structured format.

    Args:
        logger_instance: Logger to use
        method: HTTP method
        path: Request path
        status_code: Response status code
        duration_ms: Request duration in milliseconds
        client_ip: Optional client IP address
    """
    log_level = logging.INFO if status_code < 400 else logging.WARNING

    extra = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
    }
    if client_ip:
        extra["client_ip"] = client_ip

    message = f"{method} {path} {status_code} {duration_ms:.1f}ms"
    logger_instance.log(log_level, message, extra=extra)


def log_transcription_event(
    logger_instance: logging.Logger,
    video_id: str,
    event: str,
    source: str | None = None,
    duration_seconds: float | None = None,
    error: str | None = None,
) -> None:
    """
    Log transcription pipeline events.

    Args:
        logger_instance: Logger to use
        video_id: YouTube video ID
        event: Event type (started, completed, failed, fallback)
        source: Transcript source (youtube_api, whisper)
        duration_seconds: Processing duration
        error: Error message if failed
    """
    extra: dict[str, Any] = {
        "video_id": video_id,
        "event": event,
    }

    if source:
        extra["source"] = source
    if duration_seconds is not None:
        extra["duration_seconds"] = duration_seconds
    if error:
        extra["error"] = error

    if event == "failed":
        logger_instance.error(f"❌ Transcription failed: {video_id}", extra=extra)
    elif event == "completed":
        logger_instance.info(f"✅ Transcription complete: {video_id}", extra=extra)
    else:
        logger_instance.info(f"📝 Transcription {event}: {video_id}", extra=extra)


def log_channel_sync_event(
    logger_instance: logging.Logger,
    channel_id: str,
    channel_handle: str,
    event: str,
    videos_fetched: int | None = None,
    videos_new: int | None = None,
    error: str | None = None,
) -> None:
    """
    Log channel sync events.

    Args:
        logger_instance: Logger to use
        channel_id: YouTube channel ID
        channel_handle: Channel handle
        event: Event type (started, completed, failed)
        videos_fetched: Number of videos fetched
        videos_new: Number of new videos
        error: Error message if failed
    """
    extra: dict[str, Any] = {
        "channel_id": channel_id,
        "channel_handle": channel_handle,
        "event": event,
    }

    if videos_fetched is not None:
        extra["videos_fetched"] = videos_fetched
    if videos_new is not None:
        extra["videos_new"] = videos_new
    if error:
        extra["error"] = error

    if event == "failed":
        logger_instance.error(f"❌ Channel sync failed: @{channel_handle}", extra=extra)
    elif event == "completed":
        logger_instance.info(
            f"✅ Channel sync complete: @{channel_handle} ({videos_fetched} videos)",
            extra=extra,
        )
    else:
        logger_instance.info(f"🔄 Channel sync started: @{channel_handle}", extra=extra)
