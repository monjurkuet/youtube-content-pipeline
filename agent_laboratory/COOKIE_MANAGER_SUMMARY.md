# Auto Cookie Extraction Implementation Summary

## Overview
Implemented automatic YouTube cookie extraction from Chrome with daily cache refresh. The system now automatically extracts and caches cookies when needed.

## How It Works

```
Video Download Request
    ↓
Check Cookie Cache
    ↓
Cookies exist & fresh (<24h)? 
    ↓ YES → Use cached cookies ✓
    ↓ NO
Auto-extract from Chrome
    ↓
Save to ~/.config/yt-dlp/cookies.txt
Save metadata to ~/.cookie_metadata.json
    ↓
Use for download ✓
```

## Components

### 1. New Module: `src/video/cookie_manager.py`

**YouTubeCookieManager Class:**
- `ensure_cookies()` - Main entry point, ensures cookies are available
- `_has_valid_cookies()` - Checks if cookies exist and aren't expired
- `_extract_cookies()` - Extracts from Chrome using browser-cookie3
- `_get_cookie_age()` - Returns age of cookie file
- `get_cookie_args()` - Returns yt-dlp command arguments
- `invalidate_cache()` - Forces re-extraction
- `get_status()` - Returns status for debugging

**Features:**
- ✅ Auto-extracts if cookies missing/expired
- ✅ 24-hour cache duration (configurable)
- ✅ Tracks cookie metadata
- ✅ Validates auth cookies (LOGIN_INFO, SSID, etc.)
- ✅ Graceful fallback if extraction fails
- ✅ Console output for transparency

### 2. Updated: `src/video/handler.py`

**Changes:**
- Integrated `YouTubeCookieManager`
- Auto-extract enabled by default
- Constructor accepts `auto_extract_cookies` and `cookie_cache_hours` parameters
- Uses cookie manager before falling back to browser extraction

**Constructor:**
```python
VideoHandler(
    work_dir=None,
    use_browser_cookies=True,
    auto_extract_cookies=True,  # NEW
    cookie_cache_hours=24,       # NEW
)
```

## Usage

### Automatic (Default Behavior)
Just use the pipeline normally - cookies are handled automatically:
```python
from src.video.handler import VideoHandler

handler = VideoHandler()
video_path = handler.download_video("KgSEzvGOBio", "youtube")
# Cookies extracted automatically if needed
```

### Manual Cookie Management

**Check cookie status:**
```bash
uv run python -m src.video.cookie_manager --status
```

**Force re-extraction:**
```bash
uv run python -m src.video.cookie_manager --invalidate
# Then run your download again
```

**Programmatic:**
```python
from src.video.cookie_manager import get_cookie_manager

manager = get_cookie_manager()
manager.ensure_cookies()  # Extract if needed
manager.invalidate_cache()  # Force re-extract
status = manager.get_status()  # Check status
```

## Test Results

**Before:**
- Had to manually run `extract_cookies.py` first
- No cache expiration logic
- Silent failures

**After:**
```
Calling ensure_cookies...
   Using cached cookies (1.2h old)
Result: True
```

✅ **7/7 E2E tests pass with auto-extraction!**

## Cookie Flow

**First Download:**
```
Cookies missing or expired, auto-extracting from Chrome...
   ✓ Successfully extracted and cached cookies
Downloading video from YouTube...
Downloaded: 71.1 MB
```

**Subsequent Downloads (within 24h):**
```
   Using cached cookies (1.2h old)
   Cookies: 12 YouTube, 25 Google
Downloading video from YouTube...
Downloaded: 71.1 MB
```

**After 24 hours:**
```
Cookies missing or expired, auto-extracting from Chrome...
   ✓ Successfully extracted and cached cookies
```

## Configuration

**Default Settings:**
- Cache duration: 24 hours
- Auto-extract: Enabled
- Browser: Chrome only (no Firefox)
- Storage: `~/.config/yt-dlp/cookies.txt`

**Customize:**
```python
# Shorter cache (12 hours)
handler = VideoHandler(cookie_cache_hours=12)

# Disable auto-extract
handler = VideoHandler(auto_extract_cookies=False)

# Custom cookie file
from src.video.cookie_manager import YouTubeCookieManager
manager = YouTubeCookieManager(
    cookie_file="/custom/path/cookies.txt",
    cache_duration_hours=6
)
```

## Error Handling

**Chrome not found:**
```
[yellow]   Could not auto-extract cookies: Chrome not detected
[dim]   Run: uv run python agent_laboratory/extract_cookies.py
```

**Not logged into YouTube:**
```
⚠ Warning: No authentication cookies found!
   Make sure you're logged into YouTube in Chrome.
```

**Extraction fails:**
```
✗ Cookie extraction failed
# Falls back to browser extraction or shows manual instructions
```

## Files Modified/Created

1. **Created:** `src/video/cookie_manager.py` (270 lines)
2. **Modified:** `src/video/handler.py` (integrated cookie manager)

## Benefits

✅ **Zero Configuration** - Works out of the box
✅ **Automatic Refresh** - Daily re-extraction keeps session fresh
✅ **Transparent** - Shows what it's doing
✅ **Robust** - Graceful fallbacks for all failure modes
✅ **Debuggable** - Status command shows cookie state
✅ **WSL-Friendly** - Works with WSL2 Chrome

## Future Enhancements (Optional)

- Support multiple YouTube accounts (profile selection)
- Cookie health monitoring (detect when auth expires)
- Background refresh (proactive re-extraction)
- Encrypted cookie storage
- Multiple browser support (if needed later)
