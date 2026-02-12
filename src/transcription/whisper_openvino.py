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
            device: Device to use (CPU, GPU, AUTO). If None, auto-detects.
            cache_dir: Cache directory for model files
        """
        self.model_id = model_id
        self.device = device or "AUTO"
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

        try:
            # Load model and processor
            model = OVModelForSpeechSeq2Seq.from_pretrained(
                self.model_id,
                export=True,
                device=self.device,
                cache_dir=str(self.cache_dir),
            )
            processor = AutoProcessor.from_pretrained(self.model_id)
            print("✅ Model loaded successfully")

            # Store in registry to reuse across instances
            _MODEL_REGISTRY[self.cache_key] = (model, processor)

            # Store in instance
            self.model = model
            self.processor = processor

        except Exception as e:
            if self.device == "GPU":
                print(f"⚠️  Failed to load on GPU: {e}")
                print("🔄 Falling back to CPU...")
                fallback_device = "CPU"
                fallback_key = f"{self.model_id}__{fallback_device}"

                # Check if fallback model is already cached
                if fallback_key in _MODEL_REGISTRY:
                    self.model, self.processor = _MODEL_REGISTRY[fallback_key]
                    print("✅ Using cached CPU model")
                else:
                    model = OVModelForSpeechSeq2Seq.from_pretrained(
                        self.model_id,
                        export=True,
                        device=fallback_device,
                        cache_dir=str(self.cache_dir),
                    )
                    processor = AutoProcessor.from_pretrained(self.model_id)
                    print("✅ Model loaded on CPU")

                    # Store fallback in registry
                    _MODEL_REGISTRY[fallback_key] = (model, processor)
                    self.model = model
                    self.processor = processor
            else:
                raise RuntimeError(f"Failed to load Whisper model: {e}") from e

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
        """
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

        for i in range(0, len(audio_data), samples_per_chunk):
            chunk_num = i // samples_per_chunk + 1
            chunk = audio_data[i : i + samples_per_chunk]

            # Pad last chunk if needed
            if len(chunk) < samples_per_chunk:
                chunk = np.pad(chunk, (0, samples_per_chunk - len(chunk)))

            # Process chunk
            inputs = self.processor(chunk, sampling_rate=16000, return_tensors="pt").input_features

            # Generate
            with torch.no_grad():
                predicted_ids = self.model.generate(inputs, max_new_tokens=400)

            # Decode
            transcription = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]

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

        print("✅ Transcription complete!")

        return {
            "text": " ".join(full_transcription),
            "segments": segments,
            "model": self.model_id,
            "device": self.device,
            "duration": duration,
            "language": language,
        }


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
