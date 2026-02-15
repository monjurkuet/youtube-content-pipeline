"""FastAPI dependencies for the API module."""

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.config import Settings, get_settings
from src.database import MongoDBManager, get_db_manager


async def get_db() -> AsyncIOMotorDatabase:
    """Dependency to get MongoDB database instance.

    Returns:
        AsyncIOMotorDatabase: The MongoDB database instance
    """
    db_manager = get_db_manager()
    return db_manager.db


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
    return get_db_manager()
