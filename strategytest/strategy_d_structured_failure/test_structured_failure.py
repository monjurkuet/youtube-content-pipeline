#!/usr/bin/env python3
"""
Strategy D Test: Structured Failure Response

Tests the structured failure pattern. This is a code pattern test.
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
    print("=" * 60)
    print("STRATEGY D: Structured Failure Response Test")
    print("=" * 60)
    print()
    
    all_passed = True
    
    # Test 1: Successful resolution
    print("[Test 1] Successful resolution")
    success_result = create_success_result(
        channel_id="UC9gF0R6W6e3nM6XW3K2nQ",
        channel_handle="TestChannel",
        channel_title="Test Channel",
        source="ytdlp"
    )
    assert success_result.success == True
    assert success_result.channel_id == "UC9gF0R6W6e3nM6XW3K2nQ"
    assert success_result.source == "ytdlp"
    print(f"  ✓ PASS - success={success_result.success}, channel_id={success_result.channel_id}")
    print()
    
    # Test 2: Failed resolution - yt-dlp error
    print("[Test 2] Failed resolution - yt-dlp error")
    failure_result = create_failure_result(
        stage=ResolutionStage.YT_DLP,
        message="yt-dlp timeout after 30 seconds",
        retryable=True
    )
    assert failure_result.success == False
    assert failure_result.error_stage == ResolutionStage.YT_DLP
    assert failure_result.retryable == True
    print(f"  ✓ PASS - error_stage={failure_result.error_stage.value}, retryable={failure_result.retryable}")
    print()
    
    # Test 3: Failed resolution - invalid URL
    print("[Test 3] Failed resolution - invalid URL")
    failure_result = create_failure_result(
        stage=ResolutionStage.INVALID_URL,
        message="Invalid YouTube URL format",
        retryable=False
    )
    assert failure_result.success == False
    assert failure_result.error_stage == ResolutionStage.INVALID_URL
    assert failure_result.retryable == False
    print(f"  ✓ PASS - error_stage={failure_result.error_stage.value}, retryable={failure_result.retryable}")
    print()
    
    # Test 4: Convert to API response format
    print("[Test 4] Convert to API response format")
    api_response = failure_result.to_dict()
    assert api_response["success"] == False
    assert api_response["error_stage"] == "invalid_url"
    assert api_response["retryable"] == False
    print(f"  ✓ PASS - API response: {api_response}")
    print()
    
    # Test 5: Test with real channel data from Strategy B results
    print("[Test 5] Real channel data integration")
    real_channel_ids = [
        "UCuAXFkgsw1L7xaCfnd5JJOw",  # Rick Astley
        "UC4QobU6STFB0P71PMvOGN5A",  # First video
    ]
    for cid in real_channel_ids:
        result = create_success_result(
            channel_id=cid,
            channel_handle="SomeChannel",
            source="watch_page"
        )
        assert result.success == True
        assert result.channel_id == cid
    print(f"  ✓ PASS - Processed {len(real_channel_ids)} real channel IDs")
    print()
    
    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_strategy_d()
    sys.exit(0 if success else 1)
