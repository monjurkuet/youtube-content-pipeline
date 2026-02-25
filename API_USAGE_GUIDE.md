# API Usage Guide

Comprehensive guide for using the YouTube Transcription Pipeline API.

## Table of Contents

- [Authentication](#authentication)
- [Endpoints](#endpoints)
- [Code Examples](#code-examples)
- [Rate Limiting](#rate-limiting)
- [Webhooks](#webhooks)
- [Error Handling](#error-handling)

---

## Authentication

### Overview

The API supports optional API key authentication. When enabled, all requests must include a valid API key in the `X-API-Key` header.

### API Key Generation

Generate a secure API key:

```python
from src.api.security import generate_api_key

api_key = generate_api_key()
print(f"Your API key: {api_key}")
```

Or using the CLI:

```bash
uv run python -c "from src.api.security import generate_api_key; print(generate_api_key())"
```

### Configuring API Keys

Set API keys via environment variable:

```bash
# Single key
export API_KEY="your-api-key-here"

# Multiple keys (comma-separated)
export API_KEYS="key1,key2,key3"
```

Or in `.env` file:

```bash
API_KEYS=key1,key2,key3
AUTH_REQUIRE_KEY=false  # Set to true to require authentication
AUTH_DEFAULT_RATE_LIMIT_TIER=free
```

### Using API Keys in Requests

Include the API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key-here" \
     http://localhost:8000/api/v1/videos/transcribe \
     -d '{"source": "https://youtube.com/watch?v=VIDEO_ID"}'
```

### Authentication Tiers

| Tier | Rate Limit | Use Case |
|------|------------|----------|
| `free` | 10 requests/minute | Development, testing |
| `pro` | 100 requests/minute | Production applications |
| `enterprise` | 1000 requests/minute | High-volume services |

---

## Endpoints

### Base URL

```
http://localhost:8000
```

### API Versioning

All endpoints are prefixed with `/api/v1`:

```
http://localhost:8000/api/v1/...
```

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Spec**: http://localhost:8000/openapi.json

---

### Videos Endpoints

#### Submit Video for Transcription

**Endpoint**: `POST /api/v1/videos/transcribe`

Submit a video for asynchronous transcription.

**Request Body**:

```json
{
  "source": "https://youtube.com/watch?v=VIDEO_ID",
  "priority": "normal",
  "save_to_db": true,
  "webhook_url": "https://your-server.com/webhook"
}
```

**Parameters**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source` | string | Yes | - | YouTube URL, video ID, or local file path |
| `priority` | string | No | `"normal"` | Job priority: `"low"`, `"normal"`, `"high"` |
| `save_to_db` | boolean | No | `true` | Save transcript to database |
| `webhook_url` | string | No | `null` | URL to notify on completion |

**Response** (202 Accepted):

```json
{
  "job_id": "job_dQw4w9WgXcQ_20240115103000",
  "status": "queued",
  "video_id": "dQw4w9WgXcQ",
  "message": "Transcription job queued with normal priority",
  "created_at": "2024-01-15T10:30:00Z",
  "estimated_completion": "2024-01-15T10:33:00Z"
}
```

#### Get Job Status

**Endpoint**: `GET /api/v1/videos/jobs/{job_id}`

Check the status of a transcription job.

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string | Job identifier from submission response |

**Response** (200 OK):

```json
{
  "job_id": "job_dQw4w9WgXcQ_20240115103000",
  "status": "completed",
  "video_id": "dQw4w9WgXcQ",
  "progress_percent": 100.0,
  "current_step": "Completed",
  "started_at": "2024-01-15T10:30:05Z",
  "completed_at": "2024-01-15T10:32:30Z",
  "error_message": null,
  "result_url": "/api/v1/transcripts/dQw4w9WgXcQ"
}
```

**Job Statuses**:

| Status | Description |
|--------|-------------|
| `queued` | Job is waiting to be processed |
| `processing` | Job is currently being processed |
| `completed` | Job completed successfully |
| `failed` | Job failed with an error |

#### List Jobs

**Endpoint**: `GET /api/v1/videos/jobs`

List all transcription jobs with optional filtering.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 100 | Maximum jobs to return (max: 1000) |
| `offset` | integer | 0 | Number of jobs to skip |
| `status_filter` | string | null | Filter by status |

**Response** (200 OK):

```json
[
  {
    "job_id": "job_abc123",
    "status": "completed",
    "video_id": "dQw4w9WgXcQ",
    "progress_percent": 100.0,
    "result_url": "/api/v1/transcripts/dQw4w9WgXcQ"
  }
]
```

---

### Transcripts Endpoints

#### Get Transcript

**Endpoint**: `GET /api/v1/transcripts/{video_id}`

Retrieve the complete transcript for a video.

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `video_id` | string | YouTube video ID (11 characters) |

**Response** (200 OK):

```json
{
  "_id": "507f1f77bcf86cd799439011",
  "video_id": "dQw4w9WgXcQ",
  "title": "Example Video",
  "channel_id": "UC1234567890",
  "channel_name": "Example Channel",
  "duration_seconds": 212.5,
  "language": "en",
  "transcript_source": "youtube_auto",
  "segments": [
    {
      "start": 0.0,
      "end": 5.0,
      "text": "Hello world"
    },
    {
      "start": 5.0,
      "end": 10.0,
      "text": "Welcome to this video"
    }
  ],
  "full_text": "Hello world. Welcome to this video.",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

#### List Transcripts

**Endpoint**: `GET /api/v1/transcripts/`

List all transcripts with pagination and filtering.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 100 | Maximum transcripts to return |
| `offset` | integer | 0 | Number of transcripts to skip |
| `transcript_source` | string | null | Filter by source |
| `language` | string | null | Filter by language code |

**Response** (200 OK):

```json
[
  {
    "_id": "507f1f77bcf86cd799439011",
    "video_id": "dQw4w9WgXcQ",
    "title": "Example Video",
    "channel_name": "Example Channel",
    "language": "en",
    "transcript_source": "youtube_auto",
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

---

### Channels Endpoints

#### List Channels

**Endpoint**: `GET /api/v1/channels/`

List all tracked YouTube channels.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 100 | Maximum channels to return |

**Response** (200 OK):

```json
[
  {
    "_id": "507f1f77bcf86cd799439011",
    "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
    "channel_handle": "MrBeast",
    "channel_title": "MrBeast",
    "channel_url": "https://www.youtube.com/@MrBeast",
    "tracked_since": "2024-01-15T10:30:00Z",
    "video_count": 750
  }
]
```

#### Get Channel

**Endpoint**: `GET /api/v1/channels/{channel_id}`

Get details for a specific channel.

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | string | YouTube channel ID |

**Response** (200 OK):

```json
{
  "_id": "507f1f77bcf86cd799439011",
  "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
  "channel_handle": "MrBeast",
  "channel_title": "MrBeast",
  "channel_url": "https://www.youtube.com/@MrBeast",
  "tracked_since": "2024-01-15T10:30:00Z",
  "video_count": 750,
  "transcript_count": 500
}
```

#### List Channel Videos

**Endpoint**: `GET /api/v1/channels/{channel_id}/videos`

List videos for a specific channel.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 100 | Maximum videos to return |
| `offset` | integer | 0 | Number of videos to skip |
| `transcript_status` | string | null | Filter by status: pending, completed, failed |

**Response** (200 OK):

```json
[
  {
    "_id": "507f1f77bcf86cd799439012",
    "video_id": "dQw4w9WgXcQ",
    "title": "Example Video",
    "duration_seconds": 212.5,
    "published_at": "2024-01-15T10:30:00Z",
    "transcript_status": "completed"
  }
]
```

#### Remove Channel

**Endpoint**: `DELETE /api/v1/channels/{channel_id}`

Remove a channel from tracking. Video metadata and transcripts are preserved.

**Response** (200 OK):

```json
{
  "success": true,
  "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
  "message": "Channel UCX6OQ3DkcsbYNE6H8uQQuVA removed from tracking"
}
```

#### Sync Channel

**Endpoint**: `POST /api/v1/channels/{channel_id}/sync`

Sync videos from a tracked channel.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | string | "recent" | Sync mode: "recent" or "all" |

**Response** (200 OK):

```json
{
  "success": true,
  "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
  "videos_fetched": 15,
  "videos_new": 5,
  "videos_existing": 10,
  "message": "Synced 15 videos (5 new)"
}
```

---

### Stats Endpoint

#### Get System Statistics

**Endpoint**: `GET /api/v1/stats/`

Get comprehensive statistics about the pipeline.

**Response** (200 OK):

```json
{
  "total_channels": 5,
  "total_videos": 1500,
  "total_transcripts": 1200,
  "videos_pending": 250,
  "videos_completed": 1200,
  "videos_failed": 50,
  "transcripts_by_source": {
    "youtube_api": 800,
    "whisper": 400
  },
  "active_jobs": 3,
  "timestamp": "2024-01-15T10:30:00Z",
  "redis_available": true
}
```

---

### Batch Transcription

#### Submit Multiple Videos

**Endpoint**: `POST /api/v1/videos/batch-transcribe`

Submit multiple videos for transcription in a single request (up to 100 videos).

**Request Body**:

```json
{
  "sources": [
    "https://youtube.com/watch?v=VIDEO_ID1",
    "https://youtube.com/watch?v=VIDEO_ID2",
    "VIDEO_ID3"
  ],
  "priority": "normal",
  "save_to_db": true
}
```

**Parameters**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `sources` | array | Yes | - | List of video sources (max 100) |
| `priority` | string | No | `"normal"` | Job priority for all videos |
| `save_to_db` | boolean | No | `true` | Save transcripts to database |

**Response** (202 Accepted):

```json
{
  "total_submitted": 3,
  "jobs": [
    {
      "source": "https://youtube.com/watch?v=VIDEO_ID1",
      "video_id": "VIDEO_ID1",
      "job_id": "job_VIDEO_ID1_20240115103000",
      "status": "queued"
    },
    {
      "source": "VIDEO_ID3",
      "video_id": "VIDEO_ID3",
      "job_id": "job_VIDEO_ID3_20240115103000",
      "status": "queued"
    }
  ],
  "message": "Submitted 3 jobs (0 failed)"
}
```

---

### Delete Transcript

**Endpoint**: `DELETE /api/v1/transcripts/{video_id}`

Delete a transcript from the database. The video metadata is preserved but marked as pending for re-transcription.

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `video_id` | string | YouTube video ID (11 characters) |

**Response** (200 OK):

```json
{
  "success": true,
  "video_id": "dQw4w9WgXcQ",
  "message": "Transcript for video dQw4w9WgXcQ deleted"
}
```

---

### Health Endpoints

#### Basic Health Check

**Endpoint**: `GET /health`

Quick health check for load balancers.

**Response** (200 OK):

```json
{
  "status": "healthy",
  "version": "0.5.0",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Readiness Probe

**Endpoint**: `GET /health/ready`

Check if service is ready to accept traffic.

**Response** (200 OK):

```json
{
  "status": "healthy",
  "version": "0.5.0",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "api": {"status": "healthy", "latency_ms": 1},
    "database": {"status": "healthy", "latency_ms": 5, "available": true},
    "redis": {"status": "healthy", "latency_ms": 2, "available": true}
  }
}
```

#### Detailed Health

**Endpoint**: `GET /health/detailed`

Comprehensive health information.

**Response** (200 OK):

```json
{
  "status": "healthy",
  "version": "0.5.0",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "api": {"status": "healthy", "latency_ms": 1},
    "database": {"status": "healthy", "latency_ms": 5, "available": true},
    "redis": {"status": "healthy", "latency_ms": 2, "available": true},
    "transcription": {"status": "healthy", "available": true}
  },
  "uptime_seconds": 3600.5,
  "environment": {
    "redis_enabled": true,
    "rate_limit_enabled": true,
    "prometheus_enabled": true
  }
}
```

---

### Metrics Endpoint

**Endpoint**: `GET /metrics`

Prometheus metrics endpoint.

**Response** (200 OK):

```
# HELP api_requests_total Total number of API requests
# TYPE api_requests_total counter
api_requests_total{method="POST",endpoint="/api/v1/videos/transcribe",status="202"} 150
api_requests_total{method="GET",endpoint="/api/v1/transcripts/{video_id}",status="200"} 523

# HELP transcription_jobs_total Total number of transcription jobs submitted
# TYPE transcription_jobs_total counter
transcription_jobs_total{status="started",source_type="youtube"} 150
```

---

## Code Examples

### cURL Examples

#### Submit Video for Transcription

```bash
curl -X POST http://localhost:8000/api/v1/videos/transcribe \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "priority": "normal",
    "save_to_db": true
  }'
```

#### Check Job Status

```bash
curl http://localhost:8000/api/v1/videos/jobs/job_dQw4w9WgXcQ_20240115103000 \
  -H "X-API-Key: your-api-key"
```

#### Get Transcript

```bash
curl http://localhost:8000/api/v1/transcripts/dQw4w9WgXcQ \
  -H "X-API-Key: your-api-key"
```

#### List Transcripts

```bash
curl "http://localhost:8000/api/v1/transcripts/?limit=10&offset=0" \
  -H "X-API-Key: your-api-key"
```

#### Health Check

```bash
curl http://localhost:8000/health
```

#### Get Metrics

```bash
curl http://localhost:8000/metrics
```

---

### Python Examples

Using the `requests` library:

```python
import requests
import time

BASE_URL = "http://localhost:8000"
API_KEY = "your-api-key"

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def transcribe_video(source: str, priority: str = "normal") -> dict:
    """Submit a video for transcription."""
    response = requests.post(
        f"{BASE_URL}/api/v1/videos/transcribe",
        headers=HEADERS,
        json={
            "source": source,
            "priority": priority,
            "save_to_db": True
        }
    )
    response.raise_for_status()
    return response.json()

def get_job_status(job_id: str) -> dict:
    """Check job status."""
    response = requests.get(
        f"{BASE_URL}/api/v1/videos/jobs/{job_id}",
        headers=HEADERS
    )
    response.raise_for_status()
    return response.json()

def get_transcript(video_id: str) -> dict:
    """Get transcript for a video."""
    response = requests.get(
        f"{BASE_URL}/api/v1/transcripts/{video_id}",
        headers=HEADERS
    )
    response.raise_for_status()
    return response.json()

def wait_for_completion(job_id: str, poll_interval: int = 5) -> dict:
    """Wait for job to complete."""
    while True:
        status = get_job_status(job_id)
        
        if status["status"] == "completed":
            return get_transcript(status["video_id"])
        elif status["status"] == "failed":
            raise Exception(f"Job failed: {status.get('error_message')}")
        
        print(f"Status: {status['status']} - {status['progress_percent']}%")
        time.sleep(poll_interval)

# Example usage
if __name__ == "__main__":
    # Submit job
    result = transcribe_video("https://youtube.com/watch?v=dQw4w9WgXcQ")
    print(f"Job submitted: {result['job_id']}")
    
    # Wait for completion
    transcript = wait_for_completion(result['job_id'])
    print(f"Transcript received: {len(transcript['segments'])} segments")
    print(f"Full text: {transcript['full_text'][:200]}...")
```

---

### JavaScript Examples

Using the Fetch API:

```javascript
const BASE_URL = 'http://localhost:8000';
const API_KEY = 'your-api-key';

const HEADERS = {
  'X-API-Key': API_KEY,
  'Content-Type': 'application/json'
};

async function transcribeVideo(source, priority = 'normal') {
  const response = await fetch(`${BASE_URL}/api/v1/videos/transcribe`, {
    method: 'POST',
    headers: HEADERS,
    body: JSON.stringify({
      source,
      priority,
      save_to_db: true
    })
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

async function getJobStatus(jobId) {
  const response = await fetch(`${BASE_URL}/api/v1/videos/jobs/${jobId}`, {
    headers: HEADERS
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

async function getTranscript(videoId) {
  const response = await fetch(`${BASE_URL}/api/v1/transcripts/${videoId}`, {
    headers: HEADERS
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

async function waitForCompletion(jobId, pollInterval = 5000) {
  while (true) {
    const status = await getJobStatus(jobId);
    
    if (status.status === 'completed') {
      return await getTranscript(status.video_id);
    } else if (status.status === 'failed') {
      throw new Error(`Job failed: ${status.error_message}`);
    }
    
    console.log(`Status: ${status.status} - ${status.progress_percent}%`);
    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }
}

// Example usage
async function main() {
  try {
    const result = await transcribeVideo('https://youtube.com/watch?v=dQw4w9WgXcQ');
    console.log(`Job submitted: ${result.job_id}`);
    
    const transcript = await waitForCompletion(result.job_id);
    console.log(`Transcript received: ${transcript.segments.length} segments`);
    console.log(`Full text: ${transcript.full_text.substring(0, 200)}...`);
  } catch (error) {
    console.error('Error:', error.message);
  }
}

main();
```

Using Axios:

```javascript
const axios = require('axios');

const BASE_URL = 'http://localhost:8000';
const API_KEY = 'your-api-key';

const client = axios.create({
  baseURL: BASE_URL,
  headers: {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json'
  }
});

async function transcribeVideo(source, priority = 'normal') {
  const response = await client.post('/api/v1/videos/transcribe', {
    source,
    priority,
    save_to_db: true
  });
  return response.data;
}

async function getJobStatus(jobId) {
  const response = await client.get(`/api/v1/videos/jobs/${jobId}`);
  return response.data;
}

async function getTranscript(videoId) {
  const response = await client.get(`/api/v1/transcripts/${videoId}`);
  return response.data;
}
```

---

### Node.js Stream Example

For handling large transcripts:

```javascript
const axios = require('axios');
const { Writable } = require('stream');

async function streamTranscript(videoId) {
  const response = await axios.get(
    `http://localhost:8000/api/v1/transcripts/${videoId}`,
    {
      headers: { 'X-API-Key': API_KEY },
      responseType: 'stream'
    }
  );
  
  return new Promise((resolve, reject) => {
    let data = '';
    
    response.data.on('data', chunk => {
      data += chunk;
    });
    
    response.data.on('end', () => {
      resolve(JSON.parse(data));
    });
    
    response.data.on('error', reject);
  });
}
```

---

## Rate Limiting

### Overview

The API implements rate limiting to ensure fair usage and prevent abuse. Rate limits are applied per API key.

### Rate Limit Tiers

| Tier | Requests/Minute | Requests/Hour | Use Case |
|------|-----------------|---------------|----------|
| Free | 10 | 500 | Development, testing |
| Pro | 100 | 5,000 | Production applications |
| Enterprise | 1,000 | 50,000 | High-volume services |

### Rate Limit Headers

Every response includes rate limit information:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 8
X-RateLimit-Reset: 1705312260
Retry-After: 60  (only on 429 responses)
```

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests allowed in the window |
| `X-RateLimit-Remaining` | Requests remaining in current window |
| `X-RateLimit-Reset` | Unix timestamp when the limit resets |
| `Retry-After` | Seconds to wait before retrying (on 429) |

### Handling 429 Responses

When rate limited, the API returns a 429 status code:

```json
{
  "error": "RATE_LIMIT_EXCEEDED",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "message": "Too many requests. Please slow down.",
  "details": {
    "retry_after_seconds": 60
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Rate Limit Handling Example

```python
import requests
import time
from datetime import datetime

def make_request_with_retry(url, max_retries=3):
    """Make request with rate limit handling."""
    for attempt in range(max_retries):
        response = requests.get(url)
        
        if response.status_code == 429:
            # Get retry-after header
            retry_after = int(response.headers.get('Retry-After', 60))
            
            print(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            continue
        
        response.raise_for_status()
        return response.json()
    
    raise Exception("Max retries exceeded")

# Usage
result = make_request_with_retry(
    "http://localhost:8000/api/v1/transcripts/dQw4w9WgXcQ"
)
```

### Best Practices

1. **Monitor rate limit headers** and adjust request frequency
2. **Implement exponential backoff** for retries
3. **Cache responses** when possible
4. **Use webhooks** instead of polling for job status
5. **Batch requests** when processing multiple items

---

## Webhooks

### Overview

Webhooks allow you to receive notifications when transcription jobs complete, eliminating the need for polling.

### Configuring Webhooks

Include `webhook_url` when submitting a transcription job:

```json
{
  "source": "https://youtube.com/watch?v=VIDEO_ID",
  "webhook_url": "https://your-server.com/webhook"
}
```

### Webhook Payload

#### Success Notification

```json
{
  "job_id": "job_dQw4w9WgXcQ_20240115103000",
  "status": "completed",
  "video_id": "dQw4w9WgXcQ",
  "timestamp": "2024-01-15T10:32:30Z"
}
```

#### Failure Notification

```json
{
  "job_id": "job_dQw4w9WgXcQ_20240115103000",
  "status": "failed",
  "error": "Transcription failed: Video unavailable",
  "timestamp": "2024-01-15T10:32:30Z"
}
```

### Webhook Security

#### Verify Webhook Source

Add a secret token to your webhook URL:

```
https://your-server.com/webhook?secret=your-secret-token
```

Validate the token in your webhook handler:

```python
from flask import Flask, request, abort

app = Flask(__name__)
WEBHOOK_SECRET = "your-secret-token"

@app.route('/webhook', methods=['POST'])
def webhook():
    # Verify secret
    if request.args.get('secret') != WEBHOOK_SECRET:
        abort(403)
    
    data = request.json
    print(f"Received webhook: {data}")
    
    # Process webhook
    if data['status'] == 'completed':
        # Fetch transcript
        transcript = get_transcript(data['video_id'])
        # Process transcript...
    
    return {'status': 'received'}
```

### Webhook Handler Examples

#### Python (Flask)

```python
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

API_BASE = "http://localhost:8000"
API_KEY = "your-api-key"

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    
    if data['status'] == 'completed':
        # Fetch transcript
        response = requests.get(
            f"{API_BASE}/api/v1/transcripts/{data['video_id']}",
            headers={'X-API-Key': API_KEY}
        )
        transcript = response.json()
        
        # Process transcript
        print(f"Transcript: {transcript['full_text'][:100]}...")
    
    elif data['status'] == 'failed':
        print(f"Job failed: {data.get('error')}")
    
    return jsonify({'status': 'received'})

if __name__ == '__main__':
    app.run(port=5000)
```

#### Node.js (Express)

```javascript
const express = require('express');
const axios = require('axios');

const app = express();
app.use(express.json());

const API_BASE = 'http://localhost:8000';
const API_KEY = 'your-api-key';

app.post('/webhook', async (req, res) => {
  const { job_id, status, video_id, error } = req.body;
  
  if (status === 'completed') {
    // Fetch transcript
    const response = await axios.get(
      `${API_BASE}/api/v1/transcripts/${video_id}`,
      { headers: { 'X-API-Key': API_KEY } }
    );
    const transcript = response.data;
    
    console.log(`Transcript: ${transcript.full_text.substring(0, 100)}...`);
  } else if (status === 'failed') {
    console.log(`Job failed: ${error}`);
  }
  
  res.json({ status: 'received' });
});

app.listen(5000, () => {
  console.log('Webhook server listening on port 5000');
});
```

### Testing Webhooks

Use a service like [webhook.site](https://webhook.site) or [ngrok](https://ngrok.com) for testing:

```bash
# Using ngrok to expose local server
ngrok http 5000

# Use the generated URL as webhook_url
```

---

## Error Handling

### Error Response Format

All errors follow a consistent format:

```json
{
  "error": "ERROR_CODE",
  "error_code": "ERROR_CODE",
  "message": "Human-readable error message",
  "request_id": "req_abc123",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Common Error Codes

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `INVALID_VIDEO_ID` | 400 | Invalid YouTube video ID |
| `TRANSCRIPT_NOT_FOUND` | 404 | Transcript not found |
| `JOB_NOT_FOUND` | 404 | Job not found |
| `INVALID_API_KEY` | 401 | Invalid or missing API key |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Internal server error |
| `TRANSCRIPTION_ERROR` | 500 | Transcription failed |

### Error Handling Examples

#### Python

```python
import requests
from requests.exceptions import HTTPError

def safe_transcribe(source):
    try:
        response = requests.post(
            "http://localhost:8000/api/v1/videos/transcribe",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json={"source": source}
        )
        response.raise_for_status()
        return response.json()
    
    except HTTPError as e:
        error_data = e.response.json()
        
        if e.response.status_code == 401:
            print("Invalid API key")
        elif e.response.status_code == 404:
            print("Resource not found")
        elif e.response.status_code == 429:
            retry_after = e.response.headers.get('Retry-After', 60)
            print(f"Rate limited. Retry after {retry_after} seconds")
        elif e.response.status_code >= 500:
            print(f"Server error: {error_data.get('message')}")
        else:
            print(f"Error: {error_data.get('message')}")
        
        raise
```

#### JavaScript

```javascript
async function safeTranscribe(source) {
  try {
    const response = await fetch(
      'http://localhost:8000/api/v1/videos/transcribe',
      {
        method: 'POST',
        headers: {
          'X-API-Key': API_KEY,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ source })
      }
    );
    
    if (!response.ok) {
      const error = await response.json();
      
      switch (response.status) {
        case 401:
          throw new Error('Invalid API key');
        case 404:
          throw new Error('Resource not found');
        case 429:
          const retryAfter = response.headers.get('Retry-After') || 60;
          throw new Error(`Rate limited. Retry after ${retryAfter}s`);
        case 500:
          throw new Error(`Server error: ${error.message}`);
        default:
          throw new Error(error.message);
      }
    }
    
    return await response.json();
  } catch (error) {
    console.error('Transcription failed:', error.message);
    throw error;
  }
}
```

### Retry Strategy

Implement exponential backoff for transient errors:

```python
import time
import random

def retry_with_backoff(func, max_retries=5, base_delay=1):
    """Retry function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            
            # Calculate delay with jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            print(f"Attempt {attempt + 1} failed. Retrying in {delay:.1f}s...")
            time.sleep(delay)

# Usage
result = retry_with_backoff(
    lambda: requests.post(
        "http://localhost:8000/api/v1/videos/transcribe",
        json={"source": url}
    ).json()
)
```

---

## Support

For additional help:

- **API Documentation**: http://localhost:8000/docs
- **OpenAPI Spec**: http://localhost:8000/openapi.json
- **GitHub Issues**: [Report bugs and request features](https://github.com/youtube-content-pipeline/issues)
