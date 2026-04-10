# Strategy D: Structured Failure Response

This strategy tests returning structured error information instead of just `None`.

## Concept

When resolution fails, instead of returning `None`, we should return a structured object containing:
- Error stage (what failed)
- Error message (why it failed)
- Retryable flag (can we try again)
- HTTP status (if applicable)

## Current Behavior (Problem)

```python
def get_channel_from_video(video_id: str) -> dict[str, str] | None:
    # ...
    return None  # No context about failure!
```

## Proposed Behavior (Solution)

```python
from dataclasses import dataclass
from enum import Enum

class ResolutionStage(Enum):
    VIDEO_ID_EXTRACT = "video_id_extract"
    YT_DLP = "ytdlp"
    WATCH_PAGE = "watch_page"
    INNERTUBE = "innertube"
    PAGE_PARSE = "page_parse"

@dataclass
class ChannelResolutionResult:
    success: bool
    channel_id: str | None = None
    channel_handle: str | None = None
    channel_title: str | None = None
    source: str | None = None  # "ytdlp", "watch_page", "innertube"
    error_stage: ResolutionStage | None = None
    error_message: str | None = None
    retryable: bool = False
```

## Usage Example

```python
result = get_channel_from_video(video_id)

if result.success:
    # Use channel_id, channel_handle, etc.
    print(f"Resolved: {result.channel_id}")
else:
    # Handle failure with context
    print(f"Failed at stage: {result.error_stage}")
    print(f"Error: {result.error_message}")
    print(f"Retryable: {result.retryable}")
```

## Test Script

See `test_structured_failure.py` for implementation examples.