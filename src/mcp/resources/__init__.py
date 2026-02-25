"""MCP resources for YouTube transcription pipeline.

This module exports all MCP resource handlers for:
- Transcript content (transcript:// URIs)
- Job status (job:// URIs)
"""

from src.mcp.resources.jobs import read_job_resource
from src.mcp.resources.transcripts import read_transcript_resource

__all__ = [
    "read_transcript_resource",
    "read_job_resource",
]
