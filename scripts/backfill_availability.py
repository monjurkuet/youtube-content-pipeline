#!/usr/bin/env python3
"""Backfill video availability from yt-dlp for existing MongoDB documents.

Finds videos with availability="unknown" and queries yt-dlp for their
actual availability status, then updates MongoDB in bulk.

Usage:
    uv run python scripts/backfill_availability.py                  # live run
    uv run python scripts/backfill_availability.py --dry-run        # preview only
    uv run python scripts/backfill_availability.py --batch-size 20 # smaller batches
    uv run python scripts/backfill_availability.py --channel UCX6OQ3DkcsbYNE6H8uQQuVA
"""

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.constants import YTDLP_AVAILABILITY_MAP
from src.database.manager import MongoDBManager


async def backfill_availability(
    batch_size: int = 50,
    dry_run: bool = False,
    channel_id: str | None = None,
) -> dict:
    """Backfill availability for videos with unknown status.

    Args:
        batch_size: Number of videos to check per batch
        dry_run: If True, only report what would be changed
        channel_id: Optional channel ID filter

    Returns:
        Summary dict with counts
    """
    async with MongoDBManager() as db:
        # Find videos with unknown availability
        query: dict = {"availability": {"$in": ["unknown", None]}}
        if channel_id:
            query["channel_id"] = channel_id

        cursor = db.video_metadata.find(query, {
            "video_id": 1,
            "channel_id": 1,
            "title": 1,
            "availability": 1,
        })
        videos = await cursor.to_list(length=None)

    if not videos:
        print("No videos with unknown availability found.")
        return {"total": 0, "updated": 0, "unchanged": 0, "errors": 0}

    print(f"Found {len(videos)} videos with unknown availability")

    total = len(videos)
    updated = 0
    unchanged = 0
    errors = 0
    availability_counts: dict[str, int] = {}

    for i in range(0, total, batch_size):
        batch = videos[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        print(f"\nBatch {batch_num}/{total_batches}: checking {len(batch)} videos...")

        for video in batch:
            video_id = video["video_id"]
            title = video.get("title", "Unknown")[:50]

            try:
                result = subprocess.run(
                    [
                        "yt-dlp",
                        "--flat-playlist",
                        "--dump-json",
                        "--no-warnings",
                        "--quiet",
                        f"https://www.youtube.com/watch?v={video_id}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    stderr = result.stderr.strip().lower()
                    # Classify the error
                    if "private" in stderr:
                        availability = "private"
                    elif "unavailable" in stderr or "not available" in stderr:
                        availability = "unavailable"
                    elif "members-only" in stderr or "premium" in stderr:
                        availability = "members_only"
                    elif "geo" in stderr or "country" in stderr:
                        availability = "geo_restricted"
                    elif "age" in stderr and "restricted" in stderr:
                        availability = "age_restricted"
                    else:
                        availability = "unknown"
                        errors += 1
                        print(f"  ⊘ {video_id}: error - {stderr[:80]}")
                        continue
                else:
                    data = json.loads(result.stdout.strip())
                    raw_availability = data.get("availability", "unknown") or "unknown"
                    availability = YTDLP_AVAILABILITY_MAP.get(raw_availability, "unknown")

                availability_counts[availability] = availability_counts.get(availability, 0) + 1

                if availability == "unknown":
                    unchanged += 1
                    continue

                print(f"  {'[DRY] ' if dry_run else ''}{video_id}: unknown → {availability} ({title})")

                if not dry_run:
                    async with MongoDBManager() as db:
                        await db.video_metadata.update_one(
                            {"video_id": video_id},
                            {"$set": {"availability": availability}},
                        )
                    updated += 1
                else:
                    updated += 1

            except subprocess.TimeoutExpired:
                errors += 1
                print(f"  ⊘ {video_id}: yt-dlp timeout")
            except json.JSONDecodeError:
                errors += 1
                print(f"  ⊘ {video_id}: invalid JSON response")
            except Exception as e:
                errors += 1
                print(f"  ⊘ {video_id}: {e}")

        # Rate limit between batches
        if i + batch_size < total:
            print("  Rate limiting: waiting 5s between batches...")
            await asyncio.sleep(5)

    summary = {
        "total": total,
        "updated": updated,
        "unchanged": unchanged,
        "errors": errors,
        "availability_breakdown": availability_counts,
    }

    print(f"\n{'='*50}")
    print(f"Backfill {'(DRY RUN) ' if dry_run else ''}Complete")
    print(f"  Total checked: {total}")
    print(f"  Updated: {updated}")
    print(f"  Still unknown: {unchanged}")
    print(f"  Errors: {errors}")
    print(f"  Availability breakdown:")
    for avail, count in sorted(availability_counts.items()):
        print(f"    {avail}: {count}")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Backfill video availability from yt-dlp"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to MongoDB",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of videos to check per batch (default: 50)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="Only backfill videos for a specific channel ID",
    )

    args = parser.parse_args()

    asyncio.run(
        backfill_availability(
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            channel_id=args.channel,
        )
    )


if __name__ == "__main__":
    main()
