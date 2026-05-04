#!/usr/bin/env python3
"""Backfill stale transcript failures.

Finds videos with failed transcript status whose error category is
retryable (temporary_block, unknown, or missing) and whose failure
count exceeds MAX_RETRIES_BEFORE_PERMANENT, then escalates them to
permanent "unavailable" status.

Also handles legacy documents that lack transcript_failure_count
by treating them as having exceeded the threshold (they've been
failing across many cron runs without tracking).

Usage:
    # Dry run — preview what would change
    uv run python scripts/backfill_stale_transcript_failures.py --dry-run

    # Live run — updates MongoDB
    uv run python scripts/backfill_stale_transcript_failures.py

    # Specific channel only
    uv run python scripts/backfill_stale_transcript_failures.py --channel UCnwxzpFzZNtLH8NgTeAROFA

    # Force-escalate all stale failures (even without failure count)
    uv run python scripts/backfill_stale_transcript_failures.py --force-legacy
"""

import argparse
import asyncio

from src.core.constants import (
    MAX_RETRIES_BEFORE_PERMANENT,
    PERMANENT_AVAILABILITY,
)
from src.database.manager import MongoDBManager


async def main(
    dry_run: bool = False,
    channel_id: str | None = None,
    force_legacy: bool = False,
) -> None:
    async with MongoDBManager() as db:
        await db.initialize()

        # Build query: failed videos with retryable/missing error category
        query: dict = {
            "transcript_status": "failed",
            "$or": [
                {"transcript_error_category": {"$in": ["temporary_block", "unknown"]}},
                {"transcript_error_category": None},
                {"transcript_error_category": {"$exists": False}},
            ],
        }

        if channel_id:
            query["channel_id"] = channel_id

        cursor = db.video_metadata.find(query)
        scanned = 0
        updated = 0
        skipped_no_count = 0

        while True:
            docs = await cursor.to_list(length=500)
            if not docs:
                break

            for doc in docs:
                scanned += 1
                video_id = doc.get("video_id", "?")
                title = doc.get("title", "?")[:50]
                category = doc.get("transcript_error_category") or "unknown"
                availability = doc.get("availability", "unknown")
                failure_count = doc.get("transcript_failure_count", 0) or 0

                # Decision: escalate if count exceeds threshold OR force-legacy
                should_escalate = False
                reason = ""

                if failure_count > MAX_RETRIES_BEFORE_PERMANENT:
                    should_escalate = True
                    reason = f"failure_count={failure_count} > {MAX_RETRIES_BEFORE_PERMANENT}"
                elif force_legacy and failure_count == 0:
                    # Legacy docs without failure count — assume stale
                    should_escalate = True
                    reason = "force-legacy (no failure count tracked)"
                    skipped_no_count += 1

                if not should_escalate:
                    if failure_count > 0:
                        print(
                            f"  SKIP {video_id} | count={failure_count} "
                            f"(below threshold {MAX_RETRIES_BEFORE_PERMANENT})"
                        )
                    continue

                action = "WOULD ESCALATE" if dry_run else "ESCALATED"
                print(
                    f"  {action} {video_id} | {title} | "
                    f"cat={category} → unavailable | "
                    f"avail={availability} → unavailable | {reason}"
                )

                if not dry_run:
                    result = await db.video_metadata.update_one(
                        {"video_id": video_id},
                        {
                            "$set": {
                                "transcript_error_category": "unavailable",
                                "availability": "unavailable",
                            }
                        },
                    )
                    if result.modified_count > 0:
                        updated += 1

        print(f"\nScanned: {scanned}")
        print(f"{'Would update' if dry_run else 'Updated'}: {updated}")
        if skipped_no_count:
            print(f"Force-legacy escalations: {skipped_no_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill stale transcript failures to permanent unavailable"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to MongoDB",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="Only process videos from this channel ID",
    )
    parser.add_argument(
        "--force-legacy",
        action="store_true",
        help="Force-escalate legacy docs that lack transcript_failure_count",
    )
    args = parser.parse_args()

    asyncio.run(main(
        dry_run=args.dry_run,
        channel_id=args.channel,
        force_legacy=args.force_legacy,
    ))
