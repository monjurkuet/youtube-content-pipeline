"""Database module for MongoDB operations.

This module provides database management and operations for the transcription pipeline.

Usage:
    # Context manager (recommended)
    async with MongoDBManager() as db:
        await db.save_transcript(...)

    # Manual lifecycle
    db = MongoDBManager()
    try:
        await db.initialize()
        await db.save_transcript(...)
    finally:
        await db.close()
"""

from src.database.manager import MongoDBManager, get_db_manager, get_db_manager_context

__all__ = [
    "MongoDBManager",
    "get_db_manager",
    "get_db_manager_context",
]
