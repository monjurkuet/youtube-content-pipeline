## Project Constraints & Guidelines

### Development Rules
- **No CI/CD required.**
- **Always use uv for python.** (uv run, uv pip)
- **Clean slate, production-ready architecture only.** Don't maintain backward compatibility, don't need gradual migration.
- **Use bun for Node.js tasks** when applicable.

### Optimization Guidelines
- **Video download caching** is implemented and beneficial
- **Whisper model caching** is implemented and beneficial
- **Transcript caching** - NOT implemented (adds unnecessary complexity without significant benefit)
  - **NOTE:** Transcript *persistence* to MongoDB IS implemented (data storage, not caching)
- **Cookie caching (24h)** is implemented for YouTube authentication
- **Focus on eliminating redundant operations** rather than adding complex caching layers

### Architecture Principles
- **3-Agent Pipeline**: All videos go through Agent 1 (Transcript) → Agent 2 (Frames) → Agent 3 (Synthesis)
- **Hybrid Schema Validation**: Programmatic fixes first, LLM repair as fallback
- **Auto Cookie Management**: Extract from Chrome automatically, cache for 24 hours
- **Error Recovery**: All validation failures should attempt repair before giving up
- **No Data Loss**: Failed chunks should preserve partial data, not return empty results

### Code Quality
- Use type hints where practical
- Handle errors gracefully with fallback mechanisms
- Log all repairs and normalizations for debugging
- Keep console output informative but not overwhelming
- Use Rich library for beautiful terminal output

