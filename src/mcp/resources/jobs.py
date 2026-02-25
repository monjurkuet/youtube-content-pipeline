"""MCP resource handler for job status.

Provides resource access via job:// URIs.

URI Patterns:
- job://{job_id} - Get job status by job ID
"""

import json
from typing import Any

from src.mcp.tools.transcripts import get_job_status


async def read_job_resource(uri: str) -> dict[str, Any]:
    """Read a job status resource by URI.

    This handler processes job:// URIs to fetch job status information.

    Args:
        uri: Resource URI in format "job://{job_id}"

    Returns:
        dict with keys:
            - uri: The requested URI
            - mime_type: MIME type (application/json)
            - text: JSON-encoded job status
            - error: Error message if invalid (optional)

    Example:
        result = await read_job_resource("job://550e8400-e29b-41d4-a716-446655440000")
        # Returns: {"uri": "...", "mime_type": "application/json", "text": "{...}"}
    """
    # Parse URI
    if not uri.startswith("job://"):
        return {
            "uri": uri,
            "mime_type": "application/json",
            "error": f"Invalid URI scheme: {uri}",
        }

    job_id = uri[len("job://") :]

    if not job_id:
        return {
            "uri": uri,
            "mime_type": "application/json",
            "error": "No job ID specified in URI",
        }

    try:
        # Get job status
        status = await get_job_status(job_id)

        return {
            "uri": uri,
            "mime_type": "application/json",
            "text": json.dumps(status, indent=2),
        }

    except Exception as e:
        return {
            "uri": uri,
            "mime_type": "application/json",
            "error": f"Failed to read job status: {e}",
        }


def get_job_template() -> dict[str, Any]:
    """Get the job resource template.

    Returns:
        Template definition for MCP resource registration
    """
    return {
        "uri_template": "job://{job_id}",
        "name": "job",
        "description": (
            "Access transcription job status by job ID. "
            "Returns job status, progress, and result information."
        ),
        "mime_type": "application/json",
    }
