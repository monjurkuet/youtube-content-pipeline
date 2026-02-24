## Must follow rules 
- No CI/CD required.
- Always use uv for python.
- Clean slate, production-ready architecture only. Don't need to maintain compatibility, don't need gradual migration.
- You are allowed to read, modify and write .env files.
- CORS allows all origins.

## OpenVINO Whisper
| Variable | Description | Default |
|----------|-------------|---------|
| `OPENVINO_WHISPER_MODEL` | HuggingFace model ID | `openai/whisper-base` |
| `OPENVINO_DEVICE` | Device to use (AUTO, GPU, CPU) | `AUTO` |
| `OPENVINO_CACHE_DIR` | Model cache directory | `~/.cache/whisper_openvino` |
