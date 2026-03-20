# YouTube Transcription Pipeline

A production-grade API for YouTube video transcription and transcript management. Features automatic cookie management, Whisper fallback, REST API with authentication, rate limiting, Prometheus metrics, MCP integration, and **channel tracking**.

## Features

### Core Features
- **Simple 2-Step Pipeline**: Get transcript → Save to MongoDB
- **Automatic Fallback**: YouTube API → Whisper transcription
- **Auto Cookie Management**: Extracts cookies from Chrome automatically
- **Rate Limiting**: Configurable delays to prevent IP blocking (2-5s default)
- **Retry Logic**: Exponential backoff for rate-limited requests
- **YouTube API Cookie Support**: Passes browser cookies to API for less detectable requests
- **Groq Whisper API**: Cloud-based transcription with automatic chunking

### API Features
- **REST API**: FastAPI endpoints for async transcription jobs
- **OpenAPI Documentation**: Interactive docs at `/docs` and `/redoc`
- **API Key Authentication**: Optional authentication with tiered access
- **Rate Limiting**: Per-key rate limiting with Redis backend
- **Health Checks**: Comprehensive health endpoints for monitoring
- **Prometheus Metrics**: Detailed metrics for monitoring and alerting

### AI Integration
- **MCP Server**: Model Context Protocol support for AI assistants
- **Tools**: Transcribe, search, and manage transcripts via AI
- **Resources**: Direct access to transcripts and job status
- **Prompts**: Pre-defined workflows for common tasks

### Data Management
- **MongoDB Storage**: Full transcripts with timestamps
- **Redis Cache**: Job queue and caching (optional)
- **Channel Tracking**: Track YouTube channels and sync all videos with metadata
- **YAML Configuration**: Centralized config file for all settings

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
- Redis (optional, for caching and rate limiting)
- Chrome browser (for cookie extraction)
- Node.js or Deno (for YouTube JS challenges)

### Optional Dependencies

```bash
# With Redis support
uv sync --extra redis

# With all extras
uv sync --all-extras
```

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

# Add channels from video URLs (extracts channel info automatically)
uv run python -m src.cli channel add-from-videos \
  "https://youtu.be/S9s1rZKO_18" \
  "https://youtu.be/fpKtJLc5Ntg" \
  --sync --sync-mode recent

# Cookie management
uv run python -m src.cli cookie status      # Check cookie status
uv run python -m src.cli cookie extract      # Extract cookies from Chrome
uv run python -m src.cli cookie invalidate    # Force re-extraction

# Utility commands
uv run python -m src.cli utils check-dependencies  # Check yt-dlp, Bun, Deno
uv run python -m src.cli utils version             # Show version info

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

# Transcribe pending videos (5 at a time, default)
uv run python -m src.cli channel transcribe-pending @ChartChampions

# Transcribe pending videos in custom batch size
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 20

# Transcribe ALL pending videos at once (may take hours)
uv run python -m src.cli channel transcribe-pending @ChartChampions --all

# Transcribe ALL pending videos in custom batch sizes (recommended)
uv run python -m src.cli channel transcribe-pending @ChartChampions --all --batch-size 20

# Retry failed transcriptions from a specific channel
uv run python -m src.cli channel retry-failed @ChartChampions

# Retry ALL failed transcriptions at once
uv run python -m src.cli channel retry-failed @ChartChampions --all

# Reset failed status to pending without immediate retry
uv run python -m src.cli channel retry-failed @ChartChampions --reset
```

### Transcribe All Videos from Channels

```bash
# Step 1: Add and sync channel
uv run python -m src.cli channel add @ChartChampions
uv run python -m src.cli channel sync @ChartChampions --all --max-videos 500

# Step 2: Transcribe all pending videos (in batches of 10)
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 10

# Step 3: Check progress
uv run python -m src.cli channel videos @ChartChampions --status completed --limit 10
uv run python -m src.cli channel videos @ChartChampions --status pending --limit 10

# Transcribe ALL channels at once
uv run python -m src.cli channel transcribe-pending --batch-size 10

# Transcribe from specific channel
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 10

# Retry failed transcriptions
uv run python -m src.cli channel retry-failed @ChartChampions --batch-size 10

# Check channel videos by status
uv run python -m src.cli channel videos @ChartChampions --status failed
```

### Full Workflow: Add Channel → Sync → Transcribe All

```bash
# Complete workflow for a new channel
uv run python -m src.cli channel add @ChartChampions          # Add channel
uv run python -m src.cli channel sync @ChartChampions --all   # Get all videos
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 10  # Transcribe

# For large channels (1000+ videos), transcribe in multiple batches:
# Run this command repeatedly until all videos are transcribed
uv run python -m src.cli channel transcribe-pending @ChartChampions --batch-size 10
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
# Option 1: Basic server (default port 8000)
uv run uvicorn src.api.main:app --reload

# Option 2: With custom port
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Option 3: Production (with workers)
uv run uvicorn src.api.main:app --workers 4 --host 0.0.0.0 --port 8000

# Option 4: With API key (set environment variable)
API_KEYS=your-secret-key uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Option 5: Use the start-api.sh script (recommended for production)
chmod +x scripts/start-api.sh
./scripts/start-api.sh start  # Starts API on port 18080
```

### Start Full Monitoring Stack (API + Prometheus + Grafana)

```bash
# Start all services
chmod +x scripts/launch-services.sh
./scripts/launch-services.sh start

# Access:
# - API: http://localhost:18080
# - Swagger UI: http://localhost:18080/docs
# - Prometheus: http://localhost:19090
# - Grafana: http://localhost:13000 (admin/admin)
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/videos/transcribe` | Submit video for transcription |
| `POST` | `/api/v1/videos/batch-transcribe` | Batch transcription (up to 100 videos) |
| `POST` | `/api/v1/videos/channel-transcribe-pending` | Transcribe pending videos from channel |
| `GET` | `/api/v1/videos/jobs/{job_id}` | Check job status |
| `GET` | `/api/v1/videos/jobs` | List transcription jobs |
| `GET` | `/api/v1/transcripts/{video_id}` | Get transcript |
| `GET` | `/api/v1/transcripts/` | List transcripts |
| `DELETE` | `/api/v1/transcripts/{video_id}` | Delete transcript |
| `GET` | `/api/v1/channels/` | List tracked channels |
| `GET` | `/api/v1/channels/{channel_id}` | Get channel details |
| `POST` | `/api/v1/channels/from-videos` | Add channels from video URLs |
| `DELETE` | `/api/v1/channels/{channel_id}` | Remove channel from tracking |
| `POST` | `/api/v1/channels/{channel_id}/sync` | Trigger channel sync |
| `GET` | `/api/v1/channels/{channel_id}/videos` | Get channel videos |
| `GET` | `/api/v1/channels/{channel_id}/stats` | Get channel statistics |
| `POST` | `/api/v1/channels/sync-all` | Sync all tracked channels |
| `GET` | `/api/v1/stats/` | Get system statistics |
| `GET` | `/health` | Basic health check |
| `GET` | `/health/ready` | Readiness probe |
| `GET` | `/health/detailed` | Detailed health status |
| `GET` | `/metrics` | Prometheus metrics |

### API Documentation

Interactive API documentation is available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Spec**: http://localhost:8000/openapi.json

See [API_USAGE_GUIDE.md](API_USAGE_GUIDE.md) for detailed usage examples.

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=video_pipeline

# Redis (optional)
REDIS_URL=redis://localhost:6379
REDIS_ENABLED=true

# API Authentication (optional)
API_KEYS=key1,key2,key3
AUTH_REQUIRE_KEY=false

# Groq Whisper API
GROQ_API_KEY=your_groq_api_key_here
GROQ_WHISPER_MODEL=whisper-large-v3
GROQ_CHUNK_DURATION=600
GROQ_CHUNK_OVERLAP=5
GROQ_MAX_FILE_SIZE_MB=25

# Prometheus
PROMETHEUS_ENABLED=true
PROMETHEUS_PATH=/metrics
```

See [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md) for complete configuration options.

### YAML Configuration (Recommended)

Create a `config.yaml` file in the project root for runtime settings:

```yaml
# Rate Limiting - Prevents IP blocking
rate_limiting:
  enabled: true
  min_delay: 2.0        # Random delay between 2-5 seconds
  max_delay: 5.0
  retry_delay: 10.0     # Base delay for exponential backoff
  max_retries: 3

# YouTube API Settings
youtube_api:
  use_cookies: true     # Use browser cookies to avoid detection
  cookie_cache_hours: 24
  timeout: 30
  languages:
    - en
    - en-US

# Batch Processing
batch:
  default_size: 5       # Default videos per batch
  show_progress: true

# Groq Whisper API Settings
groq:
  whisper_model: whisper-large-v3
  chunk_duration: 600
  chunk_overlap: 5
  max_file_size_mb: 25

# Pipeline Settings
pipeline:
  work_dir: /tmp/transcription_pipeline
  cache_dir: /tmp/transcription_cache
  enable_cache: true
  save_to_db: true
```

### Environment Variables (.env)

Environment variables take precedence over `config.yaml`:

```bash
# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=video_pipeline

# Groq Whisper API
GROQ_API_KEY=your_groq_api_key_here
GROQ_WHISPER_MODEL=whisper-large-v3
GROQ_CHUNK_DURATION=600
GROQ_CHUNK_OVERLAP=5
GROQ_MAX_FILE_SIZE_MB=25
```

## MCP Integration

The pipeline includes an MCP (Model Context Protocol) server for AI assistant integration.

### Running the MCP Server

```bash
uv run python -m src.mcp.server
```

### Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "youtube-transcription": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp.server"],
      "cwd": "/home/muham/development/youtube-content-pipeline"
    }
  }
}
```

### Available Tools

- `transcribe_video` - Transcribe a YouTube video
- `get_transcript` - Retrieve a transcript by video ID
- `list_transcripts` - List all transcripts
- `get_job_status` - Check job status
- `add_channel` - Add channel to tracking
- `list_channels` - List all tracked channels
- `remove_channel` - Remove channel from tracking
- `sync_channel` - Sync channel videos
- `list_channel_videos` - List videos for a channel
- `transcribe_channel_pending` - Transcribe pending videos

See [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md) for detailed setup.

---

## Monitoring

### Prometheus Metrics

Metrics are exposed at `/metrics`:

- API request rates and latency
- Transcription job metrics
- Database operation metrics
- Redis operation metrics

### Health Checks

| Endpoint | Description |
|----------|-------------|
| `/health` | Basic liveness probe |
| `/health/ready` | Readiness probe (checks dependencies) |
| `/health/detailed` | Comprehensive health status |

### Grafana Dashboard

Set up Prometheus and Grafana for monitoring:

```bash
# See Prometheus WSL setup guide
```

See [PROMETHEUS_WSL_SETUP.md](PROMETHEUS_WSL_SETUP.md) for complete monitoring setup.

---

## Architecture

### Pipeline Architecture

```
YouTube URL / Local Video
    |
Step 1: Get Transcript
    ├── YouTube Transcript API (fast)
    └── Fallback: yt-dlp + Groq Whisper API (with cookies)
    |
Step 2: Save to MongoDB
    └── Full transcript with timestamps
```

### API Architecture

```
Client Request
    |
Rate Limiter (Redis/Memory)
    |
API Key Authentication (optional)
    |
FastAPI Router
    |
├── Videos Router → Transcription Job
├── Transcripts Router → MongoDB
└── Health Router → Component Checks
    |
Prometheus Metrics (all requests)
```

### MCP Architecture

```
AI Assistant (Claude, etc.)
    |
MCP Protocol (STDIO/SSE)
    |
MCP Server (FastMCP)
    |
├── Tools → Transcription API
├── Resources → MongoDB
└── Prompts → Workflow Templates
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
├── __main__.py                 # Package entry point
├── channel/                    # Channel tracking module
│   ├── __init__.py
│   ├── resolver.py            # Handle → Channel ID
│   ├── feed_fetcher.py        # RSS + yt-dlp fetching
│   ├── sync.py                # Sync logic
│   └── schemas.py             # Channel/Video schemas
├── cli/                        # CLI interface
│   ├── __init__.py            # Main CLI entry
│   ├── __main__.py            # Module entry point
│   └── commands/
│       ├── channel.py         # Channel commands
│       ├── cookie.py          # Cookie management
│       ├── transcription.py   # Transcription commands
│       └── utils.py           # Utility commands
├── api/
│   ├── main.py                # FastAPI app
│   ├── app.py                 # App factory
│   ├── dependencies.py        # FastAPI dependencies
│   ├── security.py            # API key authentication
│   ├── middleware/
│   │   ├── prometheus.py      # Prometheus metrics
│   │   ├── rate_limiter.py    # Rate limiting
│   │   ├── error_handler.py   # Error handling
│   │   └── logging.py         # Request logging
│   ├── routers/
│   │   ├── videos.py          # Transcription endpoints
│   │   ├── transcripts.py     # Transcript retrieval
│   │   ├── channels.py        # Channel management
│   │   ├── stats.py           # Statistics endpoint
│   │   └── health.py          # Health checks
│   └── models/
│       ├── requests.py        # Request models
│       └── errors.py          # Error models
├── core/
│   ├── config.py              # Configuration settings
│   ├── constants.py           # Application constants
│   ├── exceptions.py          # Custom exceptions
│   ├── schemas.py             # Pydantic models
│   ├── logging_config.py      # Logging configuration
│   ├── http_session.py        # HTTP session management
│   └── utils.py               # Utility functions
├── services/                   # Business logic services
│   ├── channel_service.py     # Channel operations
│   ├── transcription_service.py # Transcription logic
│   └── video_service.py       # Video operations
├── pipeline/
│   └── transcript.py          # Main pipeline
├── transcription/
│   ├── handler.py             # Transcription with fallback
│   ├── groq_provider.py       # Groq Whisper API provider
│   ├── whisper_provider.py    # Whisper provider abstraction
│   ├── youtube_api.py         # YouTube transcript API
│   └── youtube_downloader.py  # yt-dlp integration
├── video/
│   └── cookie_manager.py      # Browser cookie management
├── database/
│   ├── manager.py             # Database manager
│   └── redis.py               # Redis integration
└── mcp/
    ├── server.py              # MCP server
    ├── config.py              # MCP configuration
    ├── tools/
    │   ├── transcription.py   # Transcription tools
    │   ├── transcripts.py     # Transcript tools
    │   └── channels.py        # Channel tools
    ├── resources/
    │   ├── transcripts.py     # Transcript resources
    │   └── jobs.py            # Job resources
    └── prompts/
        ├── transcribe.py      # Transcription prompts
        └── channel_sync.py    # Channel sync prompts
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

Cookies are automatically extracted from Chrome and used for:
- YouTube video downloads (yt-dlp)
- YouTube Transcript API requests (makes requests less detectable)

```bash
# Check cookie status
uv run python -m src.video.cookie_manager --status

# Force re-extraction
uv run python -m src.video.cookie_manager --invalidate
```

Cookies are cached for 24 hours by default (configurable in `config.yaml`).

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_pipeline.py -v
```

## Documentation

| Document | Description |
|----------|-------------|
| [README.md](README.md) | Overview and quick start |
| [API_USAGE_GUIDE.md](API_USAGE_GUIDE.md) | Complete API usage with examples |
| [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md) | MCP server setup and usage |
| [PROMETHEUS_WSL_SETUP.md](PROMETHEUS_WSL_SETUP.md) | Prometheus and Grafana setup |
| [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md) | All configuration options |
| [CHANNEL_SYNC_GUIDE.md](CHANNEL_SYNC_GUIDE.md) | Channel sync strategies |
| [AGENTS.md](AGENTS.md) | Development guidelines |

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Spec**: http://localhost:8000/openapi.json

## Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copy application
COPY src/ ./src/
COPY config.yaml ./

# Set environment variables
ENV PYTHONPATH=/app
ENV MONGODB_URL=mongodb://mongo:27017
ENV REDIS_URL=redis://redis:6379

# Run application
CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MONGODB_URL=mongodb://mongo:27017
      - REDIS_URL=redis://redis:6379
    depends_on:
      - mongo
      - redis

  mongo:
    image: mongo:7
    volumes:
      - mongo_data:/data/db

  redis:
    image: redis:7
    volumes:
      - redis_data:/data

  prometheus:
    image: prom/prometheus:v2.47.0
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:10.1.0
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

volumes:
  mongo_data:
  redis_data:
```

### Kubernetes (Basic)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: transcription-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: transcription-api
  template:
    metadata:
      labels:
        app: transcription-api
    spec:
      containers:
      - name: api
        image: transcription-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: MONGODB_URL
          valueFrom:
            secretKeyRef:
              name: mongo-secret
              key: url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: url
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 20
```

### Security Considerations

1. **API Keys**: Use strong, unique API keys. Rotate regularly.
2. **HTTPS**: Always use HTTPS in production.
3. **Rate Limiting**: Enable rate limiting to prevent abuse.
4. **Database**: Use authentication and TLS for MongoDB/Redis.
5. **Secrets**: Store secrets in environment variables or secret manager.
6. **Monitoring**: Enable Prometheus metrics and set up alerts.

---

## License

MIT
