# MCP Integration Guide

Model Context Protocol (MCP) integration for the YouTube Transcription Pipeline.

## Table of Contents

- [What is MCP](#what-is-mcp)
- [Server Configuration](#server-configuration)
- [Available Tools](#available-tools)
- [Available Resources](#available-resources)
- [Available Prompts](#available-prompts)
- [Example Workflows](#example-workflows)
- [Troubleshooting](#troubleshooting)

---

## What is MCP

### Overview

The Model Context Protocol (MCP) is an open protocol that enables AI assistants to interact with external tools and data sources through a standardized interface. MCP allows AI models to:

- **Execute tools** - Call functions with structured parameters
- **Access resources** - Read data from external systems
- **Use prompts** - Leverage pre-defined prompt templates

### Benefits for AI Agents

Integrating the transcription pipeline with MCP provides:

1. **Natural Language Interface** - Users can request transcriptions conversationally
2. **Automated Workflows** - AI can chain multiple operations together
3. **Context Awareness** - AI has access to transcript data for analysis
4. **Standardized Protocol** - Works with any MCP-compatible client

### Architecture

```
┌─────────────────┐     MCP Protocol     ┌──────────────────────┐
│  AI Assistant   │ ◄──────────────────► │  MCP Server          │
│  (Claude, etc.) │                      │  (Python/FastMCP)    │
└─────────────────┘                      └──────────────────────┘
                                                │
                                                ▼
                                       ┌──────────────────────┐
                                       │  Transcription       │
                                       │  Pipeline API        │
                                       └──────────────────────┘
                                                │
                                                ▼
                                       ┌──────────────────────┐
                                       │  MongoDB / Redis     │
                                       └──────────────────────┘
```

---

## Server Configuration

### Running the MCP Server

The MCP server runs as a standalone Python process:

```bash
# Run with STDIO transport (default)
uv run python -m src.mcp.server

# Run with debug logging
uv run python -m src.mcp.server --log-level debug
```

### Claude Desktop Configuration

To use the MCP server with Claude Desktop:

1. **Locate Claude Desktop config file**:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. **Add server configuration**:

```json
{
  "mcpServers": {
    "youtube-transcription": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp.server"],
      "cwd": "/home/muham/development/youtube-content-pipeline",
      "env": {
        "MONGODB_URL": "mongodb://localhost:27017",
        "REDIS_URL": "redis://localhost:6379"
      }
    }
  }
}
```

3. **Restart Claude Desktop**

4. **Verify connection**:
   - Open Claude Desktop
   - Click the hammer icon (Developer Tools)
   - Check MCP servers section

### VS Code Extension Setup

For the MCP VS Code extension:

1. **Install the MCP extension** from VS Code marketplace

2. **Configure in settings.json**:

```json
{
  "mcp.servers": {
    "youtube-transcription": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp.server"],
      "cwd": "/home/muham/development/youtube-content-pipeline"
    }
  }
}
```

3. **Reload VS Code window**

### Testing with MCP Inspector

The MCP Inspector is a debugging tool for testing MCP servers:

```bash
# Install inspector
npx @modelcontextprotocol/inspector uv run python -m src.mcp.server

# Opens web UI at http://localhost:5173
```

The Inspector provides:
- Tool testing interface
- Resource browser
- Prompt testing
- Connection debugging

### Other MCP Clients

The server is compatible with any MCP client:

| Client | Configuration |
|--------|---------------|
| **Claude Desktop** | JSON config file |
| **VS Code Extension** | settings.json |
| **Windsurf** | Built-in MCP support |
| **Cursor** | MCP server configuration |
| **Custom Clients** | STDIO or SSE transport |

---

## Available Tools

The MCP server exposes the following tools:

### transcribe_video

Transcribe a YouTube video or audio file.

**Description**: Transcribe a YouTube video or audio file. Supports YouTube URLs, video IDs, and local audio files. Automatically uses YouTube Transcript API first, then falls back to Whisper. Returns the full transcript with timestamps.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source` | string | Yes | - | Video source (URL, ID, or file path) |
| `priority` | string | No | `"normal"` | Job priority: `"low"`, `"normal"`, `"high"` |
| `save_to_db` | boolean | No | `true` | Save transcript to database |
| `webhook_url` | string | No | `null` | Webhook URL for completion notification |

**Example Usage**:

```json
{
  "name": "transcribe_video",
  "arguments": {
    "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "priority": "normal",
    "save_to_db": true
  }
}
```

**Response**:

```json
{
  "job_id": "job_dQw4w9WgXcQ_20240115103000",
  "status": "completed",
  "video_id": "dQw4w9WgXcQ",
  "transcript_source": "youtube_api",
  "segment_count": 45,
  "duration_seconds": 212.5,
  "full_text": "Hello world. Welcome to this video...",
  "segments": [
    {"start": 0.0, "end": 5.0, "text": "Hello world"},
    {"start": 5.0, "end": 10.0, "text": "Welcome to this video"}
  ]
}
```

---

### get_transcript

Retrieve a transcript by video ID.

**Description**: Retrieve a transcript by video ID. Returns the full transcript document including all segments with timestamps.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `video_id` | string | Yes | YouTube video ID (11 characters) |

**Example Usage**:

```json
{
  "name": "get_transcript",
  "arguments": {
    "video_id": "dQw4w9WgXcQ"
  }
}
```

**Response**:

```json
{
  "_id": "507f1f77bcf86cd799439011",
  "video_id": "dQw4w9WgXcQ",
  "title": "Example Video",
  "channel_name": "Example Channel",
  "duration_seconds": 212.5,
  "language": "en",
  "transcript_source": "youtube_api",
  "segments": [
    {"start": 0.0, "end": 5.0, "text": "Hello world"}
  ],
  "full_text": "Hello world. Welcome to this video...",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### list_transcripts

List all transcripts with optional filtering.

**Description**: List all transcripts with optional filtering. Results are sorted by creation date (newest first). Returns metadata only, not full segments.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 100 | Maximum transcripts to return |
| `offset` | integer | No | 0 | Number of transcripts to skip |
| `transcript_source` | string | No | null | Filter by source |
| `language` | string | No | null | Filter by language code |

**Example Usage**:

```json
{
  "name": "list_transcripts",
  "arguments": {
    "limit": 10,
    "offset": 0,
    "transcript_source": "youtube_api",
    "language": "en"
  }
}
```

**Response**:

```json
{
  "total": 150,
  "transcripts": [
    {
      "_id": "507f1f77bcf86cd799439011",
      "video_id": "dQw4w9WgXcQ",
      "title": "Example Video",
      "language": "en",
      "transcript_source": "youtube_api",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "pagination": {
    "limit": 10,
    "offset": 0,
    "has_more": true
  }
}
```

---

### get_job_status

Check the status of a transcription job.

**Description**: Check the status of a transcription job. Note: Transcription is synchronous, so jobs complete immediately.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | Yes | Job identifier (UUID format) |

**Example Usage**:

```json
{
  "name": "get_job_status",
  "arguments": {
    "job_id": "job_dQw4w9WgXcQ_20240115103000"
  }
}
```

**Response**:

```json
{
  "job_id": "job_dQw4w9WgXcQ_20240115103000",
  "status": "completed",
  "video_id": "dQw4w9WgXcQ",
  "progress_percent": 100.0,
  "current_step": "Completed",
  "result_url": "/api/v1/transcripts/dQw4w9WgXcQ"
}
```

---

### add_channel

Add a YouTube channel to tracking.

**Description**: Add a YouTube channel to tracking. Resolves channel handle to channel ID and saves to database.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `handle` | string | Yes | YouTube channel handle (with or without @) |

**Example Usage**:

```json
{
  "name": "add_channel",
  "arguments": {
    "handle": "@ChartChampions"
  }
}
```

**Response**:

```json
{
  "channel_id": "UCHOP_YfwdMk5hpxbugzC1wA",
  "handle": "@ChartChampions",
  "title": "Chart Champions",
  "status": "added"
}
```

---

### sync_channel

Sync videos from a YouTube channel.

**Description**: Sync videos from a YouTube channel. Fetches video metadata and marks videos as pending transcription. Use mode='recent' for ~15 latest videos, or mode='all' for complete history.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `handle` | string | Yes | - | YouTube channel handle |
| `mode` | string | No | `"recent"` | Sync mode: `"recent"` or `"all"` |

**Example Usage**:

```json
{
  "name": "sync_channel",
  "arguments": {
    "handle": "@ChartChampions",
    "mode": "recent"
  }
}
```

**Response**:

```json
{
  "channel_id": "UCHOP_YfwdMk5hpxbugzC1wA",
  "handle": "@ChartChampions",
  "videos_fetched": 15,
  "videos_pending": 12,
  "status": "completed"
}
```

---

### transcribe_channel_pending

Transcribe all pending videos from a channel.

**Description**: Transcribe all pending videos from a channel. Finds untranscribed videos and submits them for transcription.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `handle` | string | Yes | - | YouTube channel handle |
| `limit` | integer | No | 10 | Maximum videos to transcribe |

**Example Usage**:

```json
{
  "name": "transcribe_channel_pending",
  "arguments": {
    "handle": "@ChartChampions",
    "limit": 5
  }
}
```

**Response**:

```json
{
  "channel_id": "UCHOP_YfwdMk5hpxbugzC1wA",
  "submitted": 5,
  "jobs": [
    {
      "job_id": "job_abc123",
      "video_id": "video123",
      "status": "completed"
    }
  ]
}
```

---

### list_channels

List all tracked YouTube channels.

**Description**: List all tracked YouTube channels. Returns channels sorted by when they were added (newest first).

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 100 | Maximum channels to return |

**Example Usage**:

```json
{
  "name": "list_channels",
  "arguments": {
    "limit": 50
  }
}
```

**Response**:

```json
{
  "success": true,
  "channels": [
    {
      "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
      "channel_handle": "MrBeast",
      "channel_title": "MrBeast",
      "video_count": 750
    }
  ],
  "total": 5
}
```

---

### remove_channel

Remove a channel from tracking.

**Description**: Remove a channel from tracking. Video metadata and transcripts are preserved.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `channel_id` | string | Yes | YouTube channel ID (e.g., UCX6OQ3DkcsbYNE6H8uQQuVA) |

**Example Usage**:

```json
{
  "name": "remove_channel",
  "arguments": {
    "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA"
  }
}
```

**Response**:

```json
{
  "success": true,
  "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
  "message": "Channel UCX6OQ3DkcsbYNE6H8uQQuVA removed from tracking"
}
```

---

### list_channel_videos

List videos for a specific channel.

**Description**: List videos for a specific channel. Returns video metadata sorted by publication date.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `channel_id` | string | Yes | - | YouTube channel ID |
| `limit` | integer | No | 100 | Maximum videos to return |
| `offset` | integer | No | 0 | Number of videos to skip |

**Example Usage**:

```json
{
  "name": "list_channel_videos",
  "arguments": {
    "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
    "limit": 20,
    "offset": 0
  }
}
```

**Response**:

```json
{
  "success": true,
  "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
  "channel_title": "MrBeast",
  "videos": [
    {
      "video_id": "dQw4w9WgXcQ",
      "title": "Example Video",
      "duration_seconds": 212.5,
      "transcript_status": "completed"
    }
  ],
  "total": 20,
  "total_in_channel": 750
}
```

---

## Available Resources

Resources provide read-only access to data:

### transcript://{video_id}

Access transcript content by video ID.

**URI Pattern**: `transcript://{video_id}`

**Description**: Access transcript content by video ID. Returns full transcript with segments.

**MIME Type**: `application/json`

**Example**:

```
transcript://dQw4w9WgXcQ
```

**Response**:

```json
{
  "_id": "507f1f77bcf86cd799439011",
  "video_id": "dQw4w9WgXcQ",
  "title": "Example Video",
  "segments": [...],
  "full_text": "..."
}
```

---

### job://{job_id}

Access transcription job status by job ID.

**URI Pattern**: `job://{job_id}`

**Description**: Access transcription job status by job ID.

**MIME Type**: `application/json`

**Example**:

```
job://job_dQw4w9WgXcQ_20240115103000
```

**Response**:

```json
{
  "job_id": "job_dQw4w9WgXcQ_20240115103000",
  "status": "completed",
  "video_id": "dQw4w9WgXcQ",
  "progress_percent": 100.0
}
```

---

## Available Prompts

Prompts provide pre-defined templates for common workflows:

### transcribe-video

Transcribe a YouTube video with optional settings.

**Description**: Transcribe a YouTube video with optional settings. Provides context for the transcription workflow.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source` | string | Yes | - | Video source |
| `priority` | string | No | `"normal"` | Job priority |
| `language` | string | No | `"auto-detect"` | Target language |

**Example Usage**:

```json
{
  "name": "transcribe-video",
  "arguments": {
    "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "priority": "high",
    "language": "en"
  }
}
```

**Generated Prompt**:

```
I'll help you transcribe this YouTube video.

Video: https://youtube.com/watch?v=dQw4w9WgXcQ
Priority: high
Language: English (auto-detect if not specified)

I'll use the transcribe_video tool to process this video. The transcription will:
1. First attempt to fetch from YouTube's transcript API
2. Fall back to Whisper transcription if needed
3. Save the transcript to the database

Would you like me to proceed with the transcription?
```

---

### sync-channel

Sync and transcribe all videos from a YouTube channel.

**Description**: Sync and transcribe all videos from a YouTube channel. Provides context for the complete channel workflow.

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `handle` | string | Yes | - | Channel handle |
| `limit` | integer | No | 10 | Maximum videos to process |
| `mode` | string | No | `"recent"` | Sync mode |

**Example Usage**:

```json
{
  "name": "sync-channel",
  "arguments": {
    "handle": "@ChartChampions",
    "limit": 10,
    "mode": "recent"
  }
}
```

**Generated Prompt**:

```
I'll help you sync and transcribe videos from this YouTube channel.

Channel: @ChartChampions
Mode: recent (latest ~15 videos)
Limit: 10 videos to transcribe

Workflow:
1. Add channel to tracking (if not already tracked)
2. Sync latest videos from the channel
3. Transcribe pending videos (up to 10)

This process will:
- Fetch video metadata from YouTube
- Mark videos as pending transcription
- Process transcriptions sequentially

Would you like me to proceed?
```

---

## Example Workflows

### Workflow 1: Transcribe a Single Video

**User Request**: "Transcribe this video: https://youtube.com/watch?v=dQw4w9WgXcQ"

**AI Actions**:

```json
// Step 1: Call transcribe_video tool
{
  "name": "transcribe_video",
  "arguments": {
    "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "priority": "normal",
    "save_to_db": true
  }
}

// Response received
{
  "job_id": "job_abc123",
  "status": "completed",
  "video_id": "dQw4w9WgXcQ",
  "full_text": "Hello world...",
  "segments": [...]
}

// Step 2: Present results to user
"Here's the transcript for the video:

**Title**: Example Video
**Duration**: 3:32
**Source**: YouTube API

**Full Transcript**:
Hello world. Welcome to this video...

[View full transcript with timestamps]"
```

---

### Workflow 2: Sync and Transcribe Channel

**User Request**: "Sync and transcribe the latest videos from @ChartChampions"

**AI Actions**:

```json
// Step 1: Add channel (if needed)
{
  "name": "add_channel",
  "arguments": {
    "handle": "@ChartChampions"
  }
}

// Step 2: Sync channel
{
  "name": "sync_channel",
  "arguments": {
    "handle": "@ChartChampions",
    "mode": "recent"
  }
}

// Step 3: Transcribe pending videos
{
  "name": "transcribe_channel_pending",
  "arguments": {
    "handle": "@ChartChampions",
    "limit": 10
  }
}

// Step 4: Report results
"I've synced @ChartChampions and transcribed 10 videos:

- Fetched 15 videos from the channel
- 12 videos were pending transcription
- Successfully transcribed 10 videos

You can view the transcripts or continue with more videos."
```

---

### Workflow 3: Search and Analyze Transcripts

**User Request**: "Find all transcripts about Python programming"

**AI Actions**:

```json
// Step 1: List transcripts
{
  "name": "list_transcripts",
  "arguments": {
    "limit": 100,
    "language": "en"
  }
}

// Step 2: Read individual transcripts
{
  "name": "get_transcript",
  "arguments": {
    "video_id": "video123"
  }
}

// Step 3: Analyze content (using AI's native capabilities)
// AI reads full_text and searches for Python-related content

// Step 4: Present findings
"I found 5 transcripts mentioning Python:

1. **Python Tutorial for Beginners** (video123)
   - Duration: 15:30
   - Mentions: variables, functions, loops

2. **Advanced Python Patterns** (video456)
   - Duration: 22:45
   - Mentions: decorators, generators, context managers

[... more results ...]"
```

---

### Workflow 4: Batch Processing

**User Request**: "Transcribe all videos from my tracked channels"

**AI Actions**:

```json
// Step 1: List all tracked channels (via database query)
// Step 2: For each channel:
{
  "name": "sync_channel",
  "arguments": {
    "handle": "@Channel1",
    "mode": "recent"
  }
}
{
  "name": "transcribe_channel_pending",
  "arguments": {
    "handle": "@Channel1",
    "limit": 20
  }
}

// Step 3: Report progress
"Processing 3 tracked channels:

✅ @Channel1: 15 videos synced, 10 transcribed
⏳ @Channel2: Processing...
⏳ @Channel3: Queued

Estimated completion: 30 minutes"
```

---

### Workflow 5: Transcript Summary

**User Request**: "Summarize this transcript: dQw4w9WgXcQ"

**AI Actions**:

```json
// Step 1: Get transcript
{
  "name": "get_transcript",
  "arguments": {
    "video_id": "dQw4w9WgXcQ"
  }
}

// Step 2: Analyze and summarize (using AI's native capabilities)
// AI reads full_text and generates summary

// Step 3: Present summary
"**Video Summary**: Example Video

**Key Points**:
1. Introduction to the topic
2. Main concepts explained
3. Practical examples demonstrated
4. Conclusion and next steps

**Duration**: 3:32
**Language**: English
**Source**: YouTube Auto-generated Transcript"
```

---

## Troubleshooting

### Common Issues

#### Server Not Starting

**Symptom**: MCP client cannot connect to server

**Solutions**:

1. **Check Python environment**:
   ```bash
   # Ensure dependencies are installed
   uv sync
   
   # Test server manually
   uv run python -m src.mcp.server --log-level debug
   ```

2. **Verify working directory**:
   ```json
   {
     "cwd": "/home/muham/development/youtube-content-pipeline"
   }
   ```

3. **Check for errors in logs**:
   ```
   ERROR: Database connection failed
   SOLUTION: Ensure MongoDB is running
   ```

#### Tools Not Appearing

**Symptom**: MCP client doesn't show available tools

**Solutions**:

1. **Restart MCP client** (Claude Desktop, VS Code, etc.)

2. **Verify server configuration**:
   ```bash
   # Test with inspector
   npx @modelcontextprotocol/inspector uv run python -m src.mcp.server
   ```

3. **Check tool registration** in `src/mcp/server.py`

#### Database Connection Errors

**Symptom**: Tools fail with database errors

**Solutions**:

1. **Verify MongoDB is running**:
   ```bash
   mongosh --eval "db.adminCommand('ping')"
   ```

2. **Check connection string**:
   ```bash
   export MONGODB_URL=mongodb://localhost:27017
   ```

3. **Test database connection**:
   ```bash
   uv run python -c "from src.database import get_db_manager; import asyncio; asyncio.run(get_db_manager().client.admin.command('ping'))"
   ```

#### Slow Performance

**Symptom**: Tools take too long to respond

**Solutions**:

1. **Use appropriate sync mode**:
   - `mode: "recent"` for quick sync (~2 seconds)
   - `mode: "all"` only when needed (~1.3s per video)

2. **Limit batch sizes**:
   ```json
   {
     "limit": 10  // Instead of processing all at once
   }
   ```

3. **Enable Redis caching**:
   ```bash
   export REDIS_ENABLED=true
   ```

### Debug Mode

Enable debug logging for troubleshooting:

```bash
uv run python -m src.mcp.server --log-level debug
```

This outputs detailed logs including:
- Tool invocations
- Database queries
- API requests
- Error details

### Testing with Inspector

The MCP Inspector provides a web interface for testing:

```bash
npx @modelcontextprotocol/inspector uv run python -m src.mcp.server
```

Features:
- **Tools Tab**: Test each tool with custom parameters
- **Resources Tab**: Browse available resources
- **Prompts Tab**: Test prompt templates
- **Logs Tab**: View server logs in real-time

### Verifying Connection

Test connection from command line:

```bash
# Test STDIO transport
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}' | \
uv run python -m src.mcp.server
```

Expected response:
```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{},"resources":{},"prompts":{}},"serverInfo":{"name":"youtube-transcription","version":"0.5.0"}}}
```

---

## Best Practices

### 1. Error Handling

Always handle errors gracefully:

```python
try:
    result = await transcribe_video(source=url)
    if result.get('status') == 'failed':
        print(f"Transcription failed: {result.get('error')}")
except Exception as e:
    print(f"Error: {e}")
```

### 2. Rate Limiting

Respect API rate limits when using tools:

```json
{
  "limit": 10  // Process in batches
}
```

### 3. Caching

Use cached transcripts when available:

```python
# Check if transcript exists first
transcript = await get_transcript(video_id)
if transcript:
    return transcript
# Otherwise transcribe
```

### 4. Progress Reporting

Provide progress updates for long operations:

```
"Syncing channel @ChartChampions...
- Fetched 15 videos
- Transcribing video 1/10...
- Transcribing video 2/10...
```

---

## Support

For additional help:

- **MCP Documentation**: https://modelcontextprotocol.io
- **FastMCP Documentation**: https://github.com/jlowin/fastmcp
- **GitHub Issues**: Report bugs and request features
