# Strategy B: YouTube Watch Page Scrape - TEST CODE

```python
#!/usr/bin/env python3
"""
Strategy B Test: YouTube Watch Page Scrape

Tests if we can extract channel information from the YouTube watch page HTML.
This script fetches the watch page and parses embedded JSON to extract:
- channel_id
- channel_title
- video_title
"""

import json
import re
import sys
from urllib.parse import urlencode

# Test with a known public video
TEST_VIDEO_ID = "dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up


def extract_yt_initial_data(html: str) -> dict | None:
    """Extract ytInitialData from page HTML."""
    # Pattern 1: ytInitialData in a script tag
    pattern1 = r"ytInitialData\s*=\s*({.+?});"
    match = re.search(pattern1, html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Pattern 2: var ytInitialData = {...};
    pattern2 = r"var\s+ytInitialData\s*=\s*({.+?});"
    match = re.search(pattern2, html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    return None


def extract_yt_initial_player_response(html: str) -> dict | None:
    """Extract ytInitialPlayerResponse from page HTML."""
    # This contains videoDetails with channelId
    pattern = r"ytInitialPlayerResponse\s*=\s*({.+?});"
    match = re.search(pattern, html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def extract_channel_from_player_response(player_response: dict) -> dict | None:
    """Extract channel info from ytInitialPlayerResponse."""
    if not player_response:
        return None
    
    video_details = player_response.get("videoDetails")
    if not video_details:
        return None
    
    channel_id = video_details.get("channelId")
    channel_title = video_details.get("ownerChannelName")
    
    if channel_id:
        return {
            "channel_id": channel_id,
            "channel_title": channel_title,
            "video_title": video_details.get("title"),
            "source": "ytInitialPlayerResponse"
        }
    
    return None


def extract_channel_from_initial_data(initial_data: dict) -> dict | None:
    """Extract channel info from ytInitialData."""
    if not initial_data:
        return None
    
    # Navigate through the structure
    try:
        contents = initial_data.get("contents", {})
        two_col = contents.get("twoColumnWatchNextResults", {})
        
        # Owner section
        owner = two_col.get("owner", {})
        if owner:
            video_owner_renderer = owner.get("videoOwnerRenderer", {})
            title = video_owner_renderer.get("title", {})
            runs = title.get("runs", [])
            if runs:
                channel_title = runs[0].get("text", "")
                navigation_endpoint = runs[0].get("navigationEndpoint", {})
                browse_endpoint = navigation_endpoint.get("browseEndpoint", {})
                channel_id = browse_endpoint.get("browseId")
                
                if channel_id:
                    return {
                        "channel_id": channel_id,
                        "channel_title": channel_title,
                        "source": "ytInitialData.owner"
                    }
    except Exception as e:
        pass
    
    return None


def fetch_watch_page(video_id: str) -> str | None:
    """Fetch the YouTube watch page HTML."""
    import httpx
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
            else:
                print(f"HTTP {response.status_code}")
                return None
    except Exception as e:
        print(f"Fetch error: {e}")
        return None


def test_strategy_b(video_id: str = TEST_VIDEO_ID):
    """Test Strategy B: Extract channel from watch page."""
    print(f"=== Testing Strategy B: Watch Page Scrape ===")
    print(f"Video ID: {video_id}")
    print()
    
    # Step 1: Fetch watch page
    html = fetch_watch_page(video_id)
    if not html:
        return None
    
    # Step 2: Extract from player response
    player_response = extract_yt_initial_player_response(html)
    if player_response:
        channel_info = extract_channel_from_player_response(player_response)
        if channel_info:
            return channel_info
    
    # Step 3: Try ytInitialData
    initial_data = extract_yt_initial_data(html)
    if initial_data:
        channel_info = extract_channel_from_initial_data(initial_data)
        if channel_info:
            return channel_info
    
    # Step 4: Direct HTML patterns
    pattern = r'"channelId"\s*:\s*"([a-zA-Z0-9_-]{24})"'
    match = re.search(pattern, html)
    if match:
        return {"channel_id": match.group(1), "source": "html_meta"}
    
    return None


if __name__ == "__main__":
    video_id = sys.argv[1] if len(sys.argv) > 1 else TEST_VIDEO_ID
    result = test_strategy_b(video_id)
    
    if result:
        print(f"SUCCESS - Channel ID: {result.get('channel_id')}")
    else:
        print("FAILED - No channel info found")
```

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

## Expected Results

Based on testing, `ytInitialPlayerResponse` typically contains:
- `videoDetails.channelId` - The YouTube channel ID
- `videoDetails.ownerChannelName` - The channel title
- `videoDetails.title` - The video title

This is the most reliable path for Strategy B.