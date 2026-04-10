"""Local transcript service provider."""

import logging
import time
from pathlib import Path
from typing import Any

import requests

from src.core.config import get_settings_with_yaml
from src.core.exceptions import WhisperError
from src.core.schemas import RawTranscript, TranscriptSegment

logger = logging.getLogger(__name__)


class LocalTranscriptServiceProvider:
    """Transcription provider backed by the local transcript service."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings_with_yaml()
        self.base_url = self.settings.transcript_service_base_url.rstrip("/")
        self.api_key = self.settings.transcript_service_api_key
        self.model = self.settings.groq_whisper_model
        self.chunk_duration = self.settings.groq_chunk_duration
        self.chunk_overlap = self.settings.groq_chunk_overlap
        self.poll_interval = self.settings.transcript_service_poll_interval_sec
        self.timeout_sec = self.settings.transcript_service_timeout_sec

        if not self.api_key:
            raise WhisperError("TRANSCRIPT_SERVICE_API_KEY not configured")

    def transcribe(self, audio_path: str, language: str = "en") -> RawTranscript:
        """Upload audio to the local transcript service and wait for the result."""
        path = Path(audio_path)
        if not path.exists():
            raise WhisperError(f"Audio file not found: {path}")

        job_id = self._create_job(path)
        result = self._wait_for_result(job_id)
        transcript = result.get("transcript", {})
        segments = [
            TranscriptSegment(
                text=segment.get("text", "").strip(),
                start=float(segment.get("start", 0.0)),
                duration=float(segment.get("end", 0.0)) - float(segment.get("start", 0.0)),
            )
            for segment in transcript.get("segments", [])
        ]

        return RawTranscript(
            video_id="",
            segments=segments,
            source="local_service",
            language=language,
        )

    def _headers(self) -> dict[str, str]:
        """Return authenticated request headers."""
        return {"X-API-Key": self.api_key}

    def _create_job(self, audio_path: Path) -> str:
        """Create a remote transcription job."""
        url = f"{self.base_url}/v1/jobs"
        with open(audio_path, "rb") as handle:
            files = {"file": (audio_path.name, handle, f"audio/{audio_path.suffix.lstrip('.')}")}
            data = {
                "model": self.model,
                "chunk_duration_sec": str(self.chunk_duration),
                "chunk_overlap_sec": str(self.chunk_overlap),
            }
            response = requests.post(
                url,
                headers=self._headers(),
                files=files,
                data=data,
                timeout=self.timeout_sec,
            )

        if response.status_code != 202:
            raise WhisperError(
                f"Local transcript service create-job error {response.status_code}: {response.text}"
            )

        payload = response.json()
        job_id = payload.get("job", {}).get("id")
        if not job_id:
            raise WhisperError("Local transcript service did not return a job id")
        return job_id

    def _wait_for_result(self, job_id: str) -> dict[str, Any]:
        """Poll for the remote transcript result until it succeeds or fails."""
        deadline = time.monotonic() + self.timeout_sec
        status_url = f"{self.base_url}/v1/jobs/{job_id}"
        result_url = f"{self.base_url}/v1/jobs/{job_id}/result"

        while time.monotonic() < deadline:
            status_response = requests.get(
                status_url,
                headers=self._headers(),
                timeout=self.timeout_sec,
            )

            if status_response.status_code != 200:
                raise WhisperError(
                    f"Local transcript service status error {status_response.status_code}: {status_response.text}"
                )

            status_payload = status_response.json()
            status = status_payload.get("job", {}).get("status")

            if status == "succeeded":
                result_response = requests.get(
                    result_url,
                    headers=self._headers(),
                    timeout=self.timeout_sec,
                )
                if result_response.status_code != 200:
                    raise WhisperError(
                        f"Local transcript service result error {result_response.status_code}: {result_response.text}"
                    )
                return result_response.json()

            if status in {"failed", "cancelled"}:
                error_message = status_payload.get("job", {}).get("error") or "unknown remote error"
                raise WhisperError(f"Local transcript service job failed: {error_message}")

            time.sleep(self.poll_interval)

        raise WhisperError(
            f"Local transcript service timed out waiting for job {job_id} after {self.timeout_sec}s"
        )
