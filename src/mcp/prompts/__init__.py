"""MCP prompts for YouTube transcription pipeline.

This module exports all MCP prompt handlers for:
- Video transcription workflow
- Channel sync workflow
"""

from src.mcp.prompts.channel_sync import generate_channel_sync_prompt
from src.mcp.prompts.transcribe import generate_transcribe_video_prompt

__all__ = [
    "generate_transcribe_video_prompt",
    "generate_channel_sync_prompt",
]
