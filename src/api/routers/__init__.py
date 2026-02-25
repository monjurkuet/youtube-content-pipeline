"""API routers module."""

from src.api.routers.channels import router as channels_router
from src.api.routers.health import router as health_router
from src.api.routers.stats import router as stats_router
from src.api.routers.transcripts import router as transcripts_router
from src.api.routers.videos import router as videos_router

__all__ = [
    "videos_router",
    "transcripts_router",
    "channels_router",
    "stats_router",
    "health_router",
]
