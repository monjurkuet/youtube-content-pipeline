#!/usr/bin/env python3
"""Backfill error categories and reset legacy failed videos.

This script does two things:
1. Backfills the error_category field for videos that failed but have no
   error_category set (they'll be categorized based on their error_message).
2. Optionally resets failed videos to "pending" status so they get retried
   by the pipeline with the new fallback chain.

Usage:
    # Dry run (preview only, no changes):
    uv run python scripts/backfill_failures.py --dry-run

    # Backfill error categories only (no status reset):
    uv run python scripts/backfill_failures.py

    # Backfill + reset all failed videos to pending:
    uv run python scripts/backfill_failures.py --reset-failed

    # Backfill + reset only videos with specific error categories:
    uv run python scripts/backfill_failures.py --reset-failed --only-categories preflight_blocked,download_error
"""

import argparse
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_settings
from src.database.manager import MongoDBManager


# Patterns for classifying error messages into categories
ERROR_PATTERNS = {
    "preflight_blocked": [
        r"Sign in to confirm",
        r"pre-flight check failed",
        r"video availability",
    ],
    "download_error": [
        r"download failed",
        r"yt-dlp.*error",
        r"HTTP Error 4",
        r"Content too long",
        r"Requested format not available",
    ],
    "transcription_api_error": [
        r"Groq API error",
        r"429",
        r"rate.?limit",
        r"API error",
    ],
    "transcription_local_error": [
        r"whisper.*error",
        r"local service.*error",
        r"transcription failed",
    ],
    "file_error": [
        r"Audio file not found",
        r"No such file",
        r"file too large",
    ],
    "timeout_error": [
        r"timed? ?out",
        r"deadline exceeded",
    ],
    "unknown": [],  # Fallback — anything that doesn't match
}


def classify_error(error_message: str) -> str:
    """Classify an error message into a category."""
    if not error_message:
        return "unknown"

    for category, patterns in ERROR_PATTERNS.items():
        if category == "unknown":
            continue
        for pattern in patterns:
            if re.search(pattern, error_message, re.IGNORECASE):
                return category

    return "unknown"


def backfill_error_categories(db: MongoDBManager, dry_run: bool = False) -> int:
    """Backfill error_category for videos with no category set.

    Returns:
        Number of videos updated.
    """
    collection = db.db["videos"]

    # Find videos that failed but have no error_category
    query = {
        "status": "failed",
        "$or": [
            {"error_category": {"$exists": False}},
            {"error_category": None},
            {"error_category": ""},
        ],
    }

    videos = list(collection.find(query))
    print(f"Found {len(videos)} failed videos without error_category")

    if not videos:
        return 0

    # Classify and count
    category_counts: dict[str, int] = {}
    updates: list[tuple[str, str]] = []

    for video in videos:
        error_msg = video.get("error_message", "") or ""
        category = classify_error(error_msg)
        category_counts[category] = category_counts.get(category, 0) + 1
        updates.append((video["_id"], category))

    print("\nError category distribution:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        return 0

    # Apply updates
    updated = 0
    for video_id, category in updates:
        result = collection.update_one(
            {"_id": video_id},
            {"$set": {"error_category": category}},
        )
        if result.modified_count > 0:
            updated += 1

    print(f"\nUpdated {updated} videos with error categories")
    return updated


def reset_failed_videos(
    db: MongoDBManager,
    only_categories: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    """Reset failed videos to pending so they get retried.

    Args:
        db: Database manager.
        only_categories: If set, only reset videos with these error categories.
        dry_run: If True, don't make changes.

    Returns:
        Number of videos reset.
    """
    collection = db.db["videos"]

    query: dict = {"status": "failed"}
    if only_categories:
        query["error_category"] = {"$in": only_categories}

    videos = list(collection.find(query))
    print(f"\nFound {len(videos)} failed videos to reset")

    if not videos:
        return 0

    # Show what would be reset
    category_counts: dict[str, int] = {}
    for video in videos:
        cat = video.get("error_category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    print("Categories to reset:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        return 0

    # Reset to pending
    result = collection.update_many(
        query,
        {
            "$set": {
                "status": "pending",
                "error_message": "",
                "error_category": "",
                "transcription_source": "",
            },
            "$unset": {
                "transcribed_at": "",
            },
        },
    )

    print(f"\nReset {result.modified_count} videos to pending")
    return result.modified_count


def main():
    parser = argparse.ArgumentParser(
        description="Backfill error categories and reset legacy failed videos"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without making them",
    )
    parser.add_argument(
        "--reset-failed",
        action="store_true",
        help="Reset failed videos to pending so they get retried",
    )
    parser.add_argument(
        "--only-categories",
        type=str,
        default=None,
        help="Comma-separated list of error categories to reset (e.g., preflight_blocked,download_error)",
    )
    args = parser.parse_args()

    settings = get_settings()
    db = MongoDBManager(settings)

    try:
        db.connect()

        # Step 1: Backfill error categories
        print("=" * 60)
        print("Step 1: Backfilling error categories")
        print("=" * 60)
        backfill_error_categories(db, dry_run=args.dry_run)

        # Step 2: Optionally reset failed videos
        if args.reset_failed:
            print("\n" + "=" * 60)
            print("Step 2: Resetting failed videos")
            print("=" * 60)
            only_categories = None
            if args.only_categories:
                only_categories = [c.strip() for c in args.only_categories.split(",")]
            reset_failed_videos(
                db,
                only_categories=only_categories,
                dry_run=args.dry_run,
            )
        else:
            print("\n[INFO] Use --reset-failed to also reset videos to pending")

    finally:
        db.close()


if __name__ == "__main__":
    main()
