"""Tests for API models."""

from datetime import datetime, timezone

from src.api.models.requests import (
    JobStatusResponse,
    TranscriptionJobResponse,
    TranscriptionRequest,
)


class TestTranscriptionRequest:
    """Test TranscriptionRequest model."""

    def test_valid_request(self):
        """Test valid request."""
        request = TranscriptionRequest(source="https://www.youtube.com/watch?v=test123")
        assert request.source == "https://www.youtube.com/watch?v=test123"
        assert request.priority == "normal"
        assert request.save_to_db is True

    def test_with_webhook(self):
        """Test request with webhook."""
        request = TranscriptionRequest(
            source="https://www.youtube.com/watch?v=test123",
            webhook_url="https://example.com/webhook",
            priority="high",
        )
        assert request.webhook_url == "https://example.com/webhook"
        assert request.priority == "high"


class TestTranscriptionJobResponse:
    """Test TranscriptionJobResponse model."""

    def test_response(self):
        """Test job response."""
        response = TranscriptionJobResponse(
            job_id="job_test123",
            status="queued",
            video_id="test123",
            message="Job queued",
            created_at=datetime.now(timezone.utc),
        )
        assert response.job_id == "job_test123"
        assert response.status == "queued"


class TestJobStatusResponse:
    """Test JobStatusResponse model."""

    def test_completed_status(self):
        """Test completed job status."""
        response = JobStatusResponse(
            job_id="job_test123",
            status="completed",
            video_id="test123",
            progress_percent=100.0,
            result_url="/api/v1/transcripts/test123",
        )
        assert response.status == "completed"
        assert response.progress_percent == 100.0

    def test_failed_status(self):
        """Test failed job status."""
        response = JobStatusResponse(
            job_id="job_test123",
            status="failed",
            video_id="test123",
            progress_percent=50.0,
            error_message="Download failed",
        )
        assert response.status == "failed"
        assert response.error_message == "Download failed"
