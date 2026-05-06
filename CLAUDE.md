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
- YouTube IP blocks are bypassed by extracting auth cookies from Chrome via CDP (DevTools Protocol)
- `scripts/cdp_cookie_extractor.py` — standalone CLI, run before transcription batches
- `CookieManager._extract_cookies_cdp()` — CDP first, `browser_cookie3` fallback
- `YouTubeAPIProvider._create_authenticated_api()` — injects cookies via `requests.Session` into `YouTubeTranscriptApi(http_client=session)`
- Chrome must be running with `--remote-debugging-port` (9222/9224/9225)
- Cookies cached ~24h; auto-refresh via `ensure_cookies()`
