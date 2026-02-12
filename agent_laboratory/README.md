# Agent Laboratory Documentation Index

Welcome to the Agent Laboratory! This directory contains comprehensive documentation for the YouTube Content Pipeline testing and development framework.

## 📚 Documentation Files

### Core Implementation Docs

1. **[TEST_REPORT.md](./TEST_REPORT.md)** - E2E Test Results
   - Latest test run results (KgSEzvGOBio)
   - Step-by-step validation
   - Performance metrics
   - Success/failure analysis

2. **[IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md)** - JSON Repair & Normalization
   - Complete implementation details
   - JSONRepair class documentation
   - ResponseNormalizer features
   - Test results before/after
   - Code examples

3. **[LLM_REPAIR_SUMMARY.md](./LLM_REPAIR_SUMMARY.md)** - LLM Schema Repair Agent
   - Hybrid validation approach
   - SchemaRepairAgent implementation
   - Anti-hallucination features
   - Detailed diff logging
   - Usage examples

4. **[COOKIE_MANAGER_SUMMARY.md](./COOKIE_MANAGER_SUMMARY.md)** - Auto Cookie Management
   - YouTubeCookieManager architecture
   - 24-hour auto-refresh mechanism
   - Chrome integration
   - Configuration options

5. **[YOUTUBE_DOWNLOAD_SOLUTIONS.md](./YOUTUBE_DOWNLOAD_SOLUTIONS.md)** - Troubleshooting Guide
   - HTTP 403 Forbidden solutions
   - Cookie extraction methods
   - Alternative approaches
   - Quick fixes

### Quick Reference

## 🚀 Quick Start Commands

```bash
# Run E2E Test
uv run python agent_laboratory/framework/run_e2e_test.py

# Check Cookie Status
uv run python -m src.video.cookie_manager --status

# Force Cookie Refresh
uv run python -m src.video.cookie_manager --invalidate

# Analyze Specific Video
uv run python -m src.cli analyze "https://youtube.com/watch?v=VIDEO_ID" --verbose
```

## 📊 Current System Status

### ✅ Implemented Features

1. **3-Agent Pipeline**
   - Agent 1: Transcript Intelligence (Gemini 2.5 Flash)
   - Agent 2: Frame Intelligence (qwen3-vl-plus)
   - Agent 3: Synthesis (Gemini 2.5 Flash)

2. **Robust Error Handling**
   - ✅ JSON syntax repair
   - ✅ Programmatic normalization
   - ✅ LLM-based schema repair (fallback)
   - ✅ Anti-hallucination protection
   - ✅ Detailed diff logging

3. **Auto Cookie Management**
   - ✅ Automatic Chrome extraction
   - ✅ 24-hour cache
   - ✅ Auto-refresh on expiry
   - ✅ Deno/Node.js JS runtime support

4. **Data Preservation**
   - ✅ Batch processing for long transcripts
   - ✅ Chunk merging with deduplication
   - ✅ No data loss from validation failures
   - ✅ Partial data extraction

5. **Transcription Fallback**
   - ✅ YouTube Transcript API (primary)
   - ✅ OpenVINO Whisper fallback (yt-dlp + Whisper)
   - ✅ Browser cookies for authenticated downloads
   - ✅ Local video support (direct Whisper)

### 📈 Performance Metrics

| Metric | Value |
|--------|-------|
| E2E Test Success Rate | 7/7 (100%) |
| Schema Validation Success | ~99% (with repair) |
| Average Repair Time | +2-4s (when needed) |
| Cookie Cache Duration | 24 hours |
| Video Download Success | 100% (with cookies) |

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Request                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              Transcript Acquisition                         │
│         (YouTube API or Whisper fallback)                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Agent 1: Transcript Intelligence (Gemini 2.5 Flash)  │  │
│  │  - Signal extraction                                  │  │
│  │  - Price level detection                              │  │
│  │  - Frame extraction plan                              │  │
│  └──────────────────┬────────────────────────────────────┘  │
│                     │                                       │
│         ┌───────────┴───────────┐                          │
│         │  Schema Validation    │                          │
│         │  (3-phase hybrid)     │                          │
│         └───────────┬───────────┘                          │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Video Download + Frame Extraction              │
│         (yt-dlp with auto cookies + FFmpeg)                │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Agent 2: Frame Intelligence (qwen3-vl-plus)         │  │
│  │  - Visual analysis                                    │  │
│  │  - Chart pattern recognition                          │  │
│  │  - Frame selection                                    │  │
│  └──────────────────┬────────────────────────────────────┘  │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Agent 3: Synthesis (Gemini 2.5 Flash)               │  │
│  │  - Combine transcript + visual                        │  │
│  │  - Resolve conflicts                                  │  │
│  │  - Generate final report                              │  │
│  └──────────────────┬────────────────────────────────────┘  │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                Structured Result                            │
│           (JSON Output → MongoDB/File)                     │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 Key Components

### 1. JSON Repair & Normalization
**Location:** `src/llm_agents/response_utils.py`

```python
# Usage
from src.llm_agents.response_utils import repair_and_normalize_response

data, json_repairs, norm_changes = repair_and_normalize_response(llm_output)
```

**Features:**
- Escape newlines in strings
- Fix trailing commas
- Normalize smart quotes
- Fuzzy match enums
- Type coercion

### 2. LLM Schema Repair
**Location:** `src/llm_agents/schema_repair_agent.py`

```python
# Usage
from src.llm_agents.schema_repair_agent import SchemaRepairAgent

agent = SchemaRepairAgent()
result, log = agent.repair(invalid_data, errors, SchemaClass)
```

**Features:**
- Context-aware fixes
- Hallucination detection
- Detailed diff logging
- Transcript context

### 3. Cookie Manager
**Location:** `src/video/cookie_manager.py`

```python
# Usage
from src.video.cookie_manager import get_cookie_manager

manager = get_cookie_manager(cache_duration_hours=24)
manager.ensure_cookies()  # Auto-extract if needed
```

**Features:**
- Auto-extract from Chrome
- 24-hour cache
- Metadata tracking
- Status checking

## 📖 Reading Guide

### For New Users
1. Start with [TEST_REPORT.md](./TEST_REPORT.md) to understand what the system does
2. Read the main [../README.md](../README.md) for setup instructions
3. Try the Quick Start commands above

### For Developers
1. Read [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md) for JSON repair details
2. Read [LLM_REPAIR_SUMMARY.md](./LLM_REPAIR_SUMMARY.md) for schema validation
3. Read [COOKIE_MANAGER_SUMMARY.md](./COOKIE_MANAGER_SUMMARY.md) for cookie management
4. Check [YOUTUBE_DOWNLOAD_SOLUTIONS.md](./YOUTUBE_DOWNLOAD_SOLUTIONS.md) for troubleshooting

### For Debugging
1. Check cookie status: `uv run python -m src.video.cookie_manager --status`
2. Run E2E test: `uv run python agent_laboratory/framework/run_e2e_test.py`
3. Check logs in `agent_laboratory/logs/`
4. Check results in `agent_laboratory/results/`

## 🎯 Test Results Summary

**Latest E2E Test (2026-02-12):**
- ✅ All 7 steps passed
- ✅ 7 chunks processed (no failures)
- ✅ 10 signals extracted
- ✅ 17 price levels identified
- ✅ 20 frames extracted and analyzed
- ✅ Video downloaded successfully (71.1 MB)
- ✅ Total time: ~5.5 minutes

**Improvements Over Previous Version:**
- Data loss: 0% (was ~30% before repairs)
- Chunk failure rate: 0% (was ~50% before)
- Schema validation: ~99% (was ~85% before)

## 🔗 Quick Links

- [Main README](../README.md)
- [E2E Test Framework](./framework/)
- [Source Code](../src/)
- [Test Results](./results/)
- [Logs](./logs/)

## 📝 Notes

- All documentation is kept in sync with the codebase
- Last updated: 2026-02-12
- Test video: https://www.youtube.com/watch?v=KgSEzvGOBio
- All features tested and production-ready

### Recent Changes (2026-02-12)

1. **Architecture Cleanup**
   - Removed unused `LocalOpenVINOExtractor` pipeline
   - Consolidated to single `LLMDrivenPipeline`
   - Deleted ~1,100 lines of dead code

2. **Database Integration**
   - Rewrote `database.py` to match new schemas
   - MongoDB now saves `transcript_intelligence`, `frame_intelligence`, `synthesis`
   - Async operations with proper ObjectId handling

3. **Transcription Fallback**
   - Integrated Whisper fallback for YouTube API failures
   - Uses browser cookies for audio downloads
   - Local video support via direct Whisper transcription

See [../REFACTORING_SUMMARY.md](../REFACTORING_SUMMARY.md) for complete details.

---

**Questions?** Check the individual documentation files above or run the E2E test to see the system in action!
