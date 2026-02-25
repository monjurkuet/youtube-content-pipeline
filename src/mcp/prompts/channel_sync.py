"""MCP prompt for channel sync workflow.

Provides a pre-filled prompt for syncing and transcribing
videos from a YouTube channel.
"""

from typing import Any


async def generate_channel_sync_prompt(
    arguments: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate a prompt for syncing a YouTube channel.

    This prompt provides context and guidance for syncing channel videos
    and optionally transcribing them.

    Args:
        arguments: Optional arguments containing:
            - handle: YouTube channel handle (@username)
            - limit: Maximum videos to sync/transcribe
            - mode: Sync mode ("recent" or "all")

    Returns:
        List of prompt messages for the AI assistant

    Example:
        messages = await generate_channel_sync_prompt({
            "handle": "@MrBeast",
            "limit": 10,
            "mode": "recent",
        })
    """
    handle = (arguments or {}).get("handle", "<channel_handle>")
    limit = (arguments or {}).get("limit", 10)
    mode = (arguments or {}).get("mode", "recent")

    # Normalize handle
    normalized_handle = handle.lstrip("@")

    messages = [
        {
            "role": "user",
            "content": {
                "type": "text",
                "text": f"""I want to sync and transcribe videos from a YouTube channel.

**Channel Handle:** @{normalized_handle}
**Sync Mode:** {mode}
**Video Limit:** {limit}

Please help me sync this channel's videos and transcribe them.

Available options:
- **handle**: YouTube channel handle (with or without @ prefix)
- **mode**: "recent" for ~15 latest videos (RSS), "all" for all videos (slower)
- **limit**: Maximum number of videos to process

The workflow will:
1. Resolve the channel handle to a channel ID
2. Add the channel to tracking (if not already tracked)
3. Sync videos from the channel to the database
4. Transcribe any pending videos (up to the limit)

Would you like me to proceed with the channel sync?""",
            },
        },
        {
            "role": "assistant",
            "content": {
                "type": "text",
                "text": f"""I'll help you sync and transcribe videos from @{normalized_handle}.

**Channel Sync Request:**
- Handle: @{normalized_handle}
- Mode: {mode}
- Video Limit: {limit}

I'll perform the following steps:
1. **Add Channel**: Register the channel for tracking
2. **Sync Videos**: Fetch video metadata from the channel
3. **Transcribe Pending**: Submit pending videos for transcription

Let me start by adding the channel and syncing videos...""",
            },
        },
    ]

    return messages


def get_channel_sync_prompt_template() -> dict[str, Any]:
    """Get the channel sync prompt template.

    Returns:
        Template definition for MCP prompt registration
    """
    return {
        "name": "sync-channel",
        "description": (
            "Sync and transcribe all videos from a YouTube channel. "
            "Provides context for the complete channel workflow including "
            "channel registration, video sync, and batch transcription."
        ),
        "arguments": [
            {
                "name": "handle",
                "description": "YouTube channel handle (e.g., '@MrBeast' or 'MrBeast')",
                "required": True,
            },
            {
                "name": "limit",
                "description": "Maximum number of videos to sync/transcribe",
                "required": False,
                "default": 10,
            },
            {
                "name": "mode",
                "description": "Sync mode: 'recent' for latest videos, 'all' for complete history",
                "required": False,
                "default": "recent",
            },
        ],
    }
