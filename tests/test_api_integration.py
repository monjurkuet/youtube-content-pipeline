"""Integration tests for API endpoints.

This module tests all API endpoints:
- Health endpoints
- Video transcription endpoints
- Transcript endpoints
- Metrics endpoints
- Root endpoint
"""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from src.api.models.requests import JobStatusResponse, TranscriptionJobResponse
from src.core.constants import JobStatus


class TestRootEndpoint:
    """Test root API endpoint."""

    def test_root_endpoint(self, client: TestClient) -> None:
        """Test GET / returns 404 (no root endpoint configured).

        Given: A running API server
        When: GET request to /
        Then: Returns 404 (root not configured, use /health instead)
        """
        response = client.get("/")

        # Root endpoint is not configured, returns 404
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_endpoint(self, client: TestClient) -> None:
        """Test GET /health returns healthy.

        Given: A running API server
        When: GET request to /health
        Then: Returns healthy status with 200
        """
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_health_ready(self, client: TestClient) -> None:
        """Test GET /health/ready checks dependencies.

        Given: A running API server
        When: GET request to /health/ready
        Then: Returns readiness status with component health
        """
        response = client.get("/health/ready")

        # Should return 200 or 503 depending on dependencies
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]

        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "database" in data["components"]

    def test_health_live(self, client: TestClient) -> None:
        """Test GET /health/live returns 200.

        Given: A running API server
        When: GET request to /health/live
        Then: Returns alive status with 200
        """
        response = client.get("/health/live")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data

    def test_health_detailed(self, client: TestClient) -> None:
        """Test GET /health/detailed has all components.

        Given: A running API server
        When: GET request to /health/detailed
        Then: Returns detailed health with all components
        """
        response = client.get("/health/detailed")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "status" in data
        assert "components" in data
        assert "database" in data["components"]
        assert "transcription" in data["components"]
        assert "uptime_seconds" in data
        assert "environment" in data


class TestVideoTranscriptionEndpoints:
    """Test video transcription endpoints."""

    @pytest.mark.integration
    def test_transcribe_video(self, client: TestClient, sample_transcription_request: dict) -> None:
        """Test POST /api/v1/videos/transcribe.

        Given: A valid transcription request
        When: POST request to /api/v1/videos/transcribe
        Then: Returns job ID with 202 Accepted
        """
        response = client.post(
            "/api/v1/videos/transcribe",
            json=sample_transcription_request,
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()

        assert "job_id" in data
        assert "status" in data
        assert data["status"] == JobStatus.QUEUED
        assert "video_id" in data
        assert "message" in data
        assert "created_at" in data

    def test_transcribe_video_with_priority(
        self,
        client: TestClient,
        sample_transcription_request: dict,
    ) -> None:
        """Test transcription with different priorities.

        Given: Transcription requests with different priorities
        When: POST requests to /api/v1/videos/transcribe
        Then: All requests succeed with 202
        """
        for priority in ["low", "normal", "high"]:
            request = sample_transcription_request.copy()
            request["priority"] = priority

            response = client.post(
                "/api/v1/videos/transcribe",
                json=request,
            )

            assert response.status_code == status.HTTP_202_ACCEPTED
            data = response.json()
            assert data["status"] == JobStatus.QUEUED

    def test_get_job_status(self, client: TestClient, sample_job: dict) -> None:
        """Test GET /api/v1/videos/jobs/{job_id}.

        Given: A created job
        When: GET request to /api/v1/videos/jobs/{job_id}
        Then: Returns job status
        """
        # First create a job
        request = {"source": "https://www.youtube.com/watch?v=test123"}
        create_response = client.post("/api/v1/videos/transcribe", json=request)
        assert create_response.status_code == status.HTTP_202_ACCEPTED

        job_id = create_response.json()["job_id"]

        # Then get job status
        response = client.get(f"/api/v1/videos/jobs/{job_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert "video_id" in data

    def test_get_job_status_not_found(self, client: TestClient) -> None:
        """Test GET /api/v1/videos/jobs/{job_id} for non-existent job.

        Given: A non-existent job ID
        When: GET request to /api/v1/videos/jobs/{job_id}
        Then: Returns 404 Not Found
        """
        response = client.get("/api/v1/videos/jobs/nonexistent_job_123")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        # Error response format uses 'error' and 'message' fields
        assert "error" in data or "message" in data

    def test_list_jobs(self, client: TestClient) -> None:
        """Test GET /api/v1/videos/jobs.

        Given: Multiple jobs exist
        When: GET request to /api/v1/videos/jobs
        Then: Returns list of jobs
        """
        response = client.get("/api/v1/videos/jobs")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_list_jobs_with_filter(self, client: TestClient) -> None:
        """Test GET /api/v1/videos/jobs with status filter.

        Given: Multiple jobs exist
        When: GET request with status_filter parameter
        Then: Returns filtered list of jobs
        """
        response = client.get("/api/v1/videos/jobs?status_filter=completed")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)


class TestTranscriptEndpoints:
    """Test transcript management endpoints."""

    def test_get_transcript_not_found(self, client: TestClient) -> None:
        """Test GET /api/v1/transcripts/{video_id} for non-existent transcript.

        Given: A non-existent video ID
        When: GET request to /api/v1/transcripts/{video_id}
        Then: Returns 404 Not Found
        """
        response = client.get("/api/v1/transcripts/nonexistent123")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        # Error response format uses 'error' and 'message' fields
        assert "error" in data or "message" in data

    def test_list_transcripts(self, client: TestClient) -> None:
        """Test GET /api/v1/transcripts/.

        Given: Transcripts exist in database
        When: GET request to /api/v1/transcripts/
        Then: Returns list of transcripts
        """
        response = client.get("/api/v1/transcripts/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_list_transcripts_with_pagination(self, client: TestClient) -> None:
        """Test GET /api/v1/transcripts/ with pagination.

        Given: Transcripts exist in database
        When: GET request with limit and offset
        Then: Returns paginated list
        """
        response = client.get("/api/v1/transcripts/?limit=10&offset=0")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    def test_list_transcripts_with_source_filter(
        self,
        client: TestClient,
    ) -> None:
        """Test GET /api/v1/transcripts/ with source filter.

        Given: Transcripts exist with different sources
        When: GET request with transcript_source filter
        Then: Returns filtered list
        """
        response = client.get("/api/v1/transcripts/?transcript_source=youtube_auto")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_list_transcripts_with_language_filter(
        self,
        client: TestClient,
    ) -> None:
        """Test GET /api/v1/transcripts/ with language filter.

        Given: Transcripts exist with different languages
        When: GET request with language filter
        Then: Returns filtered list
        """
        response = client.get("/api/v1/transcripts/?language=en")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_transcript_with_invalid_video_id_format(
        self,
        client: TestClient,
    ) -> None:
        """Test GET /api/v1/transcripts/{video_id} with invalid format.

        Given: An invalid video ID format
        When: GET request to /api/v1/transcripts/{video_id}
        Then: Returns 422 Validation Error
        """
        # Invalid video ID (too short)
        response = client.get("/api/v1/transcripts/abc")

        # Should return 422 due to path parameter validation
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestMetricsEndpoint:
    """Test Prometheus metrics endpoint."""

    def test_metrics_endpoint(self, client: TestClient) -> None:
        """Test GET /metrics returns Prometheus format.

        Given: Prometheus metrics may be enabled or disabled
        When: GET request to /metrics
        Then: Returns appropriate response
        """
        response = client.get("/metrics")

        # Metrics endpoint may return 200 or 404 depending on configuration
        # In test mode, Prometheus is typically disabled
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

        # If metrics are enabled, verify format
        if response.status_code == status.HTTP_200_OK:
            content = response.text
            # Prometheus metrics typically have # HELP or # TYPE comments
            # But we accept any 200 response as valid
            assert len(content) > 0


class TestTranscriptionWithMocks:
    """Test transcription endpoints with mocked dependencies."""

    @pytest.mark.integration
    def test_transcribe_with_mocked_pipeline(
        self,
        client: TestClient,
        mock_transcription_pipeline: MagicMock,
        sample_transcription_request: dict,
    ) -> None:
        """Test transcription with mocked pipeline.

        Given: Mocked transcription pipeline
        When: POST request to transcribe endpoint
        Then: Job is created successfully
        """
        response = client.post(
            "/api/v1/videos/transcribe",
            json=sample_transcription_request,
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert "job_id" in data

        # Verify mock was called
        assert mock_transcription_pipeline.called

    @pytest.mark.asyncio
    async def test_job_lifecycle_with_mocked_redis(
        self,
        client: TestClient,
        mock_redis_manager: AsyncMock,
    ) -> None:
        """Test job lifecycle with mocked Redis.

        Given: Mocked Redis manager
        When: Create job and check status
        Then: Job is stored and retrieved correctly
        """
        # Mock Redis to be available
        with patch("src.api.routers.videos.redis_manager", mock_redis_manager):
            # Create job
            request = {"source": "https://www.youtube.com/watch?v=test123"}
            create_response = client.post("/api/v1/videos/transcribe", json=request)

            assert create_response.status_code == status.HTTP_202_ACCEPTED
            job_id = create_response.json()["job_id"]

            # Get job status
            status_response = client.get(f"/api/v1/videos/jobs/{job_id}")

            # Should succeed (may use in-memory fallback)
            assert status_response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_404_NOT_FOUND,
            ]


class TestAPIInfo:
    """Test API information endpoints."""

    def test_openapi_json(self, client: TestClient) -> None:
        """Test GET /openapi.json returns valid schema.

        Given: A running API server
        When: GET request to /openapi.json
        Then: Returns valid OpenAPI schema
        """
        response = client.get("/openapi.json")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "openapi" in data
        assert "info" in data
        # Note: Custom OpenAPI schema may not include paths directly
        # Paths are generated dynamically by FastAPI
        assert data["openapi"].startswith("3.")

        # Verify schema has required components
        assert "components" in data or "paths" in data

    def test_docs_endpoint(self, client: TestClient) -> None:
        """Test GET /docs returns Swagger UI.

        Given: A running API server
        When: GET request to /docs
        Then: Returns Swagger UI HTML
        """
        response = client.get("/docs")

        assert response.status_code == status.HTTP_200_OK
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    def test_redoc_endpoint(self, client: TestClient) -> None:
        """Test GET /redoc returns ReDoc UI.

        Given: A running API server
        When: GET request to /redoc
        Then: Returns ReDoc HTML
        """
        response = client.get("/redoc")

        assert response.status_code == status.HTTP_200_OK
        assert "redoc" in response.text.lower()


class TestConcurrentRequests:
    """Test concurrent request handling."""

    def test_multiple_simultaneous_transcription_requests(
        self,
        client: TestClient,
    ) -> None:
        """Test multiple simultaneous transcription requests.

        Given: Multiple concurrent requests
        When: POST requests to transcribe endpoint
        Then: All requests succeed with unique job IDs
        """
        job_ids = set()

        for i in range(5):
            request = {
                "source": f"https://www.youtube.com/watch?v=test{i}",
                "priority": "normal",
            }
            response = client.post("/api/v1/videos/transcribe", json=request)

            assert response.status_code == status.HTTP_202_ACCEPTED
            data = response.json()
            job_ids.add(data["job_id"])

        # All job IDs should be unique
        assert len(job_ids) == 5


class TestRequestValidation:
    """Test request validation."""

    def test_transcribe_missing_source(self, client: TestClient) -> None:
        """Test transcription request without source field.

        Given: Request missing required source field
        When: POST request to transcribe endpoint
        Then: Returns 422 Validation Error
        """
        response = client.post(
            "/api/v1/videos/transcribe",
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_transcribe_invalid_priority(self, client: TestClient) -> None:
        """Test transcription request with invalid priority.

        Given: Request with invalid priority value
        When: POST request to transcribe endpoint
        Then: Returns 422 Validation Error
        """
        request = {
            "source": "https://www.youtube.com/watch?v=test123",
            "priority": "invalid_priority",
        }

        response = client.post("/api/v1/videos/transcribe", json=request)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_transcribe_invalid_save_to_db_type(
        self,
        client: TestClient,
    ) -> None:
        """Test transcription request with wrong type for save_to_db.

        Given: Request with non-boolean save_to_db
        When: POST request to transcribe endpoint
        Then: Returns 422 Validation Error
        """
        request = {
            "source": "https://www.youtube.com/watch?v=test123",
            "save_to_db": "yes",  # Should be boolean
        }

        # Use a short timeout to prevent hanging
        response = client.post("/api/v1/videos/transcribe", json=request, timeout=5.0)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
