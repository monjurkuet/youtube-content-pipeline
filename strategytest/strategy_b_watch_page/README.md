# Strategy B: YouTube Watch Page Scrape

This strategy tests fetching the YouTube watch page directly and extracting channel information from HTML/JSON.

## Concept

When a user provides a video URL like `https://www.youtube.com/watch?v=VIDEO_ID`, we can:
1. Fetch the watch page HTML
2. Extract embedded JSON data (ytInitialPlayerResponse, ytInitialData)
3. Parse channel_id, channel_title, and other metadata

## Feasibility Analysis

### Pros
- No external tool dependency (yt-dlp)
- Direct HTTP request with standard headers
- Returns rich metadata including title, thumbnails, etc.
- Works without cookies

### Cons
- YouTube frequently changes page structure
- HTML parsing is fragile
- May need to handle CAPTCHA or rate limiting
- Large page download (multiple MBs)

## Test Script

See `test_watch_page_scrape.py` for the actual implementation.