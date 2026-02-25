"""Simple 2-step transcription pipeline: get transcript -> save to DB."""

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.core.config import get_settings
from src.core.exceptions import PipelineError
from src.core.schemas import (
    ProcessingResult,
    RawTranscript,
    TranscriptDocument,
)
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
        source_type, source_id = identify_source_type(source)

        # Initialize result
        started_at = datetime.utcnow()
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

                raw_transcript = self._get_transcript(source_id, source_type)

                progress.update(task, completed=True)
                console.print(
                    f"   [green]✓[/green] Step 1 COMPLETE: "
                    f"{len(raw_transcript.segments)} segments from {raw_transcript.source}"
                )
                console.print(
                    f"   [dim]   Transcript length: {len(raw_transcript.full_text)} chars[/dim]"
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

                    doc_id = self._save_to_database(transcript_doc)

                    progress.update(task, completed=True)
                    console.print(
                        f"   [green]✓[/green] Step 2 COMPLETE: "
                        f"Saved to MongoDB (ID: {doc_id[:16]}...)"
                    )
                else:
                    console.print("   [dim]Step 2/2: Skipping database save[/dim]")

            # Build result
            completed_at = datetime.utcnow()
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
            )

            console.print("\n[bold green]✅ Transcription complete![/bold green]")
            console.print(f"   Duration: {duration_seconds:.1f}s")
            console.print(f"   Segments: {len(raw_transcript.segments)}")
            console.print(f"   Source: {raw_transcript.source}\n")

            return result

        except Exception as e:
            raise PipelineError(f"Pipeline failed: {e}") from e

    def _get_transcript(self, source_id: str, source_type: str) -> RawTranscript:
        """Get transcript from source."""
        return self.transcription.get_transcript(source_id, source_type)

    def _save_to_database(self, transcript_doc: TranscriptDocument) -> str:
        """Save transcript to MongoDB.

        Runs async database operations in sync context.
        Uses a separate thread with its own event loop to avoid conflicts.
        """
        import asyncio
        import concurrent.futures

        async def _save() -> str:
            from src.database import MongoDBManager

            # Use context manager for proper lifecycle management
            async with MongoDBManager() as db:
                doc_id = await db.save_transcript(transcript_doc)
                return doc_id

        def _run_in_thread() -> str:
            # Each thread gets its own event loop with asyncio.run()
            return asyncio.run(_save())

        try:
            # Run async DB operation in a separate thread to avoid event loop conflicts
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_in_thread)
                doc_id = future.result()
                console.print(f"   [green]✓ Database: Saved with ID {doc_id[:16]}...[/green]")
                return doc_id
        except Exception as e:
            console.print(f"   [red]✗ Database: Save failed: {e}[/red]")
            raise


def get_transcript(
    source: str,
    work_dir: Path | None = None,
    save_to_db: bool = True,
) -> ProcessingResult:
    """
    Convenience function to transcribe a video.

    Args:
        source: YouTube URL, video URL, or local file path
        work_dir: Optional working directory
        save_to_db: Whether to save to MongoDB

    Returns:
        ProcessingResult
    """
    pipeline = TranscriptPipeline(work_dir)
    return pipeline.process(source, save_to_db=save_to_db)
