"""Whisper transcription using transformers with fallback."""

import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

# Suppress warnings
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# Model cache to avoid repeated loading
_MODEL_REGISTRY = {}


def _get_preferred_device() -> str:
    """Get preferred device for inference."""
    preferred = os.environ.get("WHISPER_DEVICE", "auto")

    if preferred == "auto":
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    return preferred


class TransformersWhisperTranscriber:
    """Whisper model using HuggingFace transformers (CPU/GPU)."""

    def __init__(
        self,
        model_id: str = "openai/whisper-base",
        device: str | None = None,
        cache_dir: str | None = None,
    ):
        """Initialize Whisper with transformers.

        Args:
            model_id: HuggingFace model ID for Whisper
            device: Device to use (cuda, cpu, or auto)
            cache_dir: Model cache directory
        """
        self.model_id = model_id
        self.device = device or _get_preferred_device()
        self.cache_dir = cache_dir or os.path.expanduser("~/.cache/whisper")

        self.model = None
        self.processor = None

    def _load_model(self):
        """Load Whisper model and processor."""
        if self.model is not None:
            return

        print(f"🔄 Loading Transformers Whisper model: {self.model_id}")
        print(f"   Device: {self.device}")
        print(f"   Cache: {self.cache_dir}")

        try:
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

            # Determine device
            if self.device == "cuda" and not torch.cuda.is_available():
                print("   ⚠️  CUDA requested but not available, using CPU")
                self.device = "cpu"

            # Load processor
            self.processor = AutoProcessor.from_pretrained(
                self.model_id,
                cache_dir=self.cache_dir,
            )

            # Load model on appropriate device
            model_config = {
                "torch_dtype": torch.float16 if self.device == "cuda" else torch.float32,
            }

            # Try to load with OpenVINO first, fall back to PyTorch
            try:
                # Try OpenVINO if available
                if self.device != "cuda":
                    from transformers import AutoModelForSpeechSeq2Seq

                    # Check if optimum is available
                    try:
                        from optimum.intel.openvino import OVModelForSpeechSeq2Seq

                        print("   Using OpenVINO model...")
                        self.model = OVModelForSpeechSeq2Seq.from_pretrained(
                            self.model_id,
                            cache_dir=self.cache_dir,
                            device=self.device.lower(),
                            compile=False,
                        )
                        self._use_openvino = True
                        print(f"   ✅ OpenVINO model loaded on {self.device}")
                        return
                    except ImportError:
                        pass  # Fall back to PyTorch
            except Exception as e:
                print(f"   OpenVINO load failed ({e}), using PyTorch...")

            # Fall back to PyTorch
            self._use_openvino = False
            self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
                self.model_id,
                cache_dir=self.cache_dir,
                **model_config,
            )

            # Move to device
            self.model.to(self.device)

            print(f"   ✅ Model loaded on {self.device}")

        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model: {e}") from e

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        chunk_length: int = 30,
    ) -> dict[str, Any]:
        """Transcribe audio file.

        Args:
            audio_path: Path to audio file
            language: Language code (default: en)
            chunk_length: Chunk length for processing

        Returns:
            Dictionary with transcription results
        """
        try:
            return self._transcribe_impl(audio_path, language, chunk_length)
        except (RuntimeError, OSError, MemoryError) as e:
            error_msg = str(e)
            if "longjmp" in error_msg.lower() or "memory" in error_msg.lower():
                raise RuntimeError(
                    "Whisper transcription failed due to library crash. "
                    "Try using CPU device: export WHISPER_DEVICE=cpu"
                ) from e
            raise

    def _transcribe_impl(
        self,
        audio_path: str,
        language: str = "en",
        chunk_length: int = 30,
    ) -> dict[str, Any]:
        """Internal transcription implementation."""
        self._load_model()

        if self.model is None or self.processor is None:
            raise RuntimeError("Model not loaded")

        print(f"🎵 Loading audio: {audio_path}")

        # Load audio
        try:
            import soundfile as sf

            audio_data, samplerate = sf.read(audio_path)
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)
            if samplerate != 16000:
                import librosa

                audio_data = librosa.resample(
                    audio_data.astype(np.float32), orig_sr=samplerate, target_sr=16000
                )
        except Exception as e:
            print(f"   soundfile failed ({e}), trying librosa...")
            import librosa

            audio_data, samplerate = librosa.load(audio_path, sr=16000)

        print(f"   Audio loaded: {len(audio_data) / 16000:.1f}s at 16kHz")

        # Process audio
        input_features = self.processor(
            audio_data,
            sampling_rate=16000,
            return_tensors="pt",
        ).input_features

        # Move to device
        input_features = input_features.to(self.device)

        # Generate
        if self._use_openvino:
            # OpenVINO generates differently
            forced_decoder_ids = self.processor.get_decoder_prompt_ids(language=language)
            generated_ids = self.model.generate(
                input_features,
                forced_decoder_ids=forced_decoder_ids,
            )
        else:
            # PyTorch
            forced_decoder_ids = self.processor.get_decoder_prompt_ids(language=language)
            generated_ids = self.model.generate(
                input_features,
                forced_decoder_ids=forced_decoder_ids,
            )

        # Decode
        transcription = self.processor.batch_decode(generated_ids, skip_special_tokens=True)

        return {
            "text": transcription[0],
            "language": language,
        }

    def unload(self):
        """Unload model from memory."""
        if self.model is not None:
            del self.model
            self.model = None
        if self.processor is not None:
            del self.processor
            self.processor = None

        # Clear GPU cache if applicable
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


# Create a simple function interface for compatibility
def create_whisper_transcriber(
    model_id: str = "openai/whisper-base",
    device: str | None = None,
    cache_dir: str | None = None,
) -> TransformersWhisperTranscriber:
    """Create a Whisper transcriber instance."""
    return TransformersWhisperTranscriber(
        model_id=model_id,
        device=device,
        cache_dir=cache_dir,
    )


# For backwards compatibility, keep the same interface
WhisperTranscriber = TransformersWhisperTranscriber
