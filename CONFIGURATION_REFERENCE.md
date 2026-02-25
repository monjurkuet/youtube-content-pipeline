# Configuration Reference

Complete reference for all configuration options in the YouTube Transcription Pipeline.

## Table of Contents

- [Environment Variables](#environment-variables)
- [YAML Configuration](#yaml-configuration)
- [Redis Configuration](#redis-configuration)
- [MongoDB Configuration](#mongodb-configuration)
- [Rate Limiting Configuration](#rate-limiting-configuration)
- [Authentication Configuration](#authentication-configuration)
- [Prometheus Configuration](#prometheus-configuration)

---

## Environment Variables

Environment variables take precedence over YAML configuration.

### Database Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MONGODB_URL` | MongoDB connection string | `mongodb://localhost:27017` | No |
| `MONGODB_DATABASE` | Database name | `video_pipeline` | No |

### Redis Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` | No |
| `REDIS_DB` | Redis database number | `0` | No |
| `REDIS_KEY_PREFIX` | Key prefix for Redis keys | `transcription` | No |
| `REDIS_ENABLED` | Enable Redis features | `true` | No |

### Authentication Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `API_KEY` | Single API key | - | No |
| `API_KEYS` | Comma-separated API keys | - | No |
| `AUTH_REQUIRE_KEY` | Require API key for all requests | `false` | No |
| `AUTH_DEFAULT_RATE_LIMIT_TIER` | Default rate limit tier | `free` | No |

### Rate Limiting Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` | No |
| `RATE_LIMIT_STORAGE` | Storage backend (`redis` or `memory`) | `redis` | No |
| `RATE_LIMIT_DEFAULT_TIER` | Default tier for requests | `free` | No |

### Prometheus Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `PROMETHEUS_ENABLED` | Enable Prometheus metrics | `true` | No |
| `PROMETHEUS_PATH` | Metrics endpoint path | `/metrics` | No |

### OpenVINO Whisper Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `OPENVINO_WHISPER_MODEL` | HuggingFace model ID | `openai/whisper-base` | No |
| `OPENVINO_DEVICE` | Device (`AUTO`, `GPU`, `CPU`) | `AUTO` | No |
| `OPENVINO_CACHE_DIR` | Model cache directory | `~/.cache/whisper_openvino` | No |

### Audio Processing Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AUDIO_FORMAT` | Audio format for processing | `mp3` | No |
| `AUDIO_BITRATE` | Audio bitrate | `128k` | No |
| `WHISPER_CHUNK_LENGTH` | Chunk length in seconds | `30` | No |

### Pipeline Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `PIPELINE_WORK_DIR` | Working directory for temp files | `/tmp/transcription_pipeline` | No |
| `PIPELINE_CACHE_DIR` | Cache directory | `/tmp/transcription_cache` | No |
| `PIPELINE_ENABLE_CACHE` | Enable caching | `true` | No |
| `PIPELINE_SAVE_TO_DB` | Save to database | `true` | No |

### YouTube API Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `YOUTUBE_API_USE_COOKIES` | Use browser cookies | `true` | No |
| `YOUTUBE_API_COOKIE_CACHE_HOURS` | Cookie cache duration | `24` | No |
| `YOUTUBE_API_TIMEOUT` | Request timeout (seconds) | `30` | No |
| `YOUTUBE_API_LANGUAGES` | Preferred languages | `["en", "en-US", "en-GB"]` | No |

### Batch Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BATCH_DEFAULT_SIZE` | Default batch size | `5` | No |
| `BATCH_SHOW_PROGRESS` | Show progress bar | `true` | No |

---

## YAML Configuration

Create a `config.yaml` file in the project root for runtime settings.

### Complete Example

```yaml
# YouTube Transcription Pipeline Configuration
# Environment variables take precedence over these settings

# Rate Limiting - Prevents IP blocking
rate_limiting:
  enabled: true
  min_delay: 2.0        # Random delay between min and max
  max_delay: 5.0
  retry_delay: 10.0     # Base delay for exponential backoff
  max_retries: 3

# YouTube API Settings
youtube_api:
  use_cookies: true     # Use browser cookies
  cookie_cache_hours: 24
  timeout: 30
  languages:
    - en
    - en-US
    - en-GB

# Batch Processing
batch:
  default_size: 5       # Videos per batch
  show_progress: true

# Whisper Settings
whisper:
  audio_format: mp3
  audio_bitrate: 128k
  chunk_length: 30

# Pipeline Settings
pipeline:
  work_dir: /tmp/transcription_pipeline
  cache_dir: /tmp/transcription_cache
  enable_cache: true
  save_to_db: true
```

### Configuration Sections

#### rate_limiting

Controls rate limiting for YouTube API requests.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable rate limiting |
| `min_delay` | float | `2.0` | Minimum delay between requests (seconds) |
| `max_delay` | float | `5.0` | Maximum delay between requests (seconds) |
| `retry_delay` | float | `10.0` | Base delay for retries |
| `max_retries` | integer | `3` | Maximum retry attempts |

#### youtube_api

YouTube API configuration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `use_cookies` | boolean | `true` | Use browser cookies for requests |
| `cookie_cache_hours` | integer | `24` | Cookie cache duration |
| `timeout` | integer | `30` | Request timeout (seconds) |
| `languages` | array | `["en", "en-US", "en-GB"]` | Preferred languages |

#### batch

Batch processing configuration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_size` | integer | `5` | Default videos per batch |
| `show_progress` | boolean | `true` | Show progress bar |

#### whisper

Whisper transcription settings.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `audio_format` | string | `mp3` | Audio format |
| `audio_bitrate` | string | `128k` | Audio bitrate |
| `chunk_length` | integer | `30` | Chunk length (seconds) |

#### pipeline

Pipeline settings.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `work_dir` | string | `/tmp/transcription_pipeline` | Working directory |
| `cache_dir` | string | `/tmp/transcription_cache` | Cache directory |
| `enable_cache` | boolean | `true` | Enable caching |
| `save_to_db` | boolean | `true` | Save to database |

---

## Redis Configuration

### Connection String Format

```
redis://[username:password@]host[:port][/database_number]
```

### Examples

**Basic (no authentication)**:
```bash
REDIS_URL=redis://localhost:6379
```

**With password**:
```bash
REDIS_URL=redis://:password@localhost:6379
```

**With username and password**:
```bash
REDIS_URL=redis://username:password@localhost:6379
```

**Remote server**:
```bash
REDIS_URL=redis://redis.example.com:6379
```

### TLS Configuration

```bash
REDIS_URL=rediss://localhost:6380
```

Note: Use `rediss://` scheme for TLS connections.

### Cluster Configuration

For Redis Cluster, use comma-separated addresses:

```bash
REDIS_URL=redis://node1:6379,redis://node2:6379,redis://node3:6379
```

### Additional Options

| Option | Environment Variable | Default |
|--------|---------------------|---------|
| Database | `REDIS_DB` | `0` |
| Key Prefix | `REDIS_KEY_PREFIX` | `transcription` |
| Enabled | `REDIS_ENABLED` | `true` |

---

## MongoDB Configuration

### Connection String Format

```
mongodb://[username:password@]host1[:port1][,host2[:port2],...]/database?options
```

### Examples

**Basic (local)**:
```bash
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=video_pipeline
```

**With authentication**:
```bash
MONGODB_URL=mongodb://username:password@localhost:27017
MONGODB_DATABASE=video_pipeline
```

**Replica Set**:
```bash
MONGODB_URL=mongodb://node1:27017,node2:27017,node3:27017/video_pipeline?replicaSet=rs0
```

**Atlas (MongoDB Cloud)**:
```bash
MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/video_pipeline?retryWrites=true&w=majority
```

### Connection Options

Add options to the connection string:

| Option | Description | Example |
|--------|-------------|---------|
| `replicaSet` | Replica set name | `?replicaSet=rs0` |
| `ssl` | Enable SSL | `?ssl=true` |
| `retryWrites` | Enable retry writes | `?retryWrites=true` |
| `w` | Write concern | `?w=majority` |
| `timeoutMS` | Connection timeout | `?timeoutMS=5000` |
| `maxPoolSize` | Connection pool size | `?maxPoolSize=100` |

### TLS Configuration

```bash
# With TLS
MONGODB_URL=mongodb://localhost:27017/video_pipeline?tls=true

# With CA file
MONGODB_URL=mongodb://localhost:27017/video_pipeline?tls=true&tlsCAFile=/path/to/ca.pem

# With client certificate
MONGODB_URL=mongodb://localhost:27017/video_pipeline?tls=true&tlsCAFile=/path/to/ca.pem&tlsCertificateKeyFile=/path/to/cert.pem
```

---

## Rate Limiting Configuration

### Tier Configuration

Rate limits are configured per tier:

| Tier | Requests/Minute | Requests/Hour |
|------|-----------------|---------------|
| `free` | 10 | 500 |
| `pro` | 100 | 5,000 |
| `enterprise` | 1,000 | 50,000 |

### Custom Rate Limits

Configure custom rate limits in code:

```python
# In src/core/config.py
rate_limit_tiers: dict[str, int] = {
    "free": 10,
    "pro": 100,
    "enterprise": 1000,
    "custom": 500,  # Custom tier
}
```

### Storage Backends

**Redis (recommended for production)**:
```bash
RATE_LIMIT_STORAGE=redis
RATE_LIMIT_ENABLED=true
```

**In-memory (development only)**:
```bash
RATE_LIMIT_STORAGE=memory
RATE_LIMIT_ENABLED=true
```

---

## Authentication Configuration

### API Key Setup

**Single key**:
```bash
API_KEY=your-secret-key
```

**Multiple keys**:
```bash
API_KEYS=key1,key2,key3
```

### Require Authentication

Make API key required for all requests:
```bash
AUTH_REQUIRE_KEY=true
```

### Default Rate Limit Tier

Set default tier for unauthenticated requests:
```bash
AUTH_DEFAULT_RATE_LIMIT_TIER=free
```

### Generating API Keys

```bash
# Using Python
uv run python -c "from src.api.security import generate_api_key; print(generate_api_key())"

# Example output: xK9mN2pL5qR8sT1vW4yZ7aB0cD3eF6gH
```

---

## Prometheus Configuration

### Enable/Disable

```bash
PROMETHEUS_ENABLED=true
```

### Custom Metrics Path

```bash
PROMETHEUS_PATH=/metrics
```

### Multiprocess Mode

For multi-process deployments:

```bash
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_metrics
```

---

## Configuration Priority

Configuration is loaded in the following order (highest priority first):

1. **Environment Variables** - Always take precedence
2. **YAML Configuration** - `config.yaml` in project root
3. **Default Values** - Hardcoded defaults

### Example

```bash
# Environment (highest priority)
export MONGODB_URL=mongodb://production:27017

# config.yaml (medium priority)
# mongodb_url: mongodb://localhost:27017

# Default (lowest priority)
# mongodb://localhost:27017

# Result: Uses production MongoDB
```

---

## Validation

### Validate Configuration

```bash
# Test configuration loading
uv run python -c "from src.core.config import get_settings; print(get_settings())"

# Test YAML configuration
uv run python -c "from src.core.config import load_yaml_config; print(load_yaml_config())"
```

### Check Environment

```bash
# Show all relevant environment variables
env | grep -E "MONGODB|REDIS|API_KEY|RATE_LIMIT|PROMETHEUS"
```

---

## Troubleshooting

### Configuration Not Loading

**Symptom**: Default values are used instead of configured values

**Solutions**:

1. **Check file location**:
   ```bash
   ls -la config.yaml
   ```

2. **Validate YAML syntax**:
   ```bash
   python -c "import yaml; yaml.safe_load(open('config.yaml'))"
   ```

3. **Check environment variable precedence**:
   ```bash
   env | grep MONGODB_URL
   ```

### Database Connection Failed

**Symptom**: Cannot connect to MongoDB

**Solutions**:

1. **Verify connection string**:
   ```bash
   echo $MONGODB_URL
   ```

2. **Test connection**:
   ```bash
   mongosh "$MONGODB_URL" --eval "db.adminCommand('ping')"
   ```

3. **Check MongoDB is running**:
   ```bash
   systemctl status mongod
   ```

### Redis Connection Failed

**Symptom**: Cannot connect to Redis

**Solutions**:

1. **Verify connection string**:
   ```bash
   echo $REDIS_URL
   ```

2. **Test connection**:
   ```bash
   redis-cli -u "$REDIS_URL" ping
   ```

3. **Check Redis is running**:
   ```bash
   systemctl status redis
   ```

---

## Quick Reference

### Minimal .env File

```bash
# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=video_pipeline

# Redis (optional)
REDIS_URL=redis://localhost:6379
REDIS_ENABLED=true

# API Key (optional)
API_KEY=your-secret-key

# OpenVINO Whisper
OPENVINO_WHISPER_MODEL=openai/whisper-base
OPENVINO_DEVICE=AUTO
```

### Minimal config.yaml

```yaml
rate_limiting:
  enabled: true
  min_delay: 2.0
  max_delay: 5.0

youtube_api:
  use_cookies: true
  languages:
    - en
    - en-US

batch:
  default_size: 5
  show_progress: true
```

### Production .env File

```bash
# MongoDB (production)
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/video_pipeline?retryWrites=true&w=majority
MONGODB_DATABASE=video_pipeline

# Redis (production)
REDIS_URL=redis://redis.example.com:6379
REDIS_ENABLED=true

# Authentication
API_KEYS=key1,key2,key3
AUTH_REQUIRE_KEY=true
AUTH_DEFAULT_RATE_LIMIT_TIER=pro

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_STORAGE=redis

# Prometheus
PROMETHEUS_ENABLED=true
PROMETHEUS_PATH=/metrics

# OpenVINO Whisper (GPU)
OPENVINO_WHISPER_MODEL=openai/whisper-medium
OPENVINO_DEVICE=GPU
OPENVINO_CACHE_DIR=/var/cache/whisper_openvino
```

---

## Support

For additional help:

- **Documentation**: See other guides in this repository
- **GitHub Issues**: Report configuration issues
- **Environment Examples**: Check `.env.example` file
