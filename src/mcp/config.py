"""MCP server configuration.

This module provides configuration for the MCP server including
server metadata, transport settings, and feature flags.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MCPConfig:
    """MCP server configuration.

    Attributes:
        server_name: Name of the MCP server
        server_version: Version string
        server_description: Human-readable description
        transport: Transport protocol (stdio, sse, etc.)
        log_level: Logging level for MCP operations
    """

    server_name: str = "youtube-transcription-pipeline"
    server_version: str = "0.5.0"
    server_description: str = (
        "MCP server for YouTube transcription pipeline. "
        "Provides tools for transcribing videos, managing channels, "
        "and retrieving transcripts."
    )
    transport: Literal["stdio", "sse"] = "stdio"
    log_level: str = "info"


# Default configuration instance
DEFAULT_CONFIG = MCPConfig()


def get_mcp_config() -> MCPConfig:
    """Get the default MCP configuration.

    Returns:
        MCPConfig instance with default settings
    """
    return DEFAULT_CONFIG
