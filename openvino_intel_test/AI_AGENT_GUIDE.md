# OpenVINO Intel GPU Test - AI Agent Guide

## System Architecture

### Core Components
- `OpenVINOWhisperTranscriber`: Main transcription class
- Device detection via `ov.Core().available_devices`
- Model mapping: `openai/whisper-medium` → `OpenVINO/whisper-medium-int8-ov`
- Automatic fallback from GPU to CPU

### Configuration Parameters
```python
# From config.py
openvino_whisper_model = "openai/whisper-medium"
openvino_device = "AUTO"
openvino_cache_dir = "~/.cache/whisper_openvino"
whisper_chunk_length = 30
```

## Validation Steps

### 1. Hardware Detection
```python
def _check_intel_gpu(self) -> bool:
    import openvino as ov
    core = ov.Core()
    devices = core.available_devices
    return "GPU" in devices
```

### 2. Model Loading Sequence
1. Attempt to load OpenVINO optimized model
2. Fallback to HuggingFace CPU model if OpenVINO fails
3. Verify device compatibility

### 3. Transcription Process
- Audio preprocessing (resampling to 16kHz)
- Feature extraction using processor
- Model inference with device-specific optimizations
- Text generation and decoding

## Error Handling Patterns

### GPU-Specific Issues
- Longjmp/setjmp stack frame errors
- Device memory limitations
- Driver compatibility issues

### Fallback Mechanisms
```python
try:
    # OpenVINO GPU path
    transcriber = OpenVINOWhisperTranscriber(...)
except Exception as e:
    # Fallback to CPU
    from transformers import AutoModelForSpeechSeq2Seq
```

## Performance Optimization

### Intel GPU Optimizations
- INT8 quantization for inference
- Hardware-specific kernels
- Memory-efficient processing

### Resource Management
- Automatic model unloading
- Cache management
- Memory cleanup with `gc.collect()`

## Test Validation Points

### Success Criteria
- [ ] Device detection returns "GPU" if Intel hardware available
- [ ] Model loads without errors
- [ ] Transcription completes successfully
- [ ] Performance metrics are reasonable
- [ ] Fallback mechanism works if needed

### Monitoring Indicators
- Device utilization
- Memory consumption
- Processing time per minute of audio
- Accuracy compared to reference transcription

## Integration Points

### With Transcription Handler
```python
# In handler.py
intel_gpu_available = self._check_intel_gpu()
if intel_gpu_available:
    # Use OpenVINO path
else:
    # Use faster-whisper fallback
```

### With Configuration System
- Respects YAML and environment variable overrides
- Maintains compatibility with existing pipeline
- Preserves rate limiting and caching

## Troubleshooting

### Common Issues
1. Missing OpenVINO installation
2. GPU driver problems
3. Model download failures
4. Memory constraints

### Diagnostic Commands
```bash
# Check OpenVINO installation
python -c "import openvino; print(openvino.__version__)"

# Check available devices
python -c "import openvino as ov; print(ov.Core().available_devices)"

# Verify model cache
ls ~/.cache/whisper_openvino/
```

## Deployment Considerations

### Environment Setup
- Install OpenVINO toolkit
- Configure Intel GPU drivers
- Set appropriate cache directories
- Verify model permissions

### Scaling Factors
- Concurrent transcription limitations
- GPU memory constraints
- Model loading overhead
- Cache warming requirements