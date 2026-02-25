"""MCP resource handler for transcripts.

Provides resource access via transcript:// URIs.

URI Patterns:
- transcript://{video_id} - Get transcript by video ID
"""

import json
from typing import Any

from src.database.manager import MongoDBManager


async def read_transcript_resource(uri: str) -> dict[str, Any]:
    """Read a transcript resource by URI.

    This handler processes transcript:// URIs to fetch transcript
    documents from the database.

    Args:
        uri: Resource URI in format "transcript://{video_id}"

    Returns:
        dict with keys:
            - uri: The requested URI
            - mime_type: MIME type (application/json)
            - text: JSON-encoded transcript content
            - error: Error message if not found (optional)

    Example:
        result = await read_transcript_resource("transcript://dQw4w9WgXcQ")
        # Returns: {"uri": "...", "mime_type": "application/json", "text": "{...}"}
    """
    # Parse URI
    if not uri.startswith("transcript://"):
        return {
            "uri": uri,
            "mime_type": "application/json",
            "error": f"Invalid URI scheme: {uri}",
        }

    video_id = uri[len("transcript://") :]

    if not video_id:
        return {
            "uri": uri,
            "mime_type": "application/json",
            "error": "No video ID specified in URI",
        }

    try:
        async with MongoDBManager() as db:
            transcript = await db.get_transcript(video_id)

        if transcript is None:
            return {
                "uri": uri,
                "mime_type": "application/json",
                "error": f"Transcript not found for video ID: {video_id}",
            }

        # Return full transcript as JSON
        return {
            "uri": uri,
            "mime_type": "application/json",
            "text": json.dumps(transcript, indent=2),
        }

    except Exception as e:
        return {
            "uri": uri,
            "mime_type": "application/json",
            "error": f"Failed to read transcript: {e}",
        }


def get_transcript_template() -> dict[str, Any]:
    """Get the transcript resource template.

    Returns:
        Template definition for MCP resource registration
    """
    return {
        "uri_template": "transcript://{video_id}",
        "name": "transcript",
        "description": (
            "Access transcript content by video ID. "
            "Returns full transcript with segments and timestamps."
        ),
        "mime_type": "application/json",
    }
