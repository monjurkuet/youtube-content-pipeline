#!/usr/bin/env python3
"""
Strategy C Test: YouTube Innertube API

Tests using YouTube's internal API to extract channel information.
"""

import json
import sys

# Test videos - mix of different types
TEST_VIDEOS = [
    "dQw4w9WgXcQ",  # Rick Astley - Never Gonna Give You Up (famous, should work)
    "jNQXAC9IVRw",  # Me at the zoo (first YouTube video)
    "3tmd-ClpJxA",  # Example video
    "9bZkp7q19f0",  # PSY - Gangnam Style
    "kJQP7kiw5Fk",  # Luis Fonsi - Despacito
]


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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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


def test_strategy_c(video_id: str) -> dict | None:
    """Test Strategy C: Innertube API."""
    data = fetch_innertube(video_id)
    
    if not data:
        return None
    
    return extract_channel_from_innertube(data)


if __name__ == "__main__":
    print("=" * 60)
    print("STRATEGY C: YouTube Innertube API Test")
    print("=" * 60)
    print()
    
    results = []
    for video_id in TEST_VIDEOS:
        print(f"Testing video: {video_id}")
        result = test_strategy_c(video_id)
        
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
