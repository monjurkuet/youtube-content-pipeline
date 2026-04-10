# Strategy D: Structured Failure Response - TEST CODE

```python
#!/usr/bin/env python3
"""
Strategy D Test: Structured Failure Response

Tests returning structured error information instead of just None.
This allows the service layer to provide better feedback to users.
"""

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ResolutionStage(Enum):
    """Stages where resolution can fail."""
    VIDEO_ID_EXTRACT = "video_id_extract"
    YT_DLP = "ytdlp"
    WATCH_PAGE = "watch_page"
    INNERTUBE = "innertube"
    PAGE_PARSE = "page_parse"
    INVALID_URL = "invalid_url"


@dataclass
class ChannelResolutionResult:
    """
    Structured result from channel resolution.
    
    Attributes:
        success: Whether resolution succeeded
        channel_id: YouTube channel ID (if successful)
        channel_handle: Channel handle/name (if successful)
        channel_title: Full channel title (if successful)
        source: Which strategy succeeded ("ytdlp", "watch_page", "innertube")
        error_stage: Which stage failed (if failed)
        error_message: Human-readable error message
        retryable: Whether this can be retried
    """
    success: bool
    channel_id: Optional[str] = None
    channel_handle: Optional[str] = None
    channel_title: Optional[str] = None
    source: Optional[str] = None
    error_stage: Optional[ResolutionStage] = None
    error_message: Optional[str] = None
    retryable: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "success": self.success,
            "channel_id": self.channel_id,
            "channel_handle": self.channel_handle,
            "channel_title": self.channel_title,
            "source": self.source,
            "error_stage": self.error_stage.value if self.error_stage else None,
            "error_message": self.error_message,
            "retryable": self.retryable,
        }


def create_success_result(
    channel_id: str,
    channel_handle: str = "",
    channel_title: str = "",
    source: str = "ytdlp"
) -> ChannelResolutionResult:
    """Create a successful resolution result."""
    return ChannelResolutionResult(
        success=True,
        channel_id=channel_id,
        channel_handle=channel_handle,
        channel_title=channel_title,
        source=source,
    )


def create_failure_result(
    stage: ResolutionStage,
    message: str,
    retryable: bool = False
) -> ChannelResolutionResult:
    """Create a failed resolution result."""
    return ChannelResolutionResult(
        success=False,
        error_stage=stage,
        error_message=message,
        retryable=retryable,
    )


def test_strategy_d():
    """Test the structured failure response pattern."""
    print("=== Testing Strategy D: Structured Failure Response ===")
    print()
    
    # Test 1: Successful resolution
    print("[Test 1] Successful resolution")
    success_result = create_success_result(
        channel_id="UC9gF0R6W6e3nM6XW3K2nQ",
        channel_handle="TestChannel",
        channel_title="Test Channel",
        source="ytdlp"
    )
    print(f"  Success: {success_result.success}")
    print(f"  Channel ID: {success_result.channel_id}")
    print(f"  Source: {success_result.source}")
    print()
    
    # Test 2: Failed resolution - yt-dlp error
    print("[Test 2] Failed resolution - yt-dlp error")
    failure_result = create_failure_result(
        stage=ResolutionStage.YT_DLP,
        message="yt-dlp timeout after 30 seconds",
        retryable=True
    )
    print(f"  Success: {failure_result.success}")
    print(f"  Error Stage: {failure_result.error_stage.value}")
    print(f"  Error Message: {failure_result.error_message}")
    print(f"  Retryable: {failure_result.retryable}")
    print()
    
    # Test 3: Failed resolution - invalid URL
    print("[Test 3] Failed resolution - invalid URL")
    failure_result = create_failure_result(
        stage=ResolutionStage.INVALID_URL,
        message="Invalid YouTube URL format",
        retryable=False
    )
    print(f"  Success: {failure_result.success}")
    print(f"  Error Stage: {failure_result.error_stage.value}")
    print(f"  Retryable: {failure_result.retryable}")
    print()
    
    # Test 4: Convert to API response format
    print("[Test 4] Convert to API response format")
    api_response = failure_result.to_dict()
    print(f"  API Response: {api_response}")
    print()
    
    print("=== All tests passed ===")
    return True


if __name__ == "__main__":
    success = test_strategy_d()
    sys.exit(0 if success else 1)
```

## Integration with Service Layer

```python
# In channel_service.py
async def add_channels_from_videos_service(
    video_urls: list[str],
    db_manager: MongoDBManager,
    auto_sync: bool = True,
    sync_mode: Literal["recent", "all"] = "recent",
) -> dict[str, Any]:
    # ...
    for url in video_urls:
        video_id = extract_video_id(url)
        if not video_id:
            results["failed"].append({
                "url": url,
                "video_id": None,
                "error_stage": "video_id_extract",
                "error": "Invalid YouTube URL",
                "retryable": False,
            })
            continue
        
        # Get structured result instead of None
        result = get_channel_from_video(video_id)
        
        if not result.success:
            results["failed"].append({
                "url": url,
                "video_id": video_id,
                "error_stage": result.error_stage.value,
                "error": result.error_message,
                "retryable": result.retryable,
            })
            continue
        
        # Use result.channel_id, result.channel_handle, etc.
        channel_id = result.channel_id
        # ...
```

## Benefits

1. **Debugging**: Clear indication of which stage failed
2. **Retry Logic**: Retryable flag helps decide if retry makes sense
3. **User Feedback**: Better error messages for end users
4. **Monitoring**: Error stage can be used for metrics
5. **Testing**: Easier to mock and test different failure modes