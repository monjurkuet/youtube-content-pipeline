# Strategy C: Innertube API Fallback - TEST CODE

```python
#!/usr/bin/env python3
"""
Strategy C Test: YouTube Innertube API

Tests using YouTube's internal API to extract channel information.
The innertube API is what the YouTube player uses internally.
"""

import json
import sys

TEST_VIDEO_ID = "dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up

# YouTube innertube API endpoint
INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/player"


def build_innertube_payload(video_id: str) -> dict:
    """Build the innertube API request payload."""
    return {
        "videoId": video_id,
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20231031.06.01",
                "platform": "DESKTOP",
            }
        }
    }


def fetch_innertube(video_id: str) -> dict | None:
    """Call the innertube API to get video details."""
    import httpx
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    payload = build_innertube_payload(video_id)
    
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                INNERTUBE_URL,
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"HTTP {response.status_code}: {response.text[:200]}")
                return None
    except Exception as e:
        print(f"Request error: {e}")
        return None


def extract_channel_from_innertube(data: dict) -> dict | None:
    """Extract channel info from innertube response."""
    if not data:
        return None
    
    # Check for error responses
    if "error" in data:
        error_code = data.get("error", {}).get("code", 0)
        print(f"Innertube error: {error_code}")
        return None
    
    # videoDetails contains channelId
    video_details = data.get("videoDetails", {})
    if not video_details:
        return None
    
    channel_id = video_details.get("channelId")
    channel_title = video_details.get("ownerChannelName")
    
    if channel_id:
        return {
            "channel_id": channel_id,
            "channel_title": channel_title,
            "video_title": video_details.get("title"),
            "source": "innertube"
        }
    
    return None


def test_strategy_c(video_id: str = TEST_VIDEO_ID):
    """Test Strategy C: Innertube API."""
    print(f"=== Testing Strategy C: Innertube API ===")
    print(f"Video ID: {video_id}")
    print(f"Endpoint: {INNERTUBE_URL}")
    print()
    
    print("[1/2] Calling innertube API...")
    data = fetch_innertube(video_id)
    
    if not data:
        print("FAIL: No response from innertube")
        return None
    
    print(f"SUCCESS: Received {len(json.dumps(data))} bytes")
    print()
    
    print("[2/2] Extracting channel info...")
    channel_info = extract_channel_from_innertube(data)
    
    if channel_info:
        print(f"  Channel ID: {channel_info['channel_id']}")
        print(f"  Channel Title: {channel_info['channel_title']}")
        print(f"  Source: {channel_info['source']}")
        return channel_info
    
    print("NOT FOUND: No channel info in response")
    return None


if __name__ == "__main__":
    video_id = sys.argv[1] if len(sys.argv) > 1 else TEST_VIDEO_ID
    result = test_strategy_c(video_id)
    
    if result:
        print(f"SUCCESS - Channel ID: {result.get('channel_id')}")
    else:
        print("FAILED - No channel info found")
```

## Expected Results

The innertube API returns a JSON response with:
- `videoDetails.channelId` - The YouTube channel ID
- `videoDetails.ownerChannelName` - The channel name
- `videoDetails.title` - The video title
- `videoDetails.lengthSeconds` - Duration
- And much more metadata

## Rate Limiting Considerations

- YouTube may return 429 (Too Many Requests) if overused
- Consider adding delays between requests
- No authentication required for public videos

## Error Codes

Common innertube errors:
- 401: Unauthorized (may need cookies for some videos)
- 403: Forbidden (video may be region-locked)
- 404: Video not found
- 429: Rate limited