"""Tests for MongoDB manager configuration."""

from unittest.mock import patch

import pytest

from src.core.config import get_settings
from src.database.manager import MongoDBManager


@pytest.mark.asyncio
async def test_initialize_uses_configured_mongo_timeouts() -> None:
    """MongoDB client should inherit explicit timeout settings from config."""
    with patch.dict(
        "os.environ",
        {
            "MONGODB_SERVER_SELECTION_TIMEOUT_MS": "1234",
            "MONGODB_CONNECT_TIMEOUT_MS": "2345",
            "MONGODB_SOCKET_TIMEOUT_MS": "3456",
        },
        clear=False,
    ):
        get_settings(force_reload=True)

        with patch("src.database.manager.AsyncIOMotorClient") as mock_client:
            manager = MongoDBManager()
            await manager.initialize()

        mock_client.assert_called_once_with(
            manager.settings.mongodb_url,
            serverSelectionTimeoutMS=1234,
            connectTimeoutMS=2345,
            socketTimeoutMS=3456,
        )
