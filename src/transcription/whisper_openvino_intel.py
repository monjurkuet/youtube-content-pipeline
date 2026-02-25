"""Whisper transcription using Optimum Intel OpenVINO for Intel GPU acceleration."""

import os
import gc
import warnings
from pathlib import Path
from typing import Any

# Suppress OpenVINO deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Suppress OpenVINO warnings
os.environ["OPENVINO_LOG_LEVEL"] = "3"  # 3 = error only
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


class OpenVINOWhisperTranscriber:
    """Whisper model using Intel OpenVINO for GPU acceleration on Intel Arc."""

    # Pre-converted OpenVINO models from HuggingFace (Intel/OpenVINO official)
    # Format: model_size -> (model_id, compute_type)
    OPENVINO_MODELS = {
        "tiny": ("OpenVINO/whisper-tiny-int4-ov", "int4"),
        "base": ("OpenVINO/whisper-base-fp16-ov", "fp16"),
        "small": ("OpenVINO/whisper-small-fp16-ov", "fp16"),
        "medium": ("OpenVINO/whisper-medium-int8-ov", "int8"),
        "large-v2": ("OpenVINO/whisper-large-v2-fp16-ov", "fp16"),
        "large-v3": ("OpenVINO/whisper-large-v3-fp16-ov", "fp16"),
    }

    def __init__(
        self,
        model_id: str = "openai/whisper-medium",
        device: str | None = None,
        cache_dir: str | None = None,
    ):
        """Initialize Whisper with OpenVINO.

        Args:
            model_id: HuggingFace model ID for Whisper (e.g., "openai/whisper-medium")
            device: Device to use (GPU, CPU, or AUTO)
            cache_dir: Model cache directory
        """
        self.model_id = model_id
        self.device = device or self._detect_device()
        self.cache_dir = cache_dir or os.path.expanduser("~/.cache/huggingface")

        self.model = None
        self.processor = None

    def _detect_device(self) -> str:
        """Detect available device - prefer Intel GPU if available."""
        try:
            import openvino as ov

            core = ov.Core()
            devices = core.available_devices
            if "GPU" in devices:
                print(f"   🎮 Intel GPU detected, using GPU")
                return "GPU"
        except Exception:
            pass
        print("   💻 No GPU detected, using CPU")
        return "CPU"

    def _get_openvino_model_id(self, model_id: str) -> tuple[str, str]:
        """Get the pre-converted OpenVINO model ID and compute type."""
        # Extract base name from model_id (e.g., "openai/whisper-medium" -> "medium")
        base_name = model_id.replace("openai/", "").replace("whisper-", "")

        # Map to known sizes
        size_map = {
            "tiny": "tiny",
            "base": "base",
            "small": "small",
            "medium": "medium",
            "large-v2": "large-v2",
            "large-v3": "large-v3",
            "large-v3-turbo": "large-v3",
        }

        size = size_map.get(base_name, "base")

        if size in self.OPENVINO_MODELS:
            return self.OPENVINO_MODELS[size]

        # Default to base if not found
        return self.OPENVINO_MODELS["base"]

    def _load_model(self):
        """Load Whisper model with OpenVINO."""
        if self.model is not None:
            return

        # Get pre-converted model
        ov_model_id, compute_type = self._get_openvino_model_id(self.model_id)

        print(f"🔄 Loading OpenVINO Whisper: {self.model_id}")
        print(f"   📦 Using pre-converted: {ov_model_id}")
        print(f"   💾 Compute type: {compute_type}")
        print(f"   🖥️  Device: {self.device}")

        try:
            from optimum.intel.openvino import OVModelForSpeechSeq2Seq
            from transformers import AutoProcessor

            # Load processor from original model
            print(f"   📥 Loading processor...")
            self.processor = AutoProcessor.from_pretrained(
                self.model_id,
                cache_dir=self.cache_dir,
            )

            # Load pre-converted OpenVINO model
            print(f"   📦 Loading OpenVINO model...")
            self.model = OVModelForSpeechSeq2Seq.from_pretrained(
                ov_model_id,
                cache_dir=self.cache_dir,
                device=self.device.lower(),
                compile=False,
            )
            print(f"   ✅ OpenVINO model loaded on {self.device}")

        except Exception as e:
            print(f"   ⚠️  OpenVINO failed: {e}")
            print(f"   🔄 Falling back to HuggingFace (CPU)...")

            # Fallback to CPU PyTorch
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

            self.processor = AutoProcessor.from_pretrained(
                self.model_id,
                cache_dir=self.cache_dir,
            )

            self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
                self.model_id,
                cache_dir=self.cache_dir,
            )

            print(f"   ✅ HuggingFace model loaded on CPU")

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        chunk_length: int = 30,
    ) -> dict[str, Any]:
        """Transcribe audio file."""
        try:
            return self._transcribe_impl(audio_path, language, chunk_length)
        except (RuntimeError, OSError) as e:
            if "longjmp" in str(e).lower():
                raise RuntimeError("Transcription failed. Try using CPU device.") from e
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

        import numpy as np

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
        except Exception:
            import librosa

            audio_data, samplerate = librosa.load(audio_path, sr=16000)

        print(f"   Audio: {len(audio_data) / 16000:.1f}s at 16kHz")

        input_features = self.processor(
            audio_data,
            sampling_rate=16000,
            return_tensors="pt",
        ).input_features

        if hasattr(self.model, "device"):
            input_features = input_features.to(self.model.device)

        forced_decoder_ids = self.processor.get_decoder_prompt_ids(language=language)

        generated_ids = self.model.generate(
            input_features,
            forced_decoder_ids=forced_decoder_ids,
            max_new_tokens=256,
        )

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
        gc.collect()


def create_openvino_whisper_transcriber(
    model_id: str = "openai/whisper-base",
    device: str | None = None,
    cache_dir: str | None = None,
) -> OpenVINOWhisperTranscriber:
    """Create an OpenVINO Whisper transcriber instance."""
    return OpenVINOWhisperTranscriber(
        model_id=model_id,
        device=device,
        cache_dir=cache_dir,
    )
