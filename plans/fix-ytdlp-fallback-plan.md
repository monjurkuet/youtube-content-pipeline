# Fix yt-dlp Fallback - ROOT CAUSE & FIX

## Problem
When RSS feed fails (404), the code falls back to `fetch_recent_with_ytdlp`. It found 45 video IDs but fetched **0 videos** - all were silently skipped.

## Root Cause Confirmed

**Cookies + `--simulate` = "format not available" error**

Testing showed:
```bash
# WITHOUT cookies - WORKS
yt-dlp --simulate --dump-json "https://www.youtube.com/watch?v=vByUgzw4NHU"
# Returns full JSON metadata ✓

# WITH cookies - FAILS
yt-dlp --simulate --dump-json --cookies /path/to/cookies.txt "https://www.youtube.com/watch?v=vByUgzw4NHU"
# ERROR: Requested format is not available ✗
```

The error message doesn't contain "age"+"restrict" or "private"/"unavailable", so all videos were silently skipped.

This was already documented in `fetch_all_with_ytdlp` (lines 344-348) but NOT in `fetch_recent_with_ytdlp`.

## Fix Applied

Removed cookie usage from `fetch_recent_with_ytdlp` in `src/channel/feed_fetcher.py`:
- Removed `_ensure_cookies()` call
- Removed `cmd.extend(cookie_args)` lines

Now `fetch_recent_with_ytdlp` is consistent with `fetch_all_with_ytdlp`.

## Verification

Before fix:
```
Found 45 videos, fetching metadata...
✓ Fetched 0 videos  ← FAILURE
```

After fix:
```
Found 45 videos, fetching metadata...
✓ Fetched 45 videos
✓ Sync complete: 11 new, 34 existing  ← SUCCESS
```

## Files Modified
- `src/channel/feed_fetcher.py`: Removed cookie args from `fetch_recent_with_ytdlp`
