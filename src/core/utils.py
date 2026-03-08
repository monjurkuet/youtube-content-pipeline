"""Core utility functions."""

import re
from pathlib import Path


def extract_video_id(source: str) -> str | None:
    """
    Extract YouTube video ID from URL or return as-is if it's already an ID.

    Args:
        source: YouTube URL or video ID

    Returns:
        11-character video ID or None if not found
    """
    if not source:
        return None

    # Already an ID
    if len(source) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", source):
        return source

    # Extract from URL
    patterns = [
        r"(?:v=|/v/|/embed/|/shorts/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            return match.group(1)

    return None


def download_remote_file(url: str, work_dir: Path) -> Path:
    """Download a remote file to the work directory."""
    import httpx
    import hashlib
    from pathlib import Path

    file_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    # Try to guess extension from URL
    ext = ".mp3"
    if ".wav" in url.lower(): ext = ".wav"
    elif ".opus" in url.lower(): ext = ".opus"
    elif ".m4a" in url.lower(): ext = ".m4a"

    output_path = work_dir / f"remote_{file_hash}{ext}"
    if output_path.exists():
        return output_path

    with httpx.Client(timeout=30) as client:
        response = client.get(url)
        response.raise_for_status()
        output_path.write_bytes(response.content)

    return output_path
