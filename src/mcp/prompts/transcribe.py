"""MCP prompt for video transcription workflow.

Provides a pre-filled prompt for transcribing videos with
optional settings.
"""

from typing import Any


async def generate_transcribe_video_prompt(
    arguments: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate a prompt for transcribing a YouTube video.

    This prompt provides context and guidance for transcribing videos,
    including best practices and available options.

    Args:
        arguments: Optional arguments containing:
            - source: Video source (YouTube URL, video ID, or file path)
            - priority: Job priority ("low", "normal", "high")
            - language: Target language code (optional)

    Returns:
        List of prompt messages for the AI assistant

    Example:
        messages = await generate_transcribe_video_prompt({
            "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "priority": "normal",
        })
    """
    source = (arguments or {}).get("source", "<video_url_or_id>")
    priority = (arguments or {}).get("priority", "normal")
    language = (arguments or {}).get("language", "auto-detect")

    messages = [
        {
            "role": "user",
            "content": {
                "type": "text",
                "text": f"""I want to transcribe a YouTube video.

**Video Source:** {source}
**Priority:** {priority}
**Language:** {language}

Please help me transcribe this video using the transcription pipeline.

Available options:
- **source**: YouTube URL, video ID, or local audio file path
- **priority**: "low", "normal", or "high" (affects processing order)
- **save_to_db**: Whether to save transcript to database (default: true)
- **webhook_url**: Optional webhook for completion notification

The transcription pipeline will:
1. Extract audio from the video (if YouTube URL)
2. Attempt YouTube Transcript API first (fast, accurate)
3. Fall back to Whisper OpenVINO transcription if API fails
4. Save the transcript with timestamps to the database

Would you like me to proceed with the transcription?""",
            },
        },
        {
            "role": "assistant",
            "content": {
                "type": "text",
                "text": f"""I'll help you transcribe this video.

**Transcription Request:**
- Source: {source}
- Priority: {priority}
- Language: {language}

I'll use the `transcribe_video` tool to submit this for transcription. The pipeline will automatically:
1. Identify the source type (YouTube URL, video ID, or local file)
2. Extract audio if needed
3. Fetch or generate the transcript
4. Save it to the database

Let me proceed with the transcription...""",
            },
        },
    ]

    return messages


def get_transcribe_prompt_template() -> dict[str, Any]:
    """Get the transcribe video prompt template.

    Returns:
        Template definition for MCP prompt registration
    """
    return {
        "name": "transcribe-video",
        "description": (
            "Transcribe a YouTube video with optional settings. "
            "Provides context for the transcription workflow including "
            "source identification, priority settings, and language options."
        ),
        "arguments": [
            {
                "name": "source",
                "description": "YouTube URL, video ID, or local audio file path",
                "required": True,
            },
            {
                "name": "priority",
                "description": "Job priority: low, normal, or high",
                "required": False,
                "default": "normal",
            },
            {
                "name": "language",
                "description": "Target language code (e.g., 'en', 'es') or 'auto-detect'",
                "required": False,
                "default": "auto-detect",
            },
        ],
    }
