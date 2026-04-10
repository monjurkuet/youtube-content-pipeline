#!/usr/bin/env python3
"""
Strategy B Test: YouTube Watch Page Scrape

Tests if we can extract channel information from the YouTube watch page HTML.
"""

import json
import re
import sys

# Test videos - mix of different types
TEST_VIDEOS = [
    "dQw4w9WgXcQ",  # Rick Astley - Never Gonna Give You Up (famous, should work)
    "jNQXAC9IVRw",  # Me at the zoo (first YouTube video)
    "3tmd-ClpJxA",  # Example video
    "9bZkp7q19f0",  # PSY - Gangnam Style
    "kJQP7kiw5Fk",  # Luis Fonsi - Despacito
]


def extract_yt_initial_player_response(html: str) -> dict | None:
    """Extract ytInitialPlayerResponse from page HTML."""
    pattern = r"ytInitialPlayerResponse\s*=\s*({.+?});"
    match = re.search(pattern, html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def extract_yt_initial_data(html: str) -> dict | None:
    """Extract ytInitialData from page HTML."""
    patterns = [
        r"ytInitialData\s*=\s*({.+?});",
        r"var\s+ytInitialData\s*=\s*({.+?});",
    ]
    for pattern in patterns:
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
    except Exception:
        pass
    
    return None


def fetch_watch_page(video_id: str) -> str | None:
    """Fetch the YouTube watch page HTML."""
    import httpx
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
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


def test_strategy_b(video_id: str) -> dict | None:
    """Test Strategy B: Extract channel from watch page."""
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
    for pattern, source in [
        (r'"channelId"\s*:\s*"([a-zA-Z0-9_-]{24})"', "html_meta"),
        (r'"externalChannelId"\s*:\s*"([a-zA-Z0-9_-]{24})"', "html_external"),
    ]:
        match = re.search(pattern, html)
        if match:
            return {"channel_id": match.group(1), "source": source}
    
    return None


if __name__ == "__main__":
    print("=" * 60)
    print("STRATEGY B: YouTube Watch Page Scrape Test")
    print("=" * 60)
    print()
    
    results = []
    for video_id in TEST_VIDEOS:
        print(f"Testing video: {video_id}")
        result = test_strategy_b(video_id)
        
        if result:
            print(f"  ✓ SUCCESS")
            print(f"    Channel ID: {result['channel_id']}")
            print(f"    Channel Title: {result.get('channel_title', 'N/A')}")
            print(f"    Source: {result['source']}")
            results.append({"video_id": video_id, "success": True, "result": result})
        else:
            print(f"  ✗ FAILED - No channel info found")
            results.append({"video_id": video_id, "success": False, "result": None})
        print()
    
    # Summary
    success_count = sum(1 for r in results if r["success"])
    total = len(results)
    print("=" * 60)
    print(f"SUMMARY: {success_count}/{total} videos succeeded")
    print("=" * 60)
    
    # Exit with appropriate code
    sys.exit(0 if success_count == total else 1)
