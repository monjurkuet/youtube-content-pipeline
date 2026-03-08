"""Whisper transcription provider with OpenVINO and faster-whisper support."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import get_settings_with_yaml
from src.core.exceptions import WhisperError
from src.core.schemas import RawTranscript, TranscriptSegment

logger = logging.getLogger(__name__)


def check_intel_gpu() -> bool:
    """Check if Intel GPU is available for OpenVINO."""
    try:
        import openvino.runtime as ov
        core = ov.Core()
        devices = core.available_devices
        return "GPU" in devices
    except (ImportError, Exception):
        return False


class WhisperProvider:
    """Provides transcription using various Whisper implementations."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings_with_yaml()

    def transcribe(self, audio_path: str, language: str = "en") -> RawTranscript:
        """Transcribe audio file with automatic backend selection (OpenVINO vs faster-whisper)."""
        # Try Intel GPU with OpenVINO first
        if check_intel_gpu():
            try:
                from src.transcription.whisper_openvino_intel import OpenVINOWhisperTranscriber

                model_id = self.settings.openvino_whisper_model
                logger.info(f"Using Intel GPU with OpenVINO ({model_id})")

                transcriber = OpenVINOWhisperTranscriber(
                    model_id=model_id,
                    device="GPU",
                    cache_dir=self.settings.openvino_cache_dir,
                )

                result = transcriber.transcribe(
                    audio_path,
                    language=language,
                    chunk_length=self.settings.whisper_chunk_length,
                )

                transcriber.unload()

                segments = [
                    TranscriptSegment(
                        text=result["text"],
                        start=0.0,
                        duration=0.0,
                    )
                ]

                return RawTranscript(
                    video_id="",
                    segments=segments,
                    source="whisper_openvino",
                    language=result.get("language", language),
                )
            except Exception as e:
                logger.warning(f"Intel OpenVINO failed ({e}), falling back to faster-whisper")

        # Fallback to faster-whisper
        try:
            from faster_whisper import WhisperModel
            import torch

            has_cuda = torch.cuda.is_available()
            model_id = os.environ.get("WHISPER_MODEL", "tiny" if not has_cuda else "base")
            compute_type = "int8" if not has_cuda else "float16"

            logger.info(f"Using faster-whisper: {model_id} ({compute_type})")
            model = WhisperModel(
                model_id,
                device="auto",
                compute_type=compute_type,
            )

            segs, info = model.transcribe(
                audio_path,
                language=language,
                beam_size=5,
                vad_filter=True,
            )

            transcript_segments = []
            for segment in segs:
                transcript_segments.append(
                    TranscriptSegment(
                        text=segment.text,
                        start=segment.start,
                        duration=segment.end - segment.start,
                    )
                )

            del model

            return RawTranscript(
                video_id="",
                segments=transcript_segments,
                source="faster_whisper",
                language=language,
            )

        except Exception as e:
            logger.error(f"faster-whisper failed: {e}")
            raise WhisperError(f"All Whisper providers failed: {e}")
