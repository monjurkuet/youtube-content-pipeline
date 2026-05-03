# Plan: Members-Only & Permanent Failure Tagging

## Problem
When videos are members-only (or other permanent failures like private, geo-restricted), they get marked as `transcript_status: "failed"` but without an `error_category`. This causes:
1. **`transcribe-pending`** doesn't pass error_category to `mark_transcript_failed` — the CLI's `check_video_availability` returns `tuple[bool, str]` instead of `tuple[bool, str, str]`
2. **Retry loops**: `get_pending_transcription_videos` returns ALL pending videos regardless of whether they previously had a permanent failure. When `reset_failed_transcription` resets to "pending", permanently-failed videos get retried unnecessarily.
3. **No visibility**: `channel videos` display doesn't show error category for failed videos.

## Changes

### 1. `src/cli/commands/channel.py` — `transcribe-pending` command
- Update `check_video_availability` to return `tuple[bool, str, str]` (add error_category), matching the `retry-failed` implementation
- Add `availability` field check for `members_only` from yt-dlp JSON output
- Add geo_restricted detection
- Add `403/forbidden` → `temporary_block` detection
- Pass error_category to `db.mark_transcript_failed(video.video_id, reason, error_category)`
- Also pass error_category in the exception handler at line 555
- Add `--skip-permanent` flag (like `retry-failed` has) to skip videos with known permanent categories during retry
- Update `channel videos` table to show error category for failed videos

### 2. `src/database/manager.py` — `get_pending_transcription_videos`
- Add optional `skip_permanent_failures` parameter (default: True)
- When True, exclude videos where `transcript_error_category` is in `PERMANENT_FAILURE_CATEGORIES`

### 3. `src/services/video_service.py` — `get_pending_videos`
- Pass through `skip_permanent_failures` parameter

### 4. `src/transcription/failures.py`
- Define `PERMANENT_FAILURE_CATEGORIES` constant (already have `RETRYABLE_FAILURE_CATEGORIES`)
- Permanent = all categories that are NOT retryable AND not unknown

### 5. Tests
- Update `test_channel_retry_failed.py` for new behavior
- Add test for `get_pending_videos` skipping permanent failures
- Add test for `transcribe-pending` passing error category

### 6. Docs
- Update README.md with `--skip-permanent` flag docs
- Update AGENTS.md with failure category reference
