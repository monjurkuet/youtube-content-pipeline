"""MCP (Model Context Protocol) server for YouTube transcription pipeline.

This module provides MCP server integration using FastMCP.
MCP allows AI assistants to interact with the transcription pipeline
through a standardized protocol with tools, resources, and prompts.

Usage:
    uv run python -m src.mcp.server

Or with MCP inspector:
    npx @modelcontextprotocol/inspector uv run python -m src.mcp.server
"""

import argparse
import asyncio
import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp.config import DEFAULT_CONFIG, MCPConfig
from src.mcp.prompts.channel_sync import (
    generate_channel_sync_prompt,
    get_channel_sync_prompt_template,
)
from src.mcp.prompts.transcribe import (
    generate_transcribe_video_prompt,
    get_transcribe_prompt_template,
)
from src.mcp.resources.jobs import get_job_template, read_job_resource
from src.mcp.resources.transcripts import get_transcript_template, read_transcript_resource
from src.mcp.tools.channels import (
    add_channel,
    list_channel_videos,
    list_channels,
    remove_channel,
    sync_channel,
    transcribe_channel_pending,
)
from src.mcp.tools.transcription import transcribe_video
from src.mcp.tools.transcripts import get_job_status, get_transcript, list_transcripts

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# Create FastMCP server instance
mcp = FastMCP(
    name=DEFAULT_CONFIG.server_name,
    instructions=DEFAULT_CONFIG.server_description,
)


# ============================================================================
# Tools Registration
# ============================================================================


@mcp.tool(
    name="transcribe_video",
    description=(
        "Transcribe a YouTube video or audio file. "
        "Supports YouTube URLs, video IDs, and local audio files. "
        "Automatically uses YouTube Transcript API first, then falls back to Whisper. "
        "Returns the full transcript with timestamps."
    ),
)
async def tool_transcribe_video(
    source: str,
    priority: str = "normal",
    save_to_db: bool = True,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Transcribe a YouTube video.

    Args:
        source: Video source - YouTube URL, video ID, or local file path
        priority: Job priority - "low", "normal", or "high"
        save_to_db: Whether to save transcript to database
        webhook_url: Optional webhook URL for completion notification

    Returns:
        Job result with status, video_id, and transcript data
    """
    return await transcribe_video(
        source=source,
        priority=priority,
        save_to_db=save_to_db,
        webhook_url=webhook_url,
    )


@mcp.tool(
    name="get_transcript",
    description=(
        "Retrieve a transcript by video ID. "
        "Returns the full transcript document including all segments with timestamps."
    ),
)
async def tool_get_transcript(video_id: str) -> dict[str, Any]:
    """Get transcript for a video.

    Args:
        video_id: YouTube video ID (11-character string)

    Returns:
        Transcript document with segments
    """
    return await get_transcript(video_id=video_id)


@mcp.tool(
    name="list_transcripts",
    description=(
        "List all transcripts with optional filtering. "
        "Results are sorted by creation date (newest first). "
        "Returns metadata only, not full segments."
    ),
)
async def tool_list_transcripts(
    limit: int = 100,
    offset: int = 0,
    transcript_source: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """List transcripts.

    Args:
        limit: Maximum number of transcripts to return
        offset: Number of transcripts to skip
        transcript_source: Filter by source ("youtube_api" or "whisper")
        language: Filter by language code

    Returns:
        List of transcript metadata with pagination info
    """
    return await list_transcripts(
        limit=limit,
        offset=offset,
        transcript_source=transcript_source,
        language=language,
    )


@mcp.tool(
    name="get_job_status",
    description=(
        "Check the status of a transcription job. "
        "Note: Transcription is synchronous, so jobs complete immediately."
    ),
)
async def tool_get_job_status(job_id: str) -> dict[str, Any]:
    """Get job status.

    Args:
        job_id: Job identifier (UUID format)

    Returns:
        Job status with progress and result URL
    """
    return await get_job_status(job_id=job_id)


@mcp.tool(
    name="add_channel",
    description=(
        "Add a YouTube channel to tracking. "
        "Resolves channel handle to channel ID and saves to database."
    ),
)
async def tool_add_channel(handle: str) -> dict[str, Any]:
    """Add a channel to tracking.

    Args:
        handle: YouTube channel handle (with or without @ prefix)

    Returns:
        Channel info with resolved channel ID
    """
    return await add_channel(handle=handle)


@mcp.tool(
    name="sync_channel",
    description=(
        "Sync videos from a YouTube channel. "
        "Fetches video metadata and marks videos as pending transcription. "
        "Use mode='recent' for ~15 latest videos, or mode='all' for complete history."
    ),
)
async def tool_sync_channel(handle: str, mode: str = "recent") -> dict[str, Any]:
    """Sync channel videos.

    Args:
        handle: YouTube channel handle
        mode: Sync mode - "recent" or "all"

    Returns:
        Sync results with video counts
    """
    return await sync_channel(handle=handle, mode=mode)


@mcp.tool(
    name="transcribe_channel_pending",
    description=(
        "Transcribe all pending videos from a channel. "
        "Finds untranscribed videos and submits them for transcription."
    ),
)
async def tool_transcribe_channel_pending(handle: str, limit: int = 10) -> dict[str, Any]:
    """Transcribe pending videos from a channel.

    Args:
        handle: YouTube channel handle
        limit: Maximum number of videos to transcribe

    Returns:
        List of job results for submitted videos
    """
    return await transcribe_channel_pending(handle=handle, limit=limit)


@mcp.tool(
    name="list_channels",
    description=(
        "List all tracked YouTube channels. "
        "Returns channels sorted by when they were added (newest first)."
    ),
)
async def tool_list_channels(limit: int = 100) -> dict[str, Any]:
    """List all tracked channels.

    Args:
        limit: Maximum number of channels to return

    Returns:
        List of channels with video counts
    """
    return await list_channels(limit=limit)


@mcp.tool(
    name="remove_channel",
    description=(
        "Remove a channel from tracking. "
        "Video metadata and transcripts are preserved."
    ),
)
async def tool_remove_channel(channel_id: str) -> dict[str, Any]:
    """Remove a channel from tracking.

    Args:
        channel_id: YouTube channel ID (e.g., UCX6OQ3DkcsbYNE6H8uQQuVA)

    Returns:
        Confirmation message
    """
    return await remove_channel(channel_id=channel_id)


@mcp.tool(
    name="list_channel_videos",
    description=(
        "List videos for a specific channel. "
        "Returns video metadata sorted by publication date."
    ),
)
async def tool_list_channel_videos(
    channel_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List videos for a channel.

    Args:
        channel_id: YouTube channel ID
        limit: Maximum number of videos to return
        offset: Number of videos to skip

    Returns:
        List of video metadata
    """
    return await list_channel_videos(
        channel_id=channel_id,
        limit=limit,
        offset=offset,
    )


# ============================================================================
# Resources Registration
# ============================================================================


@mcp.resource(
    uri="transcript://{video_id}",
    name="transcript",
    description="Access transcript content by video ID. Returns full transcript with segments.",
    mime_type="application/json",
)
async def resource_transcript(video_id: str) -> str:
    """Read transcript resource.

    Args:
        video_id: YouTube video ID

    Returns:
        JSON-encoded transcript document
    """
    result = await read_transcript_resource(f"transcript://{video_id}")
    if "error" in result:
        raise ValueError(result["error"])
    return result["text"]


@mcp.resource(
    uri="job://{job_id}",
    name="job",
    description="Access transcription job status by job ID.",
    mime_type="application/json",
)
async def resource_job(job_id: str) -> str:
    """Read job status resource.

    Args:
        job_id: Job identifier

    Returns:
        JSON-encoded job status
    """
    result = await read_job_resource(f"job://{job_id}")
    if "error" in result:
        raise ValueError(result["error"])
    return result["text"]


# ============================================================================
# Prompts Registration
# ============================================================================


@mcp.prompt(
    name="transcribe-video",
    description=(
        "Transcribe a YouTube video with optional settings. "
        "Provides context for the transcription workflow."
    ),
)
async def prompt_transcribe_video(
    source: str,
    priority: str = "normal",
    language: str = "auto-detect",
) -> list[dict[str, Any]]:
    """Generate transcription prompt.

    Args:
        source: Video source (URL, ID, or file path)
        priority: Job priority
        language: Target language

    Returns:
        Prompt messages for AI assistant
    """
    return await generate_transcribe_video_prompt(
        arguments={
            "source": source,
            "priority": priority,
            "language": language,
        }
    )


@mcp.prompt(
    name="sync-channel",
    description=(
        "Sync and transcribe all videos from a YouTube channel. "
        "Provides context for the complete channel workflow."
    ),
)
async def prompt_sync_channel(
    handle: str,
    limit: int = 10,
    mode: str = "recent",
) -> list[dict[str, Any]]:
    """Generate channel sync prompt.

    Args:
        handle: Channel handle
        limit: Maximum videos to process
        mode: Sync mode

    Returns:
        Prompt messages for AI assistant
    """
    return await generate_channel_sync_prompt(
        arguments={
            "handle": handle,
            "limit": limit,
            "mode": mode,
        }
    )


# ============================================================================
# Server Entry Point
# ============================================================================


def create_mcp_server(config: MCPConfig | None = None) -> FastMCP:
    """Create and configure the MCP server.

    Args:
        config: Optional custom configuration

    Returns:
        Configured FastMCP server instance
    """
    if config is None:
        config = DEFAULT_CONFIG

    logger.info(
        "Created MCP server: %s v%s",
        config.server_name,
        config.server_version,
    )

    return mcp


async def run_server_stdio() -> None:
    """Run the MCP server with STDIO transport."""
    logger.info("Starting MCP server with STDIO transport")

    # Run the FastMCP server
    await mcp.run_stdio_async()


def main() -> None:
    """Main entry point for MCP server."""
    parser = argparse.ArgumentParser(
        description="MCP Server for YouTube Transcription Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with STDIO transport (default)
  uv run python -m src.mcp.server

  # Run with MCP inspector
  npx @modelcontextprotocol/inspector uv run python -m src.mcp.server

  # Test with Claude Desktop
  # Add to claude_desktop_config.json:
  # {
  #   "mcpServers": {
  #     "youtube-transcription": {
  #       "command": "uv",
  #       "args": ["run", "python", "-m", "src.mcp.server"]
  #     }
  #   }
  # }
        """,
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )

    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Logging level (default: info)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {DEFAULT_CONFIG.server_version}",
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(args.log_level.upper())

    logger.info(
        "Starting %s v%s with %s transport",
        DEFAULT_CONFIG.server_name,
        DEFAULT_CONFIG.server_version,
        args.transport,
    )

    # Run server
    if args.transport == "stdio":
        asyncio.run(run_server_stdio())
    else:
        logger.error("SSE transport not yet implemented")
        sys.exit(1)


if __name__ == "__main__":
    main()
