# YouTube Transcription Pipeline

A simple, robust pipeline for transcribing YouTube videos and saving transcripts to MongoDB. Features automatic cookie management, Whisper fallback, and REST API.

## Features

- **Simple 2-Step Pipeline**: Get transcript → Save to MongoDB
- **Automatic Fallback**: YouTube API → Whisper transcription
- **Auto Cookie Management**: Extracts cookies from Chrome automatically
- **OpenVINO Whisper**: Optimized transcription with GPU/CPU support
- **REST API**: FastAPI endpoints for async transcription jobs
- **MongoDB Storage**: Full transcripts with timestamps

## Installation

```bash
# Clone repository
git clone <repository-url>
cd youtube-content-pipeline

# Install dependencies
uv sync
```

### Requirements

- Python 3.12+
- FFmpeg (for audio processing)
- MongoDB (optional, for data storage)
- Chrome browser (for cookie extraction)
- Node.js or Deno (for YouTube JS challenges)

## Quick Start

### Transcribe a YouTube Video

```bash
# Basic transcription
uv run python -m src.cli transcribe "https://youtube.com/watch?v=VIDEO_ID"

# With verbose output
uv run python -m src.cli transcribe "https://youtube.com/watch?v=VIDEO_ID" --verbose

# Save to file
uv run python -m src.cli transcribe "URL" --output transcript.json

# Skip database save
uv run python -m src.cli transcribe "URL" --no-db
```

### Batch Transcription

```bash
# Create a file with video sources (one per line)
echo "https://youtube.com/watch?v=VIDEO_ID1" > sources.txt
echo "https://youtube.com/watch?v=VIDEO_ID2" >> sources.txt

# Run batch transcription
uv run python -m src.cli batch sources.txt
```

### Start the API Server

```bash
uv run uvicorn src.api.main:app --reload
```

API endpoints:
- `POST /api/v1/videos/transcribe` - Submit video for transcription
- `GET /api/v1/videos/jobs/{job_id}` - Check job status
- `GET /api/v1/transcripts/{video_id}` - Get transcript
- `GET /api/v1/transcripts/` - List transcripts

## Configuration

Create a `.env` file:

```bash
# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=video_pipeline

# OpenVINO Whisper
OPENVINO_WHISPER_MODEL=openai/whisper-base
OPENVINO_DEVICE=AUTO  # AUTO, GPU, or CPU
OPENVINO_CACHE_DIR=~/.cache/whisper_openvino
```

## Architecture

```
YouTube URL / Local Video
    |
Step 1: Get Transcript
    ├── YouTube Transcript API (fast)
    └── Fallback: yt-dlp + OpenVINO Whisper (with cookies)
    |
Step 2: Save to MongoDB
    └── Full transcript with timestamps
```

## Project Structure

```
src/
├── __init__.py                 # Package exports
├── cli.py                      # CLI interface
├── database.py                 # MongoDB integration
├── api/
│   ├── main.py                # FastAPI app
│   ├── dependencies.py        # FastAPI dependencies
│   ├── routers/
│   │   ├── videos.py          # Transcription endpoints
│   │   └── transcripts.py    # Transcript retrieval
│   └── models/
│       └── requests.py        # Pydantic models
├── core/
│   ├── config.py              # Configuration settings
│   ├── exceptions.py          # Custom exceptions
│   └── schemas.py             # Pydantic models
├── pipeline/
│   └── transcript.py         # Main pipeline
├── transcription/
│   ├── handler.py            # Transcription with fallback
│   └── whisper_openvino.py   # OpenVINO Whisper
└── video/
    └── cookie_manager.py     # Browser cookie management
```

## Programmatic API

```python
from src.pipeline import get_transcript, TranscriptPipeline

# Simple transcription
result = get_transcript("https://youtube.com/watch?v=VIDEO_ID")

# Access results
print(result.video_id)
print(result.segment_count)
print(result.duration_seconds)
print(result.transcript_source)  # "youtube_api" or "whisper"

# With custom settings
pipeline = TranscriptPipeline(work_dir="/custom/path")
result = pipeline.process("URL", save_to_db=False)
```

## Database Operations

```python
import asyncio
from src.database import get_db_manager

async def db_operations():
    db = get_db_manager()

    # Get transcript
    transcript = await db.get_transcript("video_id")

    # List transcripts
    transcripts = await db.list_transcripts(limit=10)

    await db.close()

asyncio.run(db_operations())
```

## Cookie Management

```bash
# Check cookie status
uv run python -m src.video.cookie_manager --status

# Force re-extraction
uv run python -m src.video.cookie_manager --invalidate
```

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_pipeline.py -v
```

## License

MIT
