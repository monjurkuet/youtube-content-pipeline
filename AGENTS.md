## Must Follow Rules

- No CI/CD required.
- Always use `uv` for Python package management.
- Clean slate, production-ready architecture only. Don't need to maintain compatibility, don't need gradual migration.
- You are allowed to read, modify and write .env files.
- CORS allows all origins.

## OpenVINO Whisper

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENVINO_WHISPER_MODEL` | HuggingFace model ID | `openai/whisper-base` |
| `OPENVINO_DEVICE` | Device to use (AUTO, GPU, CPU) | `AUTO` |
| `OPENVINO_CACHE_DIR` | Model cache directory | `~/.cache/whisper_openvino` |

---

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
│   │   └── health.py          # Health checks
│   └── models/
│       ├── requests.py        # Request models
│       └── errors.py          # Error models
├── core/
│   ├── config.py              # Configuration settings
│   ├── constants.py           # Application constants
│   ├── exceptions.py          # Custom exceptions
│   ├── schemas.py             # Pydantic models
│   └── logging_config.py      # Logging configuration
├── pipeline/
│   └── transcript.py          # Main pipeline
├── transcription/
│   ├── handler.py             # Transcription with fallback
│   └── whisper_openvino.py    # OpenVINO Whisper
├── video/
│   └── cookie_manager.py      # Browser cookie management
├── database/
│   ├── manager.py             # Database manager
│   ├── models.py              # Database models
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

---

## Development Guidelines

### Code Style

1. **Type Hints**: Use type hints for all function signatures
2. **Docstrings**: Write Google-style docstrings for all public functions
3. **Error Handling**: Use custom exceptions from `src.core.exceptions`
4. **Logging**: Use structured logging with `logging.getLogger(__name__)`
5. **Async/Await**: Use async for I/O operations

### Testing Requirements

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/test_api.py -v

# Run specific test
uv run pytest tests/test_api.py::test_transcribe_video -v
```

**Test Guidelines**:
- Write tests for all new features
- Maintain >80% code coverage
- Use fixtures for common setup
- Mock external services (YouTube, MongoDB, Redis)

### Database Migrations

The application uses MongoDB with automatic index creation:

```python
# Indexes are created on startup
await db_manager.init_indexes()
```

**Index Guidelines**:
- Create indexes for frequently queried fields
- Use compound indexes for multi-field queries
- Document index choices in code comments

### API Development

**Endpoint Structure**:
```python
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/resource", tags=["resource"])

@router.get("/{id}", response_model=ResourceResponse)
async def get_resource(
    id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> ResourceResponse:
    """Get resource by ID.
    
    Args:
        id: Resource identifier
        db: Database dependency
        auth_ctx: Authentication context
    
    Returns:
        ResourceResponse with resource data
    
    Raises:
        HTTPException: If resource not found
    """
    doc = await db.resources.find_one({"_id": id})
    if not doc:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    return ResourceResponse(**doc)
```

**Error Handling**:
```python
from src.api.models.errors import ErrorCodes

raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={
        "error": ErrorCodes.NOT_FOUND,
        "error_code": ErrorCodes.RESOURCE_NOT_FOUND,
        "message": "Resource not found",
    }
)
```

### Configuration

**Priority**: Environment Variables > YAML Config > Defaults

```python
from src.core.config import get_settings

settings = get_settings()

# Access settings
mongodb_url = settings.mongodb_url
redis_enabled = settings.redis_enabled
```

### Metrics

**Recording Metrics**:
```python
from src.api.middleware.prometheus import (
    record_transcription_job_start,
    record_transcription_job_complete,
    record_mongodb_operation,
)

# Record job start
record_transcription_job_start(source_type="youtube")

# Record job completion
record_transcription_job_complete(
    source_type="youtube",
    duration_seconds=duration,
    status="success",
)

# Record database operation
record_mongodb_operation(
    operation="find",
    collection="transcripts",
    duration_seconds=duration,
    status="success",
)
```

---

## Architecture Decisions

### Why FastAPI?

- **Performance**: Async support, high performance
- **Type Safety**: Pydantic models for validation
- **Documentation**: Auto-generated OpenAPI docs
- **Ecosystem**: Rich middleware ecosystem

### Why MongoDB?

- **Flexibility**: Schema-less design for transcripts
- **Scalability**: Horizontal scaling with sharding
- **Performance**: Fast reads for transcript retrieval
- **JSON Native**: Natural fit for transcript data

### Why Redis?

- **Caching**: Fast job status lookups
- **Rate Limiting**: Distributed rate limiting
- **Queue**: Job queue management
- **Optional**: Graceful degradation to memory

### Why MCP?

- **AI Integration**: Standard protocol for AI assistants
- **Tools**: Structured tool interface
- **Resources**: Direct data access
- **Prompts**: Reusable workflows

---

## Common Tasks

### Adding a New Endpoint

1. Create router in `src/api/routers/`
2. Define request/response models in `src/api/models/`
3. Add authentication if needed
4. Add rate limiting if needed
5. Add metrics recording
6. Update OpenAPI documentation
7. Write tests

### Adding a New Metric

1. Define metric in `src/api/middleware/prometheus.py`
2. Record metric at appropriate points
3. Update Prometheus configuration
4. Create Grafana dashboard panel

### Adding a New MCP Tool

1. Create tool function in `src/mcp/tools/`
2. Register tool in `src/mcp/server.py`
3. Add tool description and parameters
4. Write tests
5. Update MCP documentation

### Adding Configuration Option

1. Add to `Settings` class in `src/core/config.py`
2. Add default value
3. Add to `.env.example`
4. Add to `CONFIGURATION_REFERENCE.md`
5. Update YAML config if applicable

---

## Troubleshooting

### LSP Errors

LSP errors in IDE are expected for some files due to:
- Dynamic imports
- Type inference limitations
- External library stubs

These do not affect runtime behavior. Focus on:
- Runtime errors
- Test failures
- Type checker errors (mypy)

### Database Connection Issues

```bash
# Check MongoDB is running
mongosh --eval "db.adminCommand('ping')"

# Check connection string
echo $MONGODB_URL

# Test from Python
uv run python -c "from src.database import get_db_manager; import asyncio; asyncio.run(get_db_manager().client.admin.command('ping'))"
```

### Redis Connection Issues

```bash
# Check Redis is running
redis-cli ping

# Check connection string
echo $REDIS_URL

# Test from Python
uv run python -c "from src.database.redis import get_redis_manager; print(get_redis_manager().is_available)"
```

### MCP Server Issues

```bash
# Test server manually
uv run python -m src.mcp.server --log-level debug

# Test with inspector
npx @modelcontextprotocol/inspector uv run python -m src.mcp.server
```

---

## Performance Optimization

### Database Queries

- Use indexes for frequently queried fields
- Use projection to fetch only needed fields
- Use batch operations for bulk writes
- Avoid N+1 queries

### Caching

- Cache frequently accessed transcripts
- Use Redis for distributed caching
- Set appropriate TTL values
- Invalidate cache on updates

### Rate Limiting

- Use Redis for distributed rate limiting
- Set appropriate limits per tier
- Implement exponential backoff
- Monitor rate limit hits

### Transcription

- Use YouTube API when available (faster)
- Cache Whisper models
- Use GPU for Whisper transcription
- Process videos in batches

---

## Security

### API Keys

- Generate secure keys: `secrets.token_urlsafe(32)`
- Hash keys for storage: SHA-256
- Rotate keys periodically
- Never log API keys

### Rate Limiting

- Enable rate limiting in production
- Use Redis for distributed limiting
- Set appropriate limits per tier
- Monitor and adjust limits

### Input Validation

- Validate all user input
- Use Pydantic models for validation
- Sanitize file paths
- Limit request sizes

### Database Security

- Use authentication for MongoDB
- Use TLS for connections
- Limit database permissions
- Regular backups

---

## Monitoring

### Metrics to Watch

- API request rate and latency
- Transcription job duration
- Error rates (4xx, 5xx)
- Database operation latency
- Redis operation latency
- Queue depth

### Alerts to Configure

- High error rate (>5%)
- Slow transcription jobs (>5 min)
- Database connection lost
- Redis connection lost
- High memory usage
- High CPU usage

### Dashboards

- API performance dashboard
- Transcription jobs dashboard
- Database health dashboard
- System resources dashboard

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.5.0 | 2024-01 | Phase 4: Documentation and Prometheus |
| 0.4.0 | 2024-01 | Phase 3: MCP Integration |
| 0.3.0 | 2024-01 | Phase 2: Redis and Rate Limiting |
| 0.2.0 | 2024-01 | Phase 1: API Restructuring |
| 0.1.0 | 2024-01 | Initial release |

---

## Resources

- **FastAPI**: https://fastapi.tiangolo.com
- **Pydantic**: https://docs.pydantic.dev
- **MongoDB**: https://www.mongodb.com/docs
- **Redis**: https://redis.io/docs
- **Prometheus**: https://prometheus.io/docs
- **Grafana**: https://grafana.com/docs
- **MCP**: https://modelcontextprotocol.io
