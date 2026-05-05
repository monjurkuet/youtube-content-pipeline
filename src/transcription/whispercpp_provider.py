"""Whisper.cpp local server transcription provider.

Adapter for the whisper.cpp HTTP server running at localhost:8334.
Unlike the Groq cloud API, this provider has:
- No API key requirement
- No rate limits
- No file size limit (local server handles long files natively)
- No chunking needed

API reference:
- Health check: GET /health → {"status": "ok"}
- Transcription: POST /inference with multipart form:
    - file: audio file
    - language: language code (e.g. "en")
    - response_format: "json" | "verbose_json"
- verbose_json returns segments with start/end timestamps and word-level detail.
"""

import logging
from pathlib import Path

import requests

from src.core.exceptions import WhisperError
from src.core.schemas import RawTranscript, TranscriptSegment

logger = logging.getLogger(__name__)

# Default whisper.cpp server settings
DEFAULT_BASE_URL = "http://localhost:8334"
DEFAULT_TIMEOUT_SEC = 600  # Local inference can be slow on long files


class WhisperCppProvider:
    """Transcription using a local whisper.cpp HTTP server."""

    name = "whispercpp_local"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ):
        self.base_url = base_url.rstrip("/")
        self.inference_url = f"{self.base_url}/inference"
        self.health_url = f"{self.base_url}/health"
        self.timeout_sec = timeout_sec

    def is_available(self) -> bool:
        """Check if the whisper.cpp server is reachable.

        Returns:
            True if the server responds to /health with status 200.
        """
        try:
            response = requests.get(self.health_url, timeout=5)
            return response.status_code == 200
        except (requests.ConnectionError, requests.Timeout):
            return False

    def transcribe(self, audio_path: str, language: str = "en") -> RawTranscript:
        """Transcribe an audio file via the whisper.cpp /inference endpoint.

        Args:
            audio_path: Path to the audio file to transcribe.
            language: Language code for transcription (default: "en").

        Returns:
            RawTranscript with segments containing text, start time, and duration.

        Raises:
            WhisperError: If the server returns an error or the file cannot be read.
        """
        path = Path(audio_path)
        if not path.exists():
            raise WhisperError(f"Audio file not found: {path}")

        with open(path, "rb") as f:
            files = {"file": (path.name, f, f"audio/{path.suffix.lstrip('.')}")}
            data = {
                "language": language,
                "response_format": "verbose_json",
            }
            try:
                response = requests.post(
                    self.inference_url,
                    files=files,
                    data=data,
                    timeout=self.timeout_sec,
                )
            except requests.ConnectionError as exc:
                raise WhisperError(
                    f"whisper.cpp server at {self.base_url} is not reachable: {exc}"
                ) from exc
            except requests.Timeout as exc:
                raise WhisperError(
                    f"whisper.cpp request timed out after {self.timeout_sec}s: {exc}"
                ) from exc

        if response.status_code != 200:
            raise WhisperError(
                f"whisper.cpp error {response.status_code}: {response.text[:200]}"
            )

        return self._parse_response(response.json(), language)

    def _parse_response(
        self, result: dict, language: str
    ) -> RawTranscript:
        """Parse whisper.cpp verbose_json response into RawTranscript.

        The verbose_json format returns:
        {
            "text": "full transcript...",
            "language": "en",
            "segments": [
                {
                    "text": " segment text",
                    "start": 0.0,
                    "end": 5.2,
                    "words": [{"word": "...", "start": ..., "end": ...}, ...]
                },
                ...
            ]
        }

        Args:
            result: Parsed JSON response from whisper.cpp.
            language: Fallback language if not in response.

        Returns:
            RawTranscript with normalized segments.
        """
        segments = []
        for seg in result.get("segments", []):
            text = seg.get("text", "").strip()
            if not text:
                continue
            start = seg.get("start", 0.0)
            end = seg.get("end", 0.0)
            segments.append(
                TranscriptSegment(
                    text=text,
                    start=start,
                    duration=end - start,
                )
            )

        # If no segments were returned, try the top-level text field
        if not segments and result.get("text", "").strip():
            full_text = result["text"].strip()
            # Strip whisper.cpp markers like [BLANK_AUDIO]
            if full_text and full_text != "[BLANK_AUDIO]":
                segments.append(
                    TranscriptSegment(
                        text=full_text,
                        start=0.0,
                        duration=0.0,
                    )
                )

        return RawTranscript(
            video_id="",
            segments=segments,
            source="whispercpp_local",
            language=result.get("language", language),
        )
