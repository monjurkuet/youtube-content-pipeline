"""Tests for transcription job failure handling and retries."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.constants import JobStatus
from src.core.exceptions import TranscriptionFailureError
from src.core.schemas import RawTranscript, TranscriptSegment
from src.transcription.failures import create_failure
import src.services.transcription_service as transcription_service


@pytest.fixture(autouse=True)
def in_memory_job_store():
    """Run transcription service tests against the in-memory job store."""
    original_redis_manager = transcription_service._redis_manager
    original_jobs = dict(transcription_service._jobs_memory)
    transcription_service._redis_manager = SimpleNamespace(is_available=False)
    transcription_service._jobs_memory.clear()

    try:
        yield
    finally:
        transcription_service._jobs_memory.clear()
        transcription_service._jobs_memory.update(original_jobs)
        transcription_service._redis_manager = original_redis_manager


class TestJobNormalization:
    """Test job normalization helpers."""

    def test_normalize_job_payload_uses_legacy_error_field(self):
        """Legacy jobs should expose error_message without losing error."""
        normalized = transcription_service.normalize_job_payload(
            {
                "job_id": "job-1",
                "video_id": "video-1",
                "status": "failed",
                "error": "legacy boom",
            }
        )

        assert normalized["error_message"] == "legacy boom"
        assert normalized["error"] == "legacy boom"
        assert normalized["retryable"] is False
        assert normalized["failed_stage"] is None


class TestBackgroundProcessing:
    """Test background job retry and failure persistence behavior."""

    @pytest.mark.asyncio
    async def test_retryable_failure_retries_before_final_failure(self):
        """Retryable acquisition failures should consume the full retry budget."""
        job_id = "job_retry_test"
        await transcription_service.set_job(
            job_id,
            {
                "job_id": job_id,
                "video_id": "dQw4w9WgXcQ",
                "status": JobStatus.QUEUED,
                "progress_percent": 0.0,
                "current_step": "Queued for processing",
                "created_at": datetime.now(timezone.utc),
            },
        )

        failure = create_failure(
            "Temporary YouTube block",
            "temporary_block",
            "download",
            video_id="dQw4w9WgXcQ",
        )

        mock_pipeline = MagicMock()
        mock_pipeline.acquire_transcript.side_effect = TranscriptionFailureError(failure)

        mock_db = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.__aenter__.return_value = mock_db
        mock_manager.__aexit__.return_value = None

        with patch(
            "src.services.transcription_service.TranscriptPipeline",
            return_value=mock_pipeline,
        ), patch(
            "src.services.transcription_service.MongoDBManager",
            return_value=mock_manager,
        ), patch(
            "src.services.transcription_service.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep_mock:
            await transcription_service.process_video_transcription(
                job_id,
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "dQw4w9WgXcQ",
                "youtube",
                "dQw4w9WgXcQ",
                webhook_url=None,
                save_to_db=True,
            )

        job = await transcription_service.get_job(job_id)
        assert job is not None
        assert job["status"] == JobStatus.FAILED
        assert job["error_message"] == "Temporary YouTube block"
        assert job["error_category"] == "temporary_block"
        assert job["retryable"] is True
        assert job["failed_stage"] == "download"
        assert mock_pipeline.acquire_transcript.call_count == 3
        assert sleep_mock.await_count == 2
        mock_db.mark_transcript_failed.assert_awaited_once_with(
            "dQw4w9WgXcQ",
            "Temporary YouTube block",
            "temporary_block",
        )

    @pytest.mark.asyncio
    async def test_permanent_failure_does_not_retry(self):
        """Permanent failures should fail immediately without sleeps."""
        job_id = "job_permanent_test"
        await transcription_service.set_job(
            job_id,
            {
                "job_id": job_id,
                "video_id": "dQw4w9WgXcQ",
                "status": JobStatus.QUEUED,
                "progress_percent": 0.0,
                "current_step": "Queued for processing",
                "created_at": datetime.now(timezone.utc),
            },
        )

        failure = create_failure(
            "Video is private",
            "private",
            "download",
            video_id="dQw4w9WgXcQ",
            retryable=False,
        )

        mock_pipeline = MagicMock()
        mock_pipeline.acquire_transcript.side_effect = TranscriptionFailureError(failure)

        mock_db = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.__aenter__.return_value = mock_db
        mock_manager.__aexit__.return_value = None

        with patch(
            "src.services.transcription_service.TranscriptPipeline",
            return_value=mock_pipeline,
        ), patch(
            "src.services.transcription_service.MongoDBManager",
            return_value=mock_manager,
        ), patch(
            "src.services.transcription_service.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep_mock:
            await transcription_service.process_video_transcription(
                job_id,
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "dQw4w9WgXcQ",
                "youtube",
                "dQw4w9WgXcQ",
                webhook_url=None,
                save_to_db=True,
            )

        job = await transcription_service.get_job(job_id)
        assert job is not None
        assert job["status"] == JobStatus.FAILED
        assert job["error_category"] == "private"
        assert mock_pipeline.acquire_transcript.call_count == 1
        sleep_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_webhook_payload_includes_structured_failure_fields(self):
        """Webhook payloads should include the new failure contract."""
        job_payload = transcription_service.normalize_job_payload(
            {
                "job_id": "job_webhook_test",
                "status": JobStatus.FAILED,
                "video_id": "dQw4w9WgXcQ",
                "error_message": "Timed out downloading audio",
                "error_category": "timeout",
                "retryable": True,
                "failed_stage": "download",
            }
        )

        response = MagicMock()
        response.raise_for_status.return_value = None
        client = AsyncMock()
        client.post.return_value = response
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None

        with patch("src.services.transcription_service.httpx.AsyncClient", return_value=client):
            await transcription_service.send_webhook("https://example.com/webhook", job_payload)

        client.post.assert_awaited_once()
        payload = client.post.await_args.kwargs["json"]
        assert payload["error_message"] == "Timed out downloading audio"
        assert payload["error_category"] == "timeout"
        assert payload["retryable"] is True
        assert payload["failed_stage"] == "download"
        assert payload["error"] == "Timed out downloading audio"

    @pytest.mark.asyncio
    async def test_successful_job_still_persists_transcript(self):
        """Successful jobs should still persist the transcript and complete cleanly."""
        job_id = "job_success_test"
        await transcription_service.set_job(
            job_id,
            {
                "job_id": job_id,
                "video_id": "dQw4w9WgXcQ",
                "status": JobStatus.QUEUED,
                "progress_percent": 0.0,
                "current_step": "Queued for processing",
                "created_at": datetime.now(timezone.utc),
            },
        )

        raw_transcript = RawTranscript(
            video_id="dQw4w9WgXcQ",
            segments=[TranscriptSegment(text="hello", start=0.0, duration=1.0)],
            source="youtube_api",
            language="en",
        )

        mock_pipeline = MagicMock()
        mock_pipeline.acquire_transcript.return_value = raw_transcript
        mock_pipeline.persist_transcript.return_value = "transcript-123"

        with patch(
            "src.services.transcription_service.TranscriptPipeline",
            return_value=mock_pipeline,
        ):
            await transcription_service.process_video_transcription(
                job_id,
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "dQw4w9WgXcQ",
                "youtube",
                "dQw4w9WgXcQ",
                webhook_url=None,
                save_to_db=True,
            )

        job = await transcription_service.get_job(job_id)
        assert job is not None
        assert job["status"] == JobStatus.COMPLETED
        assert job["error_message"] is None
        mock_pipeline.persist_transcript.assert_called_once()
