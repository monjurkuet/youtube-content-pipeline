"""Regression tests for API endpoint stabilization changes."""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from src.api.dependencies import get_db, get_db_manager_dep


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    """Return whether a fake Mongo document matches a simple query."""
    for key, value in query.items():
        actual = document.get(key)
        if isinstance(value, dict):
            if "$in" in value and actual not in value["$in"]:
                return False
            if "$ne" in value and actual == value["$ne"]:
                return False
        elif actual != value:
            return False
    return True


def _apply_projection(document: dict[str, Any], projection: dict[str, Any] | None) -> dict[str, Any]:
    """Apply a simple Mongo projection to a fake document."""
    projected = deepcopy(document)
    if not projection:
        return projected

    include_fields = {key for key, value in projection.items() if value}
    exclude_fields = {key for key, value in projection.items() if not value}

    if include_fields:
        result = {field: deepcopy(document[field]) for field in include_fields if field in document}
        if projection.get("_id", 1) and "_id" in document:
            result["_id"] = deepcopy(document["_id"])
        return result

    for field in exclude_fields:
        projected.pop(field, None)
    return projected


class FakeCursor:
    """Simple async cursor used by fake Mongo collections."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = deepcopy(documents)

    def sort(self, field: str, direction: int) -> "FakeCursor":
        reverse = direction == -1
        self.documents.sort(key=lambda item: item.get(field) or "", reverse=reverse)
        return self

    def skip(self, offset: int) -> "FakeCursor":
        self.documents = self.documents[offset:]
        return self

    def limit(self, limit: int) -> "FakeCursor":
        self.documents = self.documents[:limit]
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        if length is None:
            return deepcopy(self.documents)
        return deepcopy(self.documents[:length])

    def __aiter__(self):  # type: ignore[no-untyped-def]
        async def _iterate():
            for document in deepcopy(self.documents):
                yield document

        return _iterate()


class FakeCollection:
    """Minimal fake Mongo collection for API tests."""

    def __init__(
        self,
        documents: list[dict[str, Any]],
        *,
        allow_count_documents: bool = True,
    ) -> None:
        self.documents = deepcopy(documents)
        self.allow_count_documents = allow_count_documents
        self.last_find_projection: dict[str, Any] | None = None

    def find(
        self,
        query: dict[str, Any] | None = None,
        projection: dict[str, Any] | None = None,
    ) -> FakeCursor:
        query = query or {}
        self.last_find_projection = projection
        matches = [
            _apply_projection(document, projection)
            for document in self.documents
            if _matches(document, query)
        ]
        return FakeCursor(matches)

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    async def count_documents(self, query: dict[str, Any]) -> int:
        if not self.allow_count_documents:
            raise AssertionError("count_documents should not be used for this endpoint")
        return sum(1 for document in self.documents if _matches(document, query))

    def aggregate(self, pipeline: list[dict[str, Any]]) -> FakeCursor:
        documents = deepcopy(self.documents)

        if pipeline and "$match" in pipeline[0]:
            documents = [
                document for document in documents if _matches(document, pipeline[0]["$match"])
            ]
            pipeline = pipeline[1:]

        if pipeline and "$group" in pipeline[0]:
            group_field = pipeline[0]["$group"]["_id"].lstrip("$")
            counts: dict[Any, int] = {}
            for document in documents:
                key = document.get(group_field)
                counts[key] = counts.get(key, 0) + 1
            return FakeCursor([{"_id": key, "count": value} for key, value in counts.items()])

        return FakeCursor(documents)


class FakeRedisManager:
    """Simple fake Redis manager for stats endpoint tests."""

    def __init__(self, jobs: list[dict[str, Any]], *, is_available: bool = True) -> None:
        self.jobs = jobs
        self.is_available = is_available

    async def list_jobs(
        self,
        limit: int = 1000,
        offset: int = 0,
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        jobs = deepcopy(self.jobs)
        if status_filter is not None:
            jobs = [job for job in jobs if job.get("status") == status_filter]
        return jobs[offset : offset + limit]


def _seed_documents() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build seeded transcript, channel, and video metadata documents."""
    transcripts = [
        {
            "_id": "507f1f77bcf86cd799439011",
            "video_id": "ABCDEFGHIJK",
            "title": "Alpha Video",
            "channel_id": "UC_ALPHA",
            "channel_name": "Alpha Channel",
            "duration_seconds": 120.5,
            "language": "en",
            "transcript_source": "youtube_auto",
            "segment_count": 2,
            "total_text_length": 24,
            "source_type": "youtube",
            "source_url": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
            "segments": [
                {"start": 0.0, "end": 5.0, "text": "Hello"},
                {"start": 5.0, "end": 10.0, "text": "world"},
            ],
            "full_text": "Hello world from alpha",
            "created_at": "2026-04-08T12:00:00+00:00",
            "updated_at": "2026-04-08T12:05:00+00:00",
        },
        {
            "_id": "507f1f77bcf86cd799439012",
            "video_id": "LMNOPQRSTUV",
            "title": "Beta Video",
            "channel_id": "UC_BETA",
            "channel_name": "Beta Channel",
            "duration_seconds": 95.0,
            "language": "es",
            "transcript_source": "groq_whisper",
            "segment_count": 1,
            "total_text_length": 18,
            "source_type": "youtube",
            "source_url": "https://www.youtube.com/watch?v=LMNOPQRSTUV",
            "segments": [{"start": 0.0, "end": 8.0, "text": "Hola mundo"}],
            "full_text": "Hola mundo beta",
            "created_at": "2026-04-08T10:00:00+00:00",
            "updated_at": "2026-04-08T10:05:00+00:00",
        },
    ]

    channels = [
        {
            "_id": "channel-alpha",
            "channel_id": "UC_ALPHA",
            "channel_handle": "AlphaChannel",
            "channel_title": "Alpha Channel",
            "channel_url": "https://www.youtube.com/@AlphaChannel",
            "tracked_since": "2026-04-01T00:00:00+00:00",
        },
        {
            "_id": "channel-beta",
            "channel_id": "UC_BETA",
            "channel_handle": "BetaChannel",
            "channel_title": "Beta Channel",
            "channel_url": "https://www.youtube.com/@BetaChannel",
            "tracked_since": "2026-03-20T00:00:00+00:00",
        },
    ]

    video_metadata = [
        {
            "_id": "video-alpha-1",
            "video_id": "ABCDEFGHIJK",
            "channel_id": "UC_ALPHA",
            "title": "Alpha Video",
            "transcript_status": "completed",
            "published_at": "2026-04-07T00:00:00+00:00",
        },
        {
            "_id": "video-alpha-2",
            "video_id": "AAAAABBBBB1",
            "channel_id": "UC_ALPHA",
            "title": "Alpha Pending",
            "transcript_status": "pending",
            "published_at": "2026-04-06T00:00:00+00:00",
        },
        {
            "_id": "video-beta-1",
            "video_id": "CCCCCDDDDD2",
            "channel_id": "UC_BETA",
            "title": "Beta Failed",
            "transcript_status": "failed",
            "published_at": "2026-04-05T00:00:00+00:00",
        },
    ]
    return transcripts, channels, video_metadata


def _build_fake_db(*, allow_channel_count_documents: bool = True) -> Any:
    """Construct a fake Mongo database namespace for endpoint tests."""
    transcripts, channels, video_metadata = _seed_documents()
    return SimpleNamespace(
        transcripts=FakeCollection(transcripts),
        channels=FakeCollection(channels),
        video_metadata=FakeCollection(
            video_metadata,
            allow_count_documents=allow_channel_count_documents,
        ),
    )


def _override_dependencies(app: FastAPI, database: Any) -> None:
    """Install database overrides for a test app."""

    async def _get_db_override() -> Any:
        return database

    async def _get_db_manager_override() -> Any:
        return AsyncMock()

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_db_manager_dep] = _get_db_manager_override


@pytest.fixture
def seeded_api_db(app: FastAPI) -> Any:
    """Override database dependencies with seeded fake collections."""
    database = _build_fake_db()
    _override_dependencies(app, database)
    yield database
    app.dependency_overrides.clear()


class TestTranscriptListStabilization:
    """Test transcript listing stays lightweight."""

    def test_list_transcripts_returns_summary_only(
        self,
        client: TestClient,
        seeded_api_db: Any,
    ) -> None:
        """List endpoint should omit heavy transcript fields."""
        response = client.get("/api/v1/transcripts/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        assert "segments" not in data[0]
        assert "full_text" not in data[0]
        assert data[0]["segment_count"] == 2
        assert seeded_api_db.transcripts.last_find_projection == {"segments": 0, "full_text": 0}

    def test_get_transcript_returns_full_detail(
        self,
        client: TestClient,
        seeded_api_db: Any,
    ) -> None:
        """Detail endpoint should still include full transcript content."""
        response = client.get("/api/v1/transcripts/ABCDEFGHIJK")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "segments" in data
        assert "full_text" in data
        assert data["video_id"] == "ABCDEFGHIJK"


class TestChannelSyncValidation:
    """Test stricter sync endpoint validation."""

    def test_sync_channel_invalid_mode_returns_422(
        self,
        app: FastAPI,
        client: TestClient,
        seeded_api_db: Any,
    ) -> None:
        """Invalid sync mode should fail request validation."""
        response = client.post("/api/v1/channels/UC_ALPHA/sync?mode=invalid")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_sync_channel_all_requires_max_videos(
        self,
        client: TestClient,
        seeded_api_db: Any,
    ) -> None:
        """Full sync should require an explicit max_videos bound."""
        response = client.post("/api/v1/channels/UC_ALPHA/sync?mode=all")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_sync_all_channels_all_requires_bounds(
        self,
        client: TestClient,
        seeded_api_db: Any,
    ) -> None:
        """Bulk full sync should require channel and video bounds."""
        response = client.post("/api/v1/channels/sync-all?mode=all&max_channels=1")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_add_channels_from_videos_requires_sync_bound_for_full_sync(
        self,
        client: TestClient,
    ) -> None:
        """Auto-sync full channel imports should require a per-channel bound."""
        response = client.post(
            "/api/v1/channels/from-videos",
            json={
                "video_urls": ["https://www.youtube.com/watch?v=ABCDEFGHIJK"],
                "auto_sync": True,
                "sync_mode": "all",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_sync_channel_missing_handle_returns_400(
        self,
        app: FastAPI,
        client: TestClient,
    ) -> None:
        """Missing channel handle should not be wrapped into a 500."""
        database = SimpleNamespace(
            transcripts=FakeCollection([]),
            channels=FakeCollection(
                [
                    {
                        "_id": "channel-no-handle",
                        "channel_id": "UC_NOHANDLE",
                        "channel_handle": "",
                        "channel_title": "No Handle",
                        "channel_url": "https://www.youtube.com/channel/UC_NOHANDLE",
                    }
                ]
            ),
            video_metadata=FakeCollection([]),
        )
        _override_dependencies(app, database)

        response = client.post("/api/v1/channels/UC_NOHANDLE/sync?mode=recent")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        app.dependency_overrides.clear()


class TestReadPathOptimizations:
    """Test optimized read-only endpoints."""

    def test_list_channels_uses_aggregate_video_counts(
        self,
        app: FastAPI,
        client: TestClient,
    ) -> None:
        """Channel listing should not execute count_documents per row."""
        database = _build_fake_db(allow_channel_count_documents=False)
        _override_dependencies(app, database)

        response = client.get("/api/v1/channels/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        counts = {entry["channel_id"]: entry["video_count"] for entry in data}
        assert counts["UC_ALPHA"] == 2
        assert counts["UC_BETA"] == 1
        app.dependency_overrides.clear()

    def test_stats_endpoint_uses_seeded_counts(
        self,
        client: TestClient,
        seeded_api_db: Any,
    ) -> None:
        """Stats endpoint should aggregate seeded Mongo and Redis data correctly."""
        redis_manager = FakeRedisManager(
            [
                {"job_id": "job-1", "status": "queued"},
                {"job_id": "job-2", "status": "processing"},
                {"job_id": "job-3", "status": "completed"},
            ]
        )

        with patch("src.api.routers.stats.get_redis_manager", return_value=redis_manager):
            response = client.get("/api/v1/stats/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_channels"] == 2
        assert data["total_videos"] == 3
        assert data["total_transcripts"] == 2
        assert data["videos_pending"] == 1
        assert data["videos_completed"] == 1
        assert data["videos_failed"] == 1
        assert data["transcripts_by_source"] == {"youtube_auto": 1, "groq_whisper": 1}
        assert data["active_jobs"] == 2
        assert data["redis_available"] is True


class TestNonMutatingSmoke:
    """Smoke-test non-mutating routes with seeded data."""

    @pytest.mark.parametrize(
        ("path", "patch_redis"),
        [
            ("/docs", False),
            ("/openapi.json", False),
            ("/health", False),
            ("/api/v1/stats/", True),
            ("/api/v1/transcripts/", False),
            ("/api/v1/channels/", False),
        ],
    )
    def test_non_mutating_endpoints_smoke(
        self,
        path: str,
        patch_redis: bool,
        client: TestClient,
        seeded_api_db: Any,
    ) -> None:
        """Public docs and read-only API routes should respond successfully."""
        if patch_redis:
            with patch(
                "src.api.routers.stats.get_redis_manager",
                return_value=FakeRedisManager([]),
            ):
                response = client.get(path)
        else:
            response = client.get(path)

        assert response.status_code == status.HTTP_200_OK
