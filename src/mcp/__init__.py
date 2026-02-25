"""MCP (Model Context Protocol) server module.

This module provides MCP server integration for the YouTube transcription pipeline.
MCP allows AI assistants to interact with the pipeline through a standardized protocol.

Features:
- Tools: transcribe_video, get_transcript, list_transcripts, get_job_status,
         add_channel, sync_channel, transcribe_channel_pending
- Resources: transcript:// URIs, job:// URIs
- Prompts: transcribe-video, sync-channel

Usage:
    # Start MCP server
    uv run python -m src.mcp.server

    # Test with MCP inspector
    npx @modelcontextprotocol/inspector uv run python -m src.mcp.server
"""

from src.mcp.config import MCPConfig, get_mcp_config

# Note: Server and tools are imported lazily to avoid circular imports
# Use specific imports for tools, resources, and prompts

__version__ = "0.5.0"

__all__ = [
    # Config
    "MCPConfig",
    "get_mcp_config",
    # Version
    "__version__",
]
