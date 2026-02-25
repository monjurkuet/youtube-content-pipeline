"""MCP tool for video transcription.

Provides the transcribe_video tool for submitting videos
to the transcription pipeline.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any

from src.core.schemas import TranscriptDocument
from src.database.manager import MongoDBManager
from src.transcription.handler import TranscriptionHandler, identify_source_type


async def transcribe_video(
    source: str,
    priority: str = "normal",
    save_to_db: bool = True,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Transcribe a YouTube video or audio file.

    This tool submits a video for transcription using the pipeline's
    transcription handler. It supports YouTube URLs, video IDs, and
    local audio files.

    Args:
        source: Video source - YouTube URL, video ID, or local file path
        priority: Job priority - "low", "normal", or "high" (default: "normal")
        save_to_db: Whether to save transcript to database (default: True)
        webhook_url: Optional webhook URL for job completion notification

    Returns:
        dict with keys:
            - job_id: Unique job identifier
            - status: Current job status ("completed", "processing", "failed")
            - video_id: Extracted YouTube video ID
            - message: Human-readable status message
            - transcript: Transcript data if completed (optional)

    Example:
        result = await transcribe_video("dQw4w9WgXcQ")
        # Returns: {"job_id": "...", "status": "completed", "video_id": "dQw4w9WgXcQ", ...}

        result = await transcribe_video("https://youtube.com/watch?v=abc123")
        # Returns: {"job_id": "...", "status": "completed", "video_id": "abc123", ...}
    """
    job_id = str(uuid.uuid4())

    try:
        # Identify source type and extract video ID
        source_type, identifier = identify_source_type(source)

        # Perform transcription
        handler = TranscriptionHandler()
        loop = asyncio.get_event_loop()

        # Run blocking transcription in executor
        raw_transcript = await loop.run_in_executor(
            None,
            lambda: handler.get_transcript(identifier, source_type),
        )

        result: dict[str, Any] = {
            "job_id": job_id,
            "status": "completed",
            "video_id": raw_transcript.video_id,
            "message": f"Transcription completed successfully using {raw_transcript.source}",
            "source_type": source_type,
            "language": raw_transcript.language,
            "segment_count": len(raw_transcript.segments),
            "duration_seconds": raw_transcript.duration,
        }

        # Save to database if requested
        if save_to_db:
            try:
                async with MongoDBManager() as db:
                    transcript_doc = TranscriptDocument.from_raw_transcript(
                        raw_transcript=raw_transcript,
                        source_type=source_type,
                        source_url=source if source_type in ("url",) else None,
                    )
                    doc_id = await db.save_transcript(transcript_doc)
                    result["database_id"] = doc_id

                    # Update video metadata status
                    await db.mark_transcript_completed(
                        raw_transcript.video_id,
                        doc_id,
                    )
            except Exception as db_error:
                result["db_warning"] = f"Failed to save to database: {db_error}"

        # Include full transcript in response for immediate access
        result["transcript"] = {
            "full_text": raw_transcript.full_text,
            "segments": [
                {
                    "text": seg.text,
                    "start": seg.start,
                    "end": seg.end,
                    "duration": seg.duration,
                }
                for seg in raw_transcript.segments
            ],
        }

        return result

    except Exception as e:
        return {
            "job_id": job_id,
            "status": "failed",
            "video_id": source,
            "message": f"Transcription failed: {e}",
            "error": str(e),
        }
