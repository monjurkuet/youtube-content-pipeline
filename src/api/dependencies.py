"""FastAPI dependencies for the API module."""

from typing import Any

from src.core.config import Settings, get_settings
from src.database.manager import MongoDBManager, get_db_manager


async def get_db() -> Any:
    """Dependency to get MongoDB database instance.

    Returns:
        AsyncIOMotorDatabase: The MongoDB database instance
    """
    db_manager = get_db_manager()
    await db_manager.initialize()
    return db_manager.db  # type: ignore[no-any-return]


def get_settings_dep() -> Settings:
    """Dependency to get application settings.

    Returns:
        Settings: Application settings instance
    """
    return get_settings()


async def get_db_manager_dep() -> MongoDBManager:
    """Dependency to get the database manager.

    Returns:
        MongoDBManager: Database manager instance
    """
    db_manager = get_db_manager()
    await db_manager.initialize()
    return db_manager
