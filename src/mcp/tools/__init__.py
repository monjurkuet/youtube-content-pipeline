"""MCP tools for YouTube transcription pipeline.

This module exports all MCP tool handlers for:
- Video transcription
- Transcript retrieval
- Channel management
"""

from src.mcp.tools.channels import (
    add_channel,
    sync_channel,
    transcribe_channel_pending,
)
from src.mcp.tools.transcription import transcribe_video
from src.mcp.tools.transcripts import get_job_status, get_transcript, list_transcripts

__all__ = [
    # Transcription tools
    "transcribe_video",
    # Transcript tools
    "get_transcript",
    "list_transcripts",
    "get_job_status",
    # Channel tools
    "add_channel",
    "sync_channel",
    "transcribe_channel_pending",
]
