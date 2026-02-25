"""Transcript management endpoints.

This module provides endpoints for:
- Retrieving individual transcripts
- Listing all transcripts with pagination
- Deleting transcripts
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.api.dependencies import get_db
from src.api.models.errors import ErrorCodes
from src.api.security import validate_api_key
from src.core.constants import DEFAULT_LIMIT, MAX_LIMIT

router = APIRouter(prefix="/transcripts", tags=["transcripts"])


@router.get(
    "/{video_id}",
    response_model=dict[str, Any],
    summary="Get transcript",
    description="""
    Retrieve the transcript for a specific video.

    Returns the complete transcript document including:
    - Video metadata (title, channel, duration)
    - Transcript segments with timestamps
    - Full text transcription
    - Language and source information
    """,
    operation_id="get_transcript",
    responses={
        200: {
            "description": "Transcript retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "_id": "507f1f77bcf86cd799439011",
                        "video_id": "dQw4w9WgXcQ",
                        "title": "Example Video",
                        "channel_id": "UC1234567890",
                        "channel_name": "Example Channel",
                        "duration_seconds": 212.5,
                        "language": "en",
                        "transcript_source": "youtube_auto",
                        "segments": [
                            {"start": 0.0, "end": 5.0, "text": "Hello world"},
                            {"start": 5.0, "end": 10.0, "text": "Welcome to this video"},
                        ],
                        "full_text": "Hello world. Welcome to this video.",
                        "created_at": "2024-01-15T10:30:00Z",
                        "updated_at": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        404: {
            "description": "Transcript not found",
            "content": {
                "application/json": {
                    "example": {
                        "error": "NOT_FOUND",
                        "error_code": "TRANSCRIPT_NOT_FOUND",
                        "message": "Transcript for video dQw4w9WgXcQ not found",
                        "request_id": "req_abc123",
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "error": "INTERNAL_SERVER_ERROR",
                        "error_code": "DATABASE_ERROR",
                        "message": "An unexpected error occurred",
                        "request_id": "req_abc123",
                        "timestamp": "2024-01-15T10:30:00Z",
                    }
                }
            },
        },
    },
)
async def get_transcript(
    video_id: str = Path(
        ...,
        description="YouTube video ID",
        examples=["dQw4w9WgXcQ"],
        pattern=r"^[a-zA-Z0-9_-]{11}$",
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict[str, Any]:
    """Get transcript for a video.

    Args:
        video_id: YouTube video identifier (11 characters)
        db: Database dependency

    Returns:
        Transcript document with segments and metadata

    Raises:
        HTTPException: If transcript not found (404)
    """
    doc = await db.transcripts.find_one({"video_id": video_id})

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript for video {video_id} not found",
        )

    if "_id" in doc:
        doc["_id"] = str(doc["_id"])

    return doc


@router.get(
    "/",
    response_model=list[dict[str, Any]],
    summary="List transcripts",
    description="""
    List all transcripts with pagination support.

    **Pagination:**
    - `limit`: Maximum number of results (default: 100, max: 1000)
    - `offset`: Number of results to skip (default: 0)

    **Filtering:**
    - `transcript_source`: Filter by source (youtube_auto, whisper_openvino, etc.)
    - `language`: Filter by language code (en, es, fr, etc.)

    Results are sorted by creation date (newest first).
    """,
    operation_id="list_transcripts",
    responses={
        200: {
            "description": "List of transcripts",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "_id": "507f1f77bcf86cd799439011",
                            "video_id": "dQw4w9WgXcQ",
                            "title": "Example Video",
                            "channel_name": "Example Channel",
                            "language": "en",
                            "transcript_source": "youtube_auto",
                            "created_at": "2024-01-15T10:30:00Z",
                        }
                    ]
                }
            },
        },
        422: {
            "description": "Validation error",
        },
        500: {
            "description": "Internal server error",
        },
    },
)
async def list_transcripts(
    limit: int = Query(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of results to return",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of results to skip",
    ),
    transcript_source: str | None = Query(
        default=None,
        description="Filter by transcript source",
        examples=["youtube_auto", "whisper_openvino"],
    ),
    language: str | None = Query(
        default=None,
        description="Filter by language code",
        examples=["en", "es", "fr"],
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all transcripts with optional filtering.

    Args:
        limit: Maximum results to return (1-1000)
        offset: Number of results to skip
        transcript_source: Optional filter by source
        language: Optional filter by language code
        db: Database dependency

    Returns:
        List of transcript documents

    Raises:
        HTTPException: If validation fails
    """
    query: dict[str, Any] = {}
    if transcript_source:
        query["transcript_source"] = transcript_source
    if language:
        query["language"] = language

    cursor = db.transcripts.find(query).sort("created_at", -1).skip(offset).limit(limit)

    results = []
    async for doc in cursor:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        results.append(doc)

    return results


@router.delete(
    "/{video_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete transcript",
    description="""
    Delete a transcript from the database.

    This removes the transcript document permanently.
    The associated video metadata is preserved but marked as pending for re-transcription.

    **Warning:** This action cannot be undone.
    """,
    operation_id="delete_transcript",
    responses={
        200: {
            "description": "Transcript deleted successfully",
        },
        404: {
            "description": "Transcript not found",
        },
    },
)
async def delete_transcript(
    video_id: str = Path(
        ...,
        description="YouTube video ID",
        examples=["dQw4w9WgXcQ"],
        pattern=r"^[a-zA-Z0-9_-]{11}$",
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> dict[str, Any]:
    """Delete a transcript.

    Args:
        video_id: YouTube video identifier (11 characters)
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        Confirmation message

    Raises:
        HTTPException: If transcript not found (404)
    """
    # Check if transcript exists
    doc = await db.transcripts.find_one({"video_id": video_id})

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript for video {video_id} not found",
        )

    # Delete the transcript
    result = await db.transcripts.delete_one({"video_id": video_id})

    # Update video metadata status to pending
    await db.video_metadata.update_one(
        {"video_id": video_id},
        {"$set": {"transcript_status": "pending", "transcript_id": None}},
    )

    return {
        "success": result.deleted_count > 0,
        "video_id": video_id,
        "message": f"Transcript for video {video_id} deleted",
    }
