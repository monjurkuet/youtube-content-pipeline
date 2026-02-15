"""API routers module."""

from src.api.routers.transcripts import router as transcripts_router
from src.api.routers.videos import router as videos_router

__all__ = [
    "videos_router",
    "transcripts_router",
]
