"""Source-agnostic transcription handler with fallback chain."""

import re
import subprocess
from pathlib import Path

from src.core.config import get_settings
from src.core.exceptions import TranscriptError, WhisperError, YouTubeAPIError
from src.core.schemas import RawTranscript, TranscriptSegment


class TranscriptionHandler:
    """Handle transcript acquisition from any source with fallback chain."""

    def __init__(self, work_dir: Path | None = None):
        self.settings = get_settings()
        self.work_dir = work_dir or self.settings.work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def get_transcript(self, video_id: str, source_type: str = "youtube") -> RawTranscript:
        """
        Get transcript with automatic fallback.

        For YouTube:
        1. Try YouTube Transcript API (fast, accurate)
        2. Fallback: Download audio + Whisper OpenVINO

        For other sources:
        - Direct Whisper transcription

        Args:
            video_id: Video ID or identifier
            source_type: "youtube", "url", or "local"

        Returns:
            RawTranscript object
        """
        if source_type == "youtube":
            return self._get_youtube_transcript_with_fallback(video_id)
        else:
            # For non-YouTube, use Whisper directly
            return self._transcribe_with_whisper(video_id)

    def _get_youtube_transcript_with_fallback(self, video_id: str) -> RawTranscript:
        """Get YouTube transcript with Whisper fallback."""
        # Try YouTube API first
        try:
            return self._get_youtube_api_transcript(video_id)
        except YouTubeAPIError as e:
            print(f"YouTube API failed: {e}")
            print("Falling back to Whisper transcription...")

        # Fallback to Whisper
        try:
            return self._transcribe_youtube_with_whisper(video_id)
        except Exception as e:
            raise TranscriptError(f"All transcription methods failed: {e}") from e

    def _get_youtube_api_transcript(self, video_id: str) -> RawTranscript:
        """Get transcript using YouTube Transcript API."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.fetch(video_id)

            segments = [
                TranscriptSegment(
                    text=item.text,
                    start=float(item.start),
                    duration=float(item.duration),
                )
                for item in transcript_list
            ]

            return RawTranscript(
                video_id=video_id,
                segments=segments,
                source="youtube_api",
                language="en",
            )

        except Exception as e:
            raise YouTubeAPIError(f"YouTube API failed: {e}") from e

    def _transcribe_youtube_with_whisper(self, video_id: str) -> RawTranscript:
        """Download YouTube audio and transcribe with Whisper."""
        # Download audio only
        audio_path = self._download_youtube_audio(video_id)

        try:
            result = self._transcribe_with_whisper(str(audio_path))
            result.source = "whisper"
            return result
        finally:
            # Cleanup
            if audio_path.exists():
                audio_path.unlink()

    def _download_youtube_audio(self, video_id: str) -> Path:
        """Download audio from YouTube video using browser cookies."""
        from src.video.cookie_manager import get_cookie_manager

        output_path = self.work_dir / f"{video_id}_audio.mp3"
        url = f"https://www.youtube.com/watch?v={video_id}"

        # Build command
        cmd = [
            "yt-dlp",
            "-f",
            "bestaudio/best",
            "--extract-audio",
            "--audio-format",
            self.settings.audio_format,
            "--audio-quality",
            self.settings.audio_bitrate,
            "-o",
            str(output_path.with_suffix(".%(ext)s")),
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--js-runtimes",
            "node",
        ]

        # Add cookies from browser
        cookie_manager = get_cookie_manager()
        if cookie_manager.ensure_cookies():
            cookie_args = cookie_manager.get_cookie_args()
            if cookie_args:
                cmd.extend(cookie_args)
                print("Using browser cookies for audio download")

        cmd.append(url)

        try:
            subprocess.run(cmd, check=True, timeout=300, capture_output=True, text=True)

            # Find the downloaded file (may have different extension)
            for ext in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                candidate = output_path.with_suffix(ext)
                if candidate.exists():
                    return candidate

            # Check for any audio file in work_dir
            for f in self.work_dir.glob(f"{video_id}_audio.*"):
                if f.suffix in [".mp3", ".m4a", ".wav", ".opus", ".webm"]:
                    return f

            raise WhisperError("Audio download completed but file not found")

        except subprocess.TimeoutExpired as e:
            raise WhisperError("Audio download timeout") from e
        except subprocess.CalledProcessError as e:
            error_detail = e.stderr if e.stderr else str(e)
            raise WhisperError(f"Audio download failed: {error_detail}") from e

    def _transcribe_with_whisper(self, audio_path: str) -> RawTranscript:
        """Transcribe audio file using OpenVINO Whisper."""
        from src.transcription.whisper_openvino import OpenVINOWhisperTranscriber

        transcriber = OpenVINOWhisperTranscriber(
            model_id=self.settings.openvino_whisper_model,
            device=self.settings.openvino_device,
            cache_dir=self.settings.openvino_cache_dir,
        )

        result = transcriber.transcribe(
            audio_path,
            chunk_length=self.settings.whisper_chunk_length,
        )

        # Convert to RawTranscript format
        segments = [
            TranscriptSegment(
                text=seg["text"],
                start=float(seg["start"]),
                duration=float(seg["end"] - seg["start"]),
            )
            for seg in result.get("segments", [])
        ]

        return RawTranscript(
            video_id=Path(audio_path).stem,
            segments=segments,
            source="whisper",
            language=result.get("language", "en"),
        )


def identify_source_type(source: str) -> tuple[str, str]:
    """
    Identify video source type and extract identifier.

    Returns:
        Tuple of (source_type, identifier)
    """
    # YouTube patterns
    youtube_patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",  # Just the ID
    ]

    for pattern in youtube_patterns:
        match = re.search(pattern, source)
        if match:
            return ("youtube", match.group(1))

    # Local file
    if Path(source).exists():
        return ("local", str(Path(source).resolve()))

    # URL
    from urllib.parse import urlparse

    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        return ("url", source)

    raise ValueError(f"Unknown source type: {source}")
