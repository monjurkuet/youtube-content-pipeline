"""Groq Whisper API transcription provider."""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import requests
from src.core.config import get_settings
from src.core.exceptions import WhisperError
from src.core.schemas import RawTranscript, TranscriptSegment

logger = logging.getLogger(__name__)

# Groq API settings
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_MODEL = "whisper-large-v3"
RESPONSE_FORMAT = "verbose_json"
TIMESTAMP_GRANULARITIES = ["segment"]

# Chunk settings
CHUNK_DURATION_SEC = 600  # 10 minutes
CHUNK_OVERLAP_SEC = 5  # 5 seconds overlap
MAX_FILE_SIZE_MB = 25  # Groq free tier limit


class GroqTranscriptionProvider:
    """Transcription using Groq Whisper API."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.api_key = self._load_api_key()
        self.model = getattr(self.settings, 'groq_whisper_model', DEFAULT_MODEL)
        self.chunk_duration = getattr(self.settings, 'groq_chunk_duration', CHUNK_DURATION_SEC)
        self.chunk_overlap = getattr(self.settings, 'groq_chunk_overlap', CHUNK_OVERLAP_SEC)
        self.max_file_size_mb = getattr(self.settings, 'groq_max_file_size_mb', MAX_FILE_SIZE_MB)

    def _load_api_key(self) -> str:
        """Load Groq API key from settings or environment."""
        # Try settings first
        api_key = getattr(self.settings, 'groq_api_key', None)
        if api_key:
            return api_key
        
        # Fallback to environment variable
        api_key = os.getenv('GROQ_API_KEY')
        if api_key:
            return api_key
        
        raise WhisperError("GROQ_API_KEY not configured")

    def transcribe(self, audio_path: str, language: str = "en") -> RawTranscript:
        """Transcribe audio file using Groq Whisper API."""
        audio_path = Path(audio_path)
        
        if not audio_path.exists():
            raise WhisperError(f"Audio file not found: {audio_path}")
        
        # Check file size
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        logger.info(f"Audio file size: {file_size_mb:.1f} MB")
        
        if file_size_mb > self.max_file_size_mb:
            logger.info(f"File exceeds {self.max_file_size_mb}MB, using chunking...")
            return self._transcribe_with_chunking(audio_path, language)
        else:
            return self._transcribe_standard(audio_path, language)

    def _transcribe_standard(self, audio_path: Path, language: str) -> RawTranscript:
        """Standard transcription without chunking."""
        url = GROQ_API_URL
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, f"audio/{audio_path.suffix[1:]}")}
            data = {
                "model": self.model,
                "response_format": RESPONSE_FORMAT,
                "timestamp_granularities[]": TIMESTAMP_GRANULARITIES,
                "language": language,
            }
            
            response = requests.post(url, files=files, data=data, headers=headers, timeout=300)
            
            if response.status_code != 200:
                raise WhisperError(f"Groq API error {response.status_code}: {response.text}")
            
            result = response.json()
            return self._parse_response(result, language)

    def _transcribe_with_chunking(self, audio_path: Path, language: str) -> RawTranscript:
        """Transcribe with automatic chunking for large files."""
        # Get audio duration
        duration = self._get_audio_duration(audio_path)
        logger.info(f"Audio duration: {duration / 60:.1f} minutes")
        
        # Create chunks
        with tempfile.TemporaryDirectory() as chunk_dir:
            chunk_dir = Path(chunk_dir)
            chunk_paths = self._chunk_audio(audio_path, chunk_dir)
            logger.info(f"Created {len(chunk_paths)} chunks")
            
            # Transcribe each chunk
            chunk_results = []
            for i, chunk_path in enumerate(chunk_paths):
                logger.info(f"Transcribing chunk {i + 1}/{len(chunk_paths)}")
                result = self._transcribe_standard(chunk_path, language)
                chunk_results.append(result)
            
            # Merge results
            return self._merge_transcriptions(chunk_results)

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration in seconds using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())

    def _chunk_audio(self, audio_path: Path, chunk_dir: Path) -> list[Path]:
        """Split audio into overlapping chunks using ffmpeg."""
        total_duration = self._get_audio_duration(audio_path)
        chunk_paths = []
        
        # Calculate chunk boundaries
        start_times = []
        current_start = 0.0
        while current_start < total_duration:
            start_times.append(current_start)
            current_start += self.chunk_duration - self.chunk_overlap
        
        # Create chunks
        chunk_dir.mkdir(parents=True, exist_ok=True)
        
        for i, start_time in enumerate(start_times):
            end_time = min(start_time + self.chunk_duration, total_duration)
            chunk_path = chunk_dir / f"chunk_{i:03d}.wav"
            
            cmd = [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-ss", str(start_time),
                "-to", str(end_time),
                "-ar", "16000",
                "-ac", "1",
                "-acodec", "pcm_s16le",
                str(chunk_path),
            ]
            
            subprocess.run(cmd, capture_output=True, check=True)
            chunk_paths.append(chunk_path)
        
        return chunk_paths

    def _parse_response(self, result: dict[str, Any], language: str) -> RawTranscript:
        """Parse Groq API response into RawTranscript."""
        segments = []
        for seg in result.get("segments", []):
            segments.append(
                TranscriptSegment(
                    text=seg.get("text", "").strip(),
                    start=seg.get("start", 0.0),
                    duration=seg.get("end", 0.0) - seg.get("start", 0.0),
                )
            )
        
        return RawTranscript(
            video_id="",
            segments=segments,
            source="groq_whisper",
            language=result.get("language", language),
        )

    def _merge_transcriptions(self, chunk_results: list[RawTranscript]) -> RawTranscript:
        """Merge transcriptions from multiple chunks."""
        if not chunk_results:
            return RawTranscript(video_id="", segments=[], source="groq_whisper", language="en")
        
        if len(chunk_results) == 1:
            return chunk_results[0]
        
        merged_segments = []
        segment_offset = 0.0
        
        for chunk_idx, result in enumerate(chunk_results):
            if chunk_idx == 0:
                merged_segments.extend(result.segments)
            else:
                # Adjust timestamps for subsequent chunks
                for seg in result.segments:
                    adjusted_seg = TranscriptSegment(
                        text=seg.text,
                        start=seg.start + segment_offset,
                        duration=seg.duration,
                    )
                    merged_segments.append(adjusted_seg)
            
            # Calculate offset for next chunk
            if result.segments:
                last_seg = result.segments[-1]
                segment_offset = last_seg.start + last_seg.duration - self.chunk_overlap
        
        return RawTranscript(
            video_id="",
            segments=merged_segments,
            source="groq_whisper",
            language=chunk_results[0].language,
        )
