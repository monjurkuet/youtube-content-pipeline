# YouTube Transcription Pipeline

A simple, robust pipeline for transcribing YouTube videos and saving transcripts to MongoDB. Features automatic cookie management, Whisper fallback, REST API, and **channel tracking**.

## Features

- **Simple 2-Step Pipeline**: Get transcript → Save to MongoDB
- **Automatic Fallback**: YouTube API → Whisper transcription
- **Auto Cookie Management**: Extracts cookies from Chrome automatically
- **OpenVINO Whisper**: Optimized transcription with GPU/CPU support
- **REST API**: FastAPI endpoints for async transcription jobs
- **MongoDB Storage**: Full transcripts with timestamps
- **Channel Tracking**: Track YouTube channels and sync all videos with metadata

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

### Track YouTube Channels

```bash
# Add channel to tracking
uv run python -m src.cli channel add @ChartChampions

# Sync latest videos (RSS feed, ~15 videos, 2 seconds)
uv run python -m src.cli channel sync @ChartChampions

# Sync ALL videos with full metadata (slower, ~1.3s per video)
uv run python -m src.cli channel sync @ChartChampions --all --max-videos 500

# Smart incremental sync (only fetch metadata for NEW videos)
uv run python -m src.cli channel sync @ChartChampions --all --incremental

# List tracked channels
uv run python -m src.cli channel list

# List videos from channel
uv run python -m src.cli channel videos @ChartChampions --limit 20

# Transcribe pending videos
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 5
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
- `POST /api/v1/channels/` - Add channel to tracking
- `GET /api/v1/channels/` - List tracked channels
- `POST /api/v1/channels/{channel_id}/sync` - Trigger channel sync
- `GET /api/v1/channels/{channel_id}/videos` - Get channel videos

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

## Channel Tracking Architecture

```
YouTube Channel (@Handle)
    |
Resolve Channel ID
    |
Fetch Videos
    ├── RSS Feed (fast, ~15 latest videos)
    └── yt-dlp --simulate (complete metadata, all videos)
    |
Save to MongoDB
    ├── channels collection (channel metadata)
    └── video_metadata collection (video info + transcript status)
    |
Transcribe Pending
    └── Process videos with transcript_status="pending"
```

### Video Metadata Stored

For each video:
- `video_id` - Unique YouTube video ID
- `title` - Video title
- `description` - Full description
- `thumbnail_url` - Video thumbnail
- `duration_seconds` - Video duration
- `view_count` - View count
- `published_at` - Upload date
- `transcript_status` - pending/completed/failed
- `transcript_id` - Reference to transcript document

### Sync Strategies

| Method | Command | Speed | Use Case |
|--------|---------|-------|----------|
| **RSS (default)** | `channel sync @Handle` | ⚡ 2s | Daily checks |
| **Incremental** | `channel sync @Handle --all --incremental` | 🧠 Variable | Catch-up |
| **Full Sync** | `channel sync @Handle --all --max-videos 500` | 🐌 1.3s/video | Complete refresh |

**Recommended Workflow:**
- **Daily**: `channel sync @Handle` (2 seconds)
- **Weekly**: `channel sync @Handle --all --incremental` (catch up on new videos)
- **Monthly**: `channel sync @Handle --all --max-videos 1000` (complete refresh)

See `CHANNEL_SYNC_GUIDE.md` for detailed documentation.

## Project Structure

```
src/
├── __init__.py                 # Package exports
├── cli.py                      # CLI interface
├── database.py                 # MongoDB integration
├── channel/                    # Channel tracking module
│   ├── __init__.py
│   ├── resolver.py            # Handle → Channel ID
│   ├── feed_fetcher.py        # RSS + yt-dlp fetching
│   ├── sync.py                # Sync logic
│   └── schemas.py             # Channel/Video schemas
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

### Channel Tracking API

```python
from src.channel import sync_channel, get_pending_videos

# Sync channel
result = sync_channel("@ChartChampions", mode="all", max_videos=500)
print(f"Fetched {result.videos_fetched} videos")

# Get pending videos
pending = get_pending_videos(channel_id="UCHOP_YfwdMk5hpxbugzC1wA")
print(f"{len(pending)} videos pending transcription")
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

    # List channels
    channels = await db.list_channels()

    # Get pending videos
    pending = await db.get_pending_transcription_videos()

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

## Documentation

- `README.md` - This file (overview and quick start)
- `CHANNEL_SYNC_GUIDE.md` - Detailed channel sync strategies and workflows
- `AGENTS.md` - Development guidelines and architecture notes

## License

MIT
