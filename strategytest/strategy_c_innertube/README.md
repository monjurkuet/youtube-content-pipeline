# Strategy C: Innertube API Fallback

This strategy tests using YouTube's internal API (innertube) to get channel information.

## Concept

YouTube uses an internal API called "innertube" for video playback. This API can be called directly:
- Endpoint: `https://www.youtube.com/youtubei/v1/player`
- Requires a payload with the video ID and context

## Feasibility Analysis

### Pros
- Returns structured JSON data
- More reliable than HTML parsing
- Contains detailed video metadata
- Used by actual YouTube player

### Cons
- Requires constructing a valid request body
- May require valid context/tokens
- YouTube may change API without notice
- Rate limiting possible

## Test Script

See `test_innertube_api.py` for the actual implementation.