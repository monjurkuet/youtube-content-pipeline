"""MongoDB storage for transcription pipeline.

DEPRECATED: This module is now located at src.database.manager
This file is kept for backward compatibility only.
"""

# Re-export from new location for backward compatibility
from src.database.manager import (
    MongoDBManager,
    get_db_manager,
    get_db_manager_context,
)

__all__ = [
    "MongoDBManager",
    "get_db_manager",
    "get_db_manager_context",
]
