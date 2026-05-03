"""Simple 2-step transcription pipeline: get transcript -> save to DB."""

import asyncio
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.core.config import get_settings
from src.core.exceptions import PipelineError, TranscriptionFailureError
from src.core.schemas import (
    ProcessingResult,
    RawTranscript,
    TranscriptDocument,
)
from src.transcription.failures import create_failure, failure_from_exception
from src.transcription.handler import TranscriptionHandler, identify_source_type

console = Console()


class TranscriptPipeline:
    """
    Simple transcription pipeline.

    Steps:
    1. Get transcript (via TranscriptionHandler with YouTube API / Whisper fallback)
    2. Save to MongoDB
    """

    def __init__(self, work_dir: Path | None = None):
        self.settings = get_settings()
        self.work_dir = work_dir or self.settings.work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.transcription = TranscriptionHandler(self.work_dir)

    def process(self, source: str, save_to_db: bool = True) -> ProcessingResult:
        """
        Main entry point for transcription.

        Args:
            source: YouTube URL, video URL, or local file path
            save_to_db: Whether to save transcript to MongoDB

        Returns:
            ProcessingResult with transcript information
        """
        # Identify source
        source_type, source_id = self.identify_source(source)

        # Initialize result
        started_at = datetime.now(timezone.utc)
        transcript_doc: TranscriptDocument | None = None

        console.print(
            f"\n[bold blue]📄 Transcribing {source_type} video: {source_id}[/bold blue]\n"
        )

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                # Step 1: Get transcript
                task = progress.add_task("Acquiring transcript...", total=None)
                console.print(f"[dim]Step 1/2: Acquiring transcript from {source_type}...[/dim]")

                raw_transcript = self.acquire_transcript(source_id, source_type)

                progress.update(task, completed=True)
                console.print(
                    f" [green]✓[/green] Step 1 COMPLETE: "
                    f"{len(raw_transcript.segments)} segments from {raw_transcript.source}"
                )
                console.print(
                    f" [dim] Transcript length: {len(raw_transcript.full_text)} chars[/dim]"
                )

                # Create transcript document
                transcript_doc = TranscriptDocument.from_raw_transcript(
                    raw_transcript=raw_transcript,
                    source_type=source_type,  # type: ignore
                    source_url=source if source_type in ("youtube", "url") else None,
                    title=None,
                )

                # Step 2: Save to database
                if save_to_db and self.settings.pipeline_save_to_db:
                    task = progress.add_task("Saving to database...", total=None)
                    console.print("[dim]Step 2/2: Saving transcript to MongoDB...[/dim]")

                    doc_id = self.save_transcript_document(transcript_doc)

                    progress.update(task, completed=True)
                    console.print(
                        f" [green]✓[/green] Step 2 COMPLETE: "
                        f"Saved to MongoDB (ID: {doc_id[:16]}...)"
                    )
                else:
                    console.print(" [dim]Step 2/2: Skipping database save[/dim]")

                # Build result
                completed_at = datetime.now(timezone.utc)
                duration_seconds = (completed_at - started_at).total_seconds()

                result = ProcessingResult(
                    video_id=source_id,
                    source_type=source_type,  # type: ignore
                    source_url=source if source_type in ("youtube", "url") else None,
                    transcript_source=raw_transcript.source,
                    segment_count=len(raw_transcript.segments),
                    duration_seconds=raw_transcript.duration,
                    total_text_length=len(raw_transcript.full_text),
                    language=raw_transcript.language,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds_total=duration_seconds,
                    saved_to_db=save_to_db and self.settings.pipeline_save_to_db,
                    transcript_id=doc_id if (save_to_db and self.settings.pipeline_save_to_db) else None,
                )

                console.print("\n[bold green]✅ Transcription complete![/bold green]")
                console.print(f" Duration: {duration_seconds:.1f}s")
                console.print(f" Segments: {len(raw_transcript.segments)}")
                console.print(f" Source: {raw_transcript.source}\n")

                return result

        except TranscriptionFailureError:
            raise
        except Exception as e:
            raise PipelineError(f"Pipeline failed: {e}") from e

    def identify_source(self, source: str) -> tuple[str, str]:
        """Identify the source type and canonical source identifier."""
        try:
            return identify_source_type(source)
        except Exception as exc:
            raise TranscriptionFailureError(
                failure_from_exception(
                    exc,
                    stage="source_identification",
                    default_category="invalid_source",
                    retryable=False,
                )
            ) from exc

    def acquire_transcript(self, source_id: str, source_type: str) -> RawTranscript:
        """Acquire a transcript without persisting it."""
        try:
            return self._get_transcript(source_id, source_type)
        except TranscriptionFailureError:
            raise
        except Exception as exc:
            raise TranscriptionFailureError(
                failure_from_exception(
                    exc,
                    stage="pipeline",
                    video_id=source_id if source_type == "youtube" else None,
                    default_category="unknown",
                    retryable=False,
                )
            ) from exc

    def persist_transcript(
        self,
        raw_transcript: RawTranscript,
        source_type: str,
        source: str,
    ) -> str:
        """Persist a transcript and update YouTube metadata when possible."""
        transcript_doc = TranscriptDocument.from_raw_transcript(
            raw_transcript=raw_transcript,
            source_type=source_type,  # type: ignore[arg-type]
            source_url=source if source_type in ("youtube", "url") else None,
            title=None,
        )
        return self.save_transcript_document(transcript_doc)

    def _get_transcript(self, source_id: str, source_type: str) -> RawTranscript:
        """Get transcript from source."""
        return self.transcription.get_transcript(source_id, source_type)

    @staticmethod
    async def save_transcript_document_async(transcript_doc: TranscriptDocument) -> str:
        """Save transcript to MongoDB (async-native).

        This is the canonical implementation — no thread-pool hacks.
        """
        from src.database import MongoDBManager

        async with MongoDBManager() as db:
            # Populate channel_id from video metadata if missing
            if not transcript_doc.channel_id:
                try:
                    video = await db.video_metadata.find_one(
                        {"video_id": transcript_doc.video_id},
                        {"channel_id": 1},
                    )
                    if video and video.get("channel_id"):
                        transcript_doc.channel_id = video["channel_id"]
                except Exception:
                    pass  # Non-critical — channel_id will be None

            doc_id = await db.save_transcript(transcript_doc)
            if transcript_doc.source_type == "youtube":
                await db.mark_transcript_completed(transcript_doc.video_id, doc_id)
            return doc_id

    def save_transcript_document(self, transcript_doc: TranscriptDocument) -> str:
        """Save transcript to MongoDB (sync wrapper for CLI usage).

        Detects whether we're inside a running event loop.
        - No loop: safe to use asyncio.run()
        - Inside loop: run in a separate thread with its own loop
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        try:
            if loop is None:
                # No running loop — safe to use asyncio.run()
                doc_id = asyncio.run(self.save_transcript_document_async(transcript_doc))
            else:
                # Already inside a loop (e.g. CLI's asyncio.run(process_all()))
                # Run in a separate thread with its own event loop
                import concurrent.futures

                def _run_in_thread() -> str:
                    return asyncio.run(self.save_transcript_document_async(transcript_doc))

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    doc_id = executor.submit(_run_in_thread).result()

            console.print(f" [green]✓ Database: Saved with ID {doc_id[:16]}...[/green]")
            return doc_id
        except TranscriptionFailureError:
            raise
        except Exception as e:
            console.print(f" [red]✗ Database: Save failed: {e}[/red]")
            raise TranscriptionFailureError(
                create_failure(
                    f"Database save failed: {e}",
                    "database",
                    "database",
                    video_id=transcript_doc.video_id,
                    retryable=False,
                )
            ) from e

    def _save_to_database(self, transcript_doc: TranscriptDocument) -> str:
        """Backward-compatible alias for existing tests and callers."""
        return self.save_transcript_document(transcript_doc)


def get_transcript(
    source: str,
    work_dir: Path | None = None,
    save_to_db: bool = True,
    language: str | None = None,
    verbose: bool = False,
) -> ProcessingResult:
    """
    Convenience function to transcribe a video.

    Args:
        source: YouTube URL, video URL, or local file path
        work_dir: Optional working directory
        save_to_db: Whether to save to MongoDB
        language: Preferred language code (currently unused, reserved for future)
        verbose: Whether to show verbose output

    Returns:
        ProcessingResult
    """
    pipeline = TranscriptPipeline(work_dir)
    return pipeline.process(source, save_to_db=save_to_db)
