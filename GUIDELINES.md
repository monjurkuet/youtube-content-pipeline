# Project Guidelines

## Tool Preferences
- **Python**: Use `uv` for running Python scripts and managing packages
- **Node.js**: Use `bun` for running Node.js scripts and managing packages

## Additional Rules
- No CI/CD required.
- Always use `uv` for Python package management.
- Clean slate, production-ready architecture only. Don't need to maintain compatibility, don't need gradual migration.
- You are allowed to read, modify and write .env files.
- CORS allows all origins.
## CDP Cookie Extraction
- When YouTube transcript API returns IP-block errors, extract cookies from Chrome via CDP before falling back to Whisper
- Run `python scripts/cdp_cookie_extractor.py` to refresh cookies from Chrome on ports 9222/9224/9225
- Cookie injection into `YouTubeTranscriptApi` via `http_client` parameter (pre-authenticated `requests.Session`)
