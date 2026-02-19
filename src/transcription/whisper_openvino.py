"""Whisper transcription using OpenVINO on Intel GPU/CPU."""

import os
from pathlib import Path
from typing import Any

import numpy as np
import torch

# Fix OpenVINO threading issues
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["OPENVINO_CPU_THREADS"] = "4"

# Model cache to avoid repeated loading
_MODEL_REGISTRY = {}


def _get_preferred_device() -> str:
    """Get preferred device, checking if GPU is actually usable."""
    preferred = os.environ.get("OPENVINO_DEVICE", "AUTO")

    if preferred in ("CPU", "AUTO"):
        return preferred

    # If GPU is requested, verify it's available
    if preferred == "GPU":
        try:
            import openvino as ov

            core = ov.Core()
            devices = core.available_devices
            if "GPU" in devices:
                return "GPU"
            else:
                print("⚠️  GPU requested but not available, falling back to CPU")
                return "CPU"
        except Exception:
            return "CPU"

    return preferred


class OpenVINOWhisperTranscriber:
    """Whisper model optimized for Intel GPU/CPU using OpenVINO."""

    def __init__(
        self,
        model_id: str = "openai/whisper-base",
        device: str | None = None,
        cache_dir: str | None = None,
    ):
        """Initialize Whisper with OpenVINO.

        Args:
            model_id: HuggingFace model ID for Whisper
            device: Device to use (CPU, GPU, AUTO). If None, uses OPENVINO_DEVICE env var or AUTO.
            cache_dir: Cache directory for model files
        """
        self.model_id = model_id
        self.device = device or _get_preferred_device()
        self.cache_dir = Path(cache_dir or "~/.cache/whisper_openvino").expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Create cache key for this configuration
        self.cache_key = f"{model_id}__{self.device}"

        # Check if model is already loaded in registry
        if self.cache_key in _MODEL_REGISTRY:
            self.model, self.processor = _MODEL_REGISTRY[self.cache_key]
        else:
            # Will be loaded later
            self.model = None
            self.processor = None

    def _load_model(self) -> None:
        """Load or initialize the OpenVINO model."""
        if self.model is not None:
            return

        print(f"🔄 Loading OpenVINO Whisper model: {self.model_id}")
        print(f"   Device: {self.device}")
        print(f"   Cache: {self.cache_dir}")

        # Import here to avoid issues at module level
        from optimum.intel.openvino import OVModelForSpeechSeq2Seq
        from transformers import AutoProcessor

        # Try loading on requested device
        devices_to_try = [self.device]

        # Add fallback devices
        if self.device not in ("CPU",):
            devices_to_try.append("CPU")

        last_error = None
        for device in devices_to_try:
            try:
                cache_key = f"{self.model_id}__{device}"

                # Check if already cached in registry
                if cache_key in _MODEL_REGISTRY:
                    self.model, self.processor = _MODEL_REGISTRY[cache_key]
                    self.device = device
                    print(f"✅ Using cached model on {device}")
                    return

                # Load model and processor
                model = OVModelForSpeechSeq2Seq.from_pretrained(
                    self.model_id,
                    export=True,
                    device=device,
                    cache_dir=str(self.cache_dir),
                )
                processor = AutoProcessor.from_pretrained(self.model_id)
                print(f"✅ Model loaded on {device}")

                # Store in registry to reuse across instances
                _MODEL_REGISTRY[cache_key] = (model, processor)

                # Store in instance
                self.model = model
                self.processor = processor
                self.device = device
                return

            except Exception as e:
                last_error = e
                if device != "CPU":
                    print(f"⚠️  Failed on {device}: {str(e)[:100]}")
                    print("🔄 Trying fallback device...")
                continue

        raise RuntimeError(f"Failed to load Whisper model on any device: {last_error}")

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        chunk_length: int = 30,
    ) -> dict[str, Any]:
        """Transcribe audio using OpenVINO.

        Args:
            audio_path: Path to audio or video file
            language: Language code (default: "en")
            chunk_length: Length of audio chunks in seconds (default: 30)

        Returns:
            Dictionary with transcription text and metadata

        Raises:
            RuntimeError: If transcription fails due to OpenVINO issues
        """
        try:
            return self._transcribe_impl(audio_path, language, chunk_length)
        except (RuntimeError, OSError, MemoryError) as e:
            error_msg = str(e)
            if "longjmp" in error_msg.lower() or "memory" in error_msg.lower():
                raise RuntimeError(
                    f"OpenVINO transcription failed due to library crash. "
                    f"This is typically caused by: "
                    f"(1) Insufficient memory, (2) OpenVINO library bug, or "
                    f"(3) Incompatible hardware. Try using CPU device or "
                    f"installing the standard transformers package: "
                    f"pip install transformers torch"
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

        # Load audio using soundfile or librosa
        try:
            import soundfile as sf

            audio_data, samplerate = sf.read(audio_path)
            # Convert to mono if stereo
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)
            # Resample to 16kHz if needed
            if samplerate != 16000:
                import librosa

                audio_data = librosa.resample(
                    audio_data.astype(np.float32), orig_sr=samplerate, target_sr=16000
                )
        except Exception as e:
            print(f"   soundfile failed ({e}), trying librosa...")
            import librosa

            audio_data, samplerate = librosa.load(audio_path, sr=16000, mono=True)

        duration = len(audio_data) / 16000
        print(f"   Duration: {duration:.1f} seconds")

        # Process audio in chunks
        print("📝 Transcribing...")

        samples_per_chunk = chunk_length * 16000
        full_transcription: list[str] = []
        segments: list[dict] = []

        num_chunks = (len(audio_data) + samples_per_chunk - 1) // samples_per_chunk

        try:
            for i in range(0, len(audio_data), samples_per_chunk):
                chunk_num = i // samples_per_chunk + 1
                chunk = audio_data[i : i + samples_per_chunk]

                # Pad last chunk if needed
                if len(chunk) < samples_per_chunk:
                    chunk = np.pad(chunk, (0, samples_per_chunk - len(chunk)))

                # Process chunk
                inputs = self.processor(
                    chunk, sampling_rate=16000, return_tensors="pt"
                ).input_features

                # Generate
                with torch.no_grad():
                    predicted_ids = self.model.generate(  # type: ignore[attr-defined]
                        inputs, max_new_tokens=400
                    )

                # Decode
                transcription = self.processor.batch_decode(
                    predicted_ids, skip_special_tokens=True
                )[0]

                if transcription.strip():
                    full_transcription.append(transcription)
                    segments.append(
                        {
                            "id": chunk_num,
                            "start": i / 16000,
                            "end": min((i + samples_per_chunk) / 16000, duration),
                            "text": transcription,
                        }
                    )
                    progress = chunk_num / num_chunks * 100
                    print(f"   [{progress:5.1f}%] {transcription[:60]}...")

        except Exception as e:
            # If inference fails on GPU, try to fall back to CPU
            is_gpu = self.device == "GPU" or (
                self.device == "AUTO" and "GPU" in self._get_available_devices()
            )
            if is_gpu:
                print(f"⚠️  Inference error on GPU: {str(e)[:100]}")
                print("🔄 Retrying on CPU...")

                # Force CPU reload
                self.device = "CPU"
                self.cache_key = f"{self.model_id}__CPU"
                self.model = None
                self.processor = None
                self._load_model()

                # Retry transcription
                return self._transcribe_impl(audio_path, language, chunk_length)

            raise RuntimeError(f"Transcription failed: {e}") from e

        print("✅ Transcription complete!")

        return {
            "text": " ".join(full_transcription),
            "segments": segments,
            "model": self.model_id,
            "device": self.device,
            "duration": duration,
            "language": language,
        }

    def _get_available_devices(self) -> list[str]:
        """Get list of available OpenVINO devices."""
        try:
            import openvino as ov

            core = ov.Core()
            return core.available_devices
        except Exception:
            return ["CPU"]


def transcribe_audio(
    audio_path: str,
    model_id: str = "openai/whisper-base",
    device: str | None = None,
) -> dict[str, Any]:
    """Convenience function to transcribe audio with OpenVINO.

    Args:
        audio_path: Path to audio or video file
        model_id: HuggingFace model ID
        device: Device to use (CPU, GPU, AUTO)

    Returns:
        Transcription result dictionary
    """
    transcriber = OpenVINOWhisperTranscriber(model_id=model_id, device=device)
    return transcriber.transcribe(audio_path)
