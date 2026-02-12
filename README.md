# YouTube Content Pipeline

A production-ready LLM-driven pipeline for analyzing YouTube videos with intelligent transcript and visual analysis. Features 3-agent architecture, automatic cookie management, and robust schema validation with LLM-based repair.

## Features

### LLM-Driven 3-Agent Pipeline
- **Agent 1** (Gemini 2.5 Flash) - Transcript intelligence extraction
  - Trading signals, price levels, patterns
  - Frame extraction planning
  - Content classification
  
- **Agent 2** (qwen3-vl-plus) - Visual frame analysis
  - Batch frame analysis at key moments
  - Chart pattern recognition
  - Duplicate removal
  
- **Agent 3** (Gemini 2.5 Flash) - Synthesis
  - Combines transcript + visual data
  - Resolves conflicts
  - Generates executive summary

### Robust Error Handling (NEW)
- **Hybrid Schema Validation**
  - Phase 1: Programmatic normalization (enums, types)
  - Phase 2: Programmatic fixes (defaults, fuzzy matching)
  - Phase 3: LLM-based repair for complex errors
  - Prevents data loss from validation failures
  
- **JSON Repair**
  - Automatic fixing of malformed JSON
  - Escape newlines, fix trailing commas
  - Extract partial data when possible

### Transcription Fallback Chain
- **YouTube videos**: Try YouTube Transcript API first, fallback to yt-dlp + Whisper
- **Local videos**: Direct OpenVINO Whisper transcription
- Uses browser cookies for authenticated downloads
- OpenVINO Whisper with model caching for performance

### Auto Cookie Management
- Automatic extraction from Chrome
- 24-hour cache with auto-refresh
- No manual setup required
- Used for both video and audio downloads

### Adaptive Price Level Normalization
- Context-aware classification
- Self-improving SQLite database
- CLI tools for review and correction
- Fuzzy matching for LLM output variations

### E2E Testing Framework
- Real video testing (not mocked)
- All 3 LLM agents executed
- Validates complete data flow
- Detailed timing and metrics

## Installation

```bash
# Clone repository
git clone <repository-url>
cd youtube-content-pipeline

# Install dependencies
uv sync

# Or with pip
pip install -e ".[dev]"
```

### Requirements

- Python 3.12+
- FFmpeg (for video processing)
- MongoDB (optional, for data storage)
- Chrome browser (for cookie extraction)
- Deno or Node.js (for YouTube JS challenges)

## Quick Start

### Analyze a YouTube Video

```bash
# Basic analysis
uv run python -m src.cli analyze "https://youtube.com/watch?v=VIDEO_ID"

# With verbose output
uv run python -m src.cli analyze "https://youtube.com/watch?v=VIDEO_ID" --verbose

# Save to file
uv run python -m src.cli analyze "URL" --output analysis.json

# Skip database save
uv run python -m src.cli analyze "URL" --no-db
```

### Analyze a Local Video

```bash
# Local video file
uv run python -m src.cli analyze "/path/to/video.mp4" --verbose
```

### Check Cookie Status

```bash
# Check if cookies are working
uv run python -m src.video.cookie_manager --status

# Force re-extraction
uv run python -m src.video.cookie_manager --invalidate
```

### Run E2E Test

```bash
# Test with specific video
uv run python agent_laboratory/framework/run_e2e_test.py

# Or use the CLI
uv run python -m src.cli analyze "https://youtube.com/watch?v=KgSEzvGOBio" --verbose
```

## Configuration

Create a `.env` file:

```bash
# MongoDB (optional)
MONGODB_URL=mongodb+srv://user:password@cluster.mongodb.net/
MONGODB_DATABASE=video_pipeline

# LLM API
LLM_API_BASE=http://localhost:8087/v1
LLM_API_KEY=sk-dummy

# Model Selection
LLM_TRANSCRIPT_MODEL=gemini-2.5-flash    # Agent 1
LLM_FRAME_MODEL=qwen3-vl-plus             # Agent 2  
LLM_SYNTHESIS_MODEL=gemini-2.5-flash      # Agent 3

# Schema Repair (NEW)
ENABLE_LLM_REPAIR=true                    # Enable LLM fallback
LLM_REPAIR_TEMPERATURE=0.1               # Low temp for precision

# Cookie Management (NEW)
COOKIE_CACHE_HOURS=24                    # Auto-refresh cookies daily
AUTO_EXTRACT_COOKIES=true                # Auto-extract from Chrome

# Video Processing
VIDEO_RESOLUTION=720p                    # 720p for faster download
MAX_FRAMES_TO_EXTRACT=20                 # Limit API calls
FRAME_BATCH_SIZE=15                      # Batch size for frame analysis

# Processing
PIPELINE_WORK_DIR=/tmp/llm_video_analysis
PIPELINE_ENABLE_CACHE=true
PIPELINE_SAVE_TO_DB=true              # Enable MongoDB save (requires MONGODB_URL)

# Timeouts
TRANSCRIPT_TIMEOUT=60
FRAME_TIMEOUT=90
SYNTHESIS_TIMEOUT=60

# Whisper (for fallback transcription)
OPENVINO_WHISPER_MODEL=openai/whisper-base
OPENVINO_DEVICE=AUTO                   # AUTO, GPU, or CPU
```

## Architecture

### 3-Agent Pipeline Flow

```
YouTube URL / Local Video
    |
Transcript Acquisition
    ├── YouTube Transcript API (fast)
    └── Fallback: yt-dlp + OpenVINO Whisper (with cookies)
    |
Agent 1: Transcript Intelligence (Gemini 2.5 Flash)
    ├── Content classification
    ├── Trading signals extraction
    ├── Price level identification
    └── Frame extraction planning
    |
Video Download (YouTube only, with cookies)
    |
Frame Extraction (FFmpeg, using LLM plan)
    |
Agent 2: Frame Intelligence (qwen3-vl-plus)
    ├── Batch frame analysis
    ├── Chart pattern recognition
    └── Duplicate removal
    |
Agent 3: Synthesis (Gemini 2.5 Flash)
    ├── Combines transcript + visual data
    ├── Resolves conflicts
    └── Generates executive summary
    |
Structured Result
    ├── JSON file
    └── MongoDB (if configured)
```

### Schema Validation Flow (NEW)

```
LLM Output
    |
JSON Repair (syntax fixes)
    |
Parse JSON
    |
Phase 1: Programmatic Normalization
    - Enum normalization
    - Type coercion
    |
Validate
    |--PASS?--> Success
    |--FAIL-->
Phase 2: Programmatic Fixes
    - Fuzzy matching
    - Default values
    |
Validate
    |--PASS?--> Success
    |--FAIL-->
Phase 3: LLM Schema Repair
    - Context-aware fixes
    - Hallucination prevention
    |
Validate
    |--PASS?--> Success
    |--FAIL--> Error
```

### Auto Cookie Management

Browser cookies are automatically used for:
- **Video downloads** (YouTube videos for frame extraction)
- **Audio downloads** (for Whisper transcription fallback)

```
Download Request
    |
Check Cookie Cache
    |
Fresh cookies (<24h)?
    |--YES--> Use cached cookies
    |--NO-->
Auto-extract from Chrome
    |
Validate auth cookies
    |
Cache for 24 hours
    |
Use for download
```

## Project Structure

```
src/
├── __init__.py                 # Package exports
├── __main__.py                 # Module entry point
├── cli.py                      # Main CLI interface
├── database.py                 # MongoDB integration
├── core/
│   ├── __init__.py
│   ├── config.py               # Configuration settings
│   ├── exceptions.py           # Custom exceptions
│   ├── models.py               # Dataclass models
│   ├── normalizer.py           # Price level normalization
│   └── schemas.py              # Pydantic models
├── llm_agents/
│   ├── __init__.py
│   ├── base.py                 # Base agent with 3-phase validation
│   ├── batch_processor.py      # Chunked transcript processing
│   ├── factory.py              # LLM client factory
│   ├── frame_agent.py          # Agent 2: Frame analysis
│   ├── prompts/                # Prompt templates
│   ├── response_utils.py       # JSON repair & normalization
│   ├── schema_repair_agent.py  # LLM schema repair
│   ├── synthesis_agent.py      # Agent 3: Synthesis
│   └── transcript_agent.py     # Agent 1: Transcript analysis
├── pipeline/
│   ├── __init__.py
│   └── llm_driven.py           # Main orchestrator
├── transcription/
│   ├── __init__.py
│   ├── handler.py              # Transcription with fallback
│   └── whisper_openvino.py     # OpenVINO Whisper implementation
└── video/
    ├── __init__.py
    ├── cookie_manager.py       # Browser cookie management
    └── handler.py              # Video download & frame extraction

agent_laboratory/               # Testing & documentation
├── framework/
│   ├── README.md
│   └── run_e2e_test.py         # E2E test runner
├── extract_cookies.py          # Manual cookie extraction
├── *.md                        # Implementation documentation
├── logs/                       # Test logs (gitignored)
└── results/                    # Test results (gitignored)
```

## Advanced Usage

### Manage Price Level Normalizations

```bash
# Review recent normalizations
uv run python -m src.cli review-normalizations --limit 20

# Show low confidence (need review)
uv run python -m src.cli review-normalizations --max-confidence 0.5

# Show statistics
uv run python -m src.cli review-normalizations --stats

# Correct a normalization
uv run python -m src.cli correct-normalization 42 entry
```

### Programmatic API

```python
from src.pipeline.llm_driven import analyze_video

# Analyze a YouTube video
result = analyze_video(
    source="https://youtube.com/watch?v=VIDEO_ID"
)

# Or analyze a local video
result = analyze_video(
    source="/path/to/local/video.mp4"
)

# Access structured data
print(result.video_id)
print(result.content_type)                    # "bitcoin_analysis"
print(len(result.transcript_intelligence.signals))   # Number of signals
print(result.synthesis.executive_summary)
```

### Custom Configuration

```python
from src.video.handler import VideoHandler
from src.video.cookie_manager import get_cookie_manager

# Custom cookie settings
handler = VideoHandler(
    cookie_cache_hours=12,        # Refresh every 12 hours
    auto_extract_cookies=True
)

# Or use cookie manager directly
manager = get_cookie_manager(cache_duration_hours=6)
manager.ensure_cookies()
manager.invalidate_cache()  # Force refresh
```

### Database Operations

```python
import asyncio
from src.database import get_db_manager

async def db_operations():
    db = get_db_manager()
    
    # Save analysis
    doc_id = await db.save_analysis(result)
    print(f"Saved with ID: {doc_id}")
    
    # Retrieve analysis
    doc = await db.get_analysis("video_id_123")
    
    # List analyses with filters
    results = await db.list_analyses(
        limit=10,
        content_type="bitcoin_analysis",
        primary_asset="BTC"
    )
    
    # Get count
    count = await db.get_analysis_count(content_type="bitcoin_analysis")
    
    await db.close()

# Run async operations
asyncio.run(db_operations())
```

## Testing

### E2E Test Framework

```bash
# Run full E2E test (all 3 agents + database)
uv run python agent_laboratory/framework/run_e2e_test.py

# Or test via CLI
uv run python -m src.cli analyze "https://youtube.com/watch?v=KgSEzvGOBio" --verbose
```

**E2E Test validates:**
1. Transcript acquisition (YouTube API with Whisper fallback)
2. Agent 1: Transcript Intelligence
3. Video download (with cookies)
4. Frame extraction (FFmpeg)
5. Agent 2: Frame Intelligence (Vision)
6. Agent 3: Synthesis
7. Result structure validation
8. MongoDB save (if configured)



## Performance

### Typical Processing Times

| Step | Time | Notes |
|------|------|-------|
| Transcript acquisition (YouTube API) | 2-5s | Fast path |
| Transcript acquisition (Whisper fallback) | 30-120s | Download + transcribe |
| Agent 1 (Transcript) | 60-120s | Depends on length |
| Video download | 30-60s | With cookies |
| Frame extraction | 5-10s | FFmpeg |
| Agent 2 (Frames) | 30-60s | Batch analysis |
| Agent 3 (Synthesis) | 10-20s | Final combine |
| LLM Schema Repair | +2-4s | Only when needed |
| **Total** | **2-5 min** | Typical YouTube video |

## Documentation

### Implementation Details
- `REFACTORING_SUMMARY.md` - Summary of recent codebase refactoring
- `CODEBASE_AUDIT_REPORT.md` - Full codebase audit and recommendations

### Agent Laboratory
- `agent_laboratory/TEST_REPORT.md` - E2E test results
- `agent_laboratory/IMPLEMENTATION_SUMMARY.md` - JSON repair & normalization
- `agent_laboratory/COOKIE_MANAGER_SUMMARY.md` - Auto cookie extraction
- `agent_laboratory/LLM_REPAIR_SUMMARY.md` - LLM schema repair agent
- `agent_laboratory/YOUTUBE_DOWNLOAD_SOLUTIONS.md` - YouTube download troubleshooting

## License

MIT
