"""Transcript management endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.api.dependencies import get_db

router = APIRouter(prefix="/transcripts", tags=["transcripts"])


@router.get(
    "/{video_id}",
    response_model=dict[str, Any],
    summary="Get transcript",
    description="Retrieve the transcript for a specific video.",
)
async def get_transcript(
    video_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict[str, Any]:
    """Get transcript for a video.

    Args:
        video_id: Video identifier
        db: Database dependency

    Returns:
        Transcript document

    Raises:
        HTTPException: If transcript not found
    """
    from src.database import get_db_manager

    db_manager = get_db_manager()
    transcript = await db_manager.get_transcript(video_id)

    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript for video {video_id} not found",
        )

    return transcript


@router.get(
    "/",
    response_model=list[dict[str, Any]],
    summary="List transcripts",
    description="List all transcripts with pagination.",
)
async def list_transcripts(
    limit: int = 100,
    offset: int = 0,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all transcripts.

    Args:
        limit: Maximum results to return
        offset: Number of results to skip
        db: Database dependency

    Returns:
        List of transcript documents
    """
    # Query the transcripts collection directly
    cursor = db.transcripts.find().sort("created_at", -1).skip(offset).limit(limit)

    results = []
    async for doc in cursor:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        results.append(doc)

    return results
