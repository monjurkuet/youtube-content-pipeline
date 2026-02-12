"""Main LLM-driven video analysis pipeline."""

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.core.config import get_settings
from src.core.exceptions import PipelineError
from src.core.schemas import (
    ProcessingMetadata,
    RawTranscript,
    TranscriptDocument,
    VideoAnalysisResult,
)
from src.llm_agents import (
    FrameIntelligenceAgent,
    SynthesisAgent,
    TranscriptIntelligenceAgent,
)
from src.transcription.handler import TranscriptionHandler, identify_source_type
from src.video.handler import VideoHandler

console = Console()


class LLMDrivenPipeline:
    """
    Production-ready LLM-driven video analysis pipeline.

    Makes exactly 3 LLM calls per video:
    1. Gemini 2.5 Flash - Transcript intelligence
    2. qwen3-vl-plus - Frame batch analysis (with individual fallback)
    3. Gemini 2.5 Flash - Final synthesis
    """

    def __init__(self, work_dir: Path | None = None):
        self.settings = get_settings()
        self.work_dir = work_dir or self.settings.work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.transcription = TranscriptionHandler(self.work_dir)
        self.video = VideoHandler(self.work_dir)

        # Initialize agents
        self.transcript_agent = TranscriptIntelligenceAgent()
        self.frame_agent = FrameIntelligenceAgent()
        self.synthesis_agent = SynthesisAgent()

        # Tracking
        self.llm_calls = 0

    def analyze(self, source: str) -> VideoAnalysisResult:
        """
        Main entry point for video analysis.

        Args:
            source: YouTube URL, video URL, or local file path

        Returns:
            VideoAnalysisResult with complete structured analysis
        """
        # Identify source
        source_type, source_id = identify_source_type(source)

        # Initialize metadata
        metadata = ProcessingMetadata(
            started_at=datetime.utcnow(),
            llm_calls_made=0,
        )

        console.print(f"\n[bold blue]🎬 Analyzing {source_type} video: {source_id}[/bold blue]\n")

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                # Step 1: Get transcript
                task = progress.add_task("📄 Acquiring transcript...", total=None)
                console.print(f"\n[dim]Step 1/7: Acquiring transcript from {source_type}...[/dim]")
                raw_transcript = self._get_transcript(source_id, source_type)
                metadata.transcript_source = raw_transcript.source
                progress.update(task, completed=True)
                console.print(
                    f"   [green]✓[/green] Step 1 COMPLETE: {len(raw_transcript.segments)} segments from {raw_transcript.source}"
                )
                console.print(
                    f"   [dim]   Transcript length: {len(raw_transcript.full_text)} chars[/dim]"
                )

                # Save transcript to database if enabled
                if self.settings.pipeline_save_to_db:
                    import asyncio

                    async def _save_transcript() -> str:
                        from src.database import get_db_manager

                        db = get_db_manager()
                        transcript_doc = TranscriptDocument.from_raw_transcript(
                            raw_transcript=raw_transcript,
                            source_type=source_type,  # type: ignore
                            source_url=source if source_type in ("youtube", "url") else None,
                            title=None,
                        )
                        doc_id = await db.save_transcript(transcript_doc)
                        return doc_id

                    try:
                        doc_id = asyncio.run(_save_transcript())
                        console.print(
                            f"   [dim]Database: Transcript saved (ID: {doc_id[:16]}...)[/dim]"
                        )
                    except Exception as e:
                        console.print(f"   [yellow]Database: Transcript save failed: {e}[/yellow]")

                # Step 2: Transcript Intelligence (LLM #1)
                task = progress.add_task("🧠 Agent 1: Analyzing transcript...", total=None)
                console.print(
                    "\n[dim]Step 2/7: Agent 1 (Gemini 2.5 Flash) analyzing transcript...[/dim]"
                )
                console.print(f"   [dim]   Model: {self.transcript_agent.model}[/dim]")
                transcript_intel = self.transcript_agent.analyze_with_fallback(
                    raw_transcript, use_batch=True
                )
                self.llm_calls += 1
                progress.update(task, completed=True)
                console.print(f"   [green]✓[/green] Step 2 COMPLETE: LLM Call #{self.llm_calls}")
                console.print(f"   [dim]   Content Type: {transcript_intel.content_type}[/dim]")
                console.print(
                    f"   [dim]   Primary Asset: {transcript_intel.primary_asset or 'N/A'}[/dim]"
                )
                console.print(f"   [dim]   Signals Found: {len(transcript_intel.signals)}[/dim]")
                console.print(
                    f"   [dim]   Price Levels: {len(transcript_intel.price_levels)}[/dim]"
                )
                console.print(
                    f"   [dim]   Frame Extraction Plan: {transcript_intel.frame_extraction_plan.suggested_count} frames suggested[/dim]"
                )

                # Step 3: Download video (only if we need frames)
                task = progress.add_task("⬇️  Downloading video...", total=None)
                console.print("\n[dim]Step 3/7: Downloading video for frame extraction...[/dim]")
                # For YouTube, use source_id (video ID), for others use full source
                video_identifier = source_id if source_type == "youtube" else source
                video_path = self._get_video(video_identifier, source_type)
                metadata.video_downloaded = True
                progress.update(task, completed=True)
                video_size_mb = video_path.stat().st_size / (1024 * 1024)
                console.print("   [green]✓[/green] Step 3 COMPLETE: Video downloaded")
                console.print(f"   [dim]   Path: {video_path}[/dim]")
                console.print(f"   [dim]   Size: {video_size_mb:.1f} MB[/dim]")

                # Step 4: Extract frames at LLM-suggested timestamps
                task = progress.add_task("🎬 Extracting frames...", total=None)
                console.print(
                    "\n[dim]Step 4/7: Extracting frames using LLM-suggested timestamps...[/dim]"
                )
                extraction_plan = transcript_intel.frame_extraction_plan
                console.print(
                    f"   [dim]   Suggested count: {extraction_plan.suggested_count}[/dim]"
                )
                console.print(f"   [dim]   Key moments: {len(extraction_plan.key_moments)}[/dim]")
                console.print(
                    f"   [dim]   Coverage interval: {extraction_plan.coverage_interval_seconds}s[/dim]"
                )
                frames = self.video.extract_frames(
                    video_path,
                    extraction_plan,
                )
                progress.update(task, completed=True)
                console.print(
                    f"   [green]✓[/green] Step 4 COMPLETE: {len(frames)} frames extracted"
                )
                if frames:
                    console.print(f"   [dim]   First frame: {frames[0].name}[/dim]")
                    console.print(f"   [dim]   Last frame: {frames[-1].name}[/dim]")

                # Step 5: Frame Intelligence (LLM #2)
                task = progress.add_task("👁️  Agent 2: Analyzing frames...", total=None)
                console.print(
                    f"\n[dim]Step 5/7: Agent 2 (qwen3-vl-plus) analyzing {len(frames)} frames...[/dim]"
                )
                console.print(f"   [dim]   Model: {self.frame_agent.model}[/dim]")
                console.print(f"   [dim]   Batch size: {self.settings.frame_batch_size}[/dim]")
                frame_intel = self.frame_agent.analyze_with_fallback(frames)
                self.llm_calls += 1
                progress.update(task, completed=True)
                console.print(f"   [green]✓[/green] Step 5 COMPLETE: LLM Call #{self.llm_calls}")
                console.print(
                    f"   [dim]   Total analyzed: {frame_intel.summary.total_frames_analyzed}[/dim]"
                )
                console.print(
                    f"   [dim]   Frames selected: {frame_intel.summary.frames_selected}[/dim]"
                )
                console.print(
                    f"   [dim]   Redundancy groups: {frame_intel.summary.redundancy_groups_found}[/dim]"
                )
                if frame_intel.summary.primary_assets_visualized:
                    console.print(
                        f"   [dim]   Assets visualized: {', '.join(frame_intel.summary.primary_assets_visualized)}[/dim]"
                    )

                # Step 6: Final Synthesis (LLM #3)
                task = progress.add_task("🔄 Agent 3: Synthesizing...", total=None)
                console.print(
                    "\n[dim]Step 6/7: Agent 3 (Gemini 2.5 Flash) synthesizing final analysis...[/dim]"
                )
                console.print(f"   [dim]   Model: {self.synthesis_agent.model}[/dim]")
                console.print(
                    f"   [dim]   Input: {len(transcript_intel.signals)} signals + {frame_intel.summary.frames_selected} frames[/dim]"
                )
                synthesis = self.synthesis_agent.synthesize_with_fallback(
                    transcript_intel,
                    frame_intel,
                )
                self.llm_calls += 1
                progress.update(task, completed=True)
                console.print(f"   [green]✓[/green] Step 6 COMPLETE: LLM Call #{self.llm_calls}")
                console.print(
                    f"   [dim]   Executive summary: {len(synthesis.executive_summary)} chars[/dim]"
                )
                console.print(
                    f"   [dim]   Detailed analysis: {len(synthesis.detailed_analysis)} chars[/dim]"
                )
                console.print(f"   [dim]   Key takeaways: {len(synthesis.key_takeaways)}[/dim]")
                if synthesis.consistency_notes:
                    console.print("   [dim]   Consistency notes present: Yes[/dim]")

            # Build final result
            metadata.completed_at = datetime.utcnow()
            metadata.duration_seconds = (
                metadata.completed_at - metadata.started_at
            ).total_seconds()
            metadata.llm_calls_made = self.llm_calls

            result = VideoAnalysisResult.from_agents(
                video_id=source_id,
                source_type=source_type,
                source_url=source if source_type in ("youtube", "url") else None,
                title=None,  # Could extract from video metadata
                duration=raw_transcript.duration,
                transcript_intel=transcript_intel,
                frame_intel=frame_intel,
                synthesis=synthesis,
                metadata=metadata,
            )

            # Save result
            self._save_result(result)

            # Save to database if enabled
            if self.settings.pipeline_save_to_db:
                self._save_to_database(result)

            console.print("\n[bold green]✅ Analysis complete![/bold green]")
            console.print(f"   Duration: {metadata.duration_seconds:.1f}s")
            console.print(f"   LLM calls: {self.llm_calls}")
            console.print(f"   Result saved to: {self.work_dir}/result.json\n")

            return result

        except Exception as e:
            raise PipelineError(f"Pipeline failed: {e}") from e

    def _get_transcript(self, source_id: str, source_type: str) -> RawTranscript:
        """Get transcript from source."""
        return self.transcription.get_transcript(source_id, source_type)

    def _get_video(self, source: str, source_type: str) -> Path:
        """Get video path (download if needed)."""
        return self.video.download_video(source, source_type)

    def _save_result(self, result: VideoAnalysisResult) -> None:
        """Save result to JSON file."""
        output_path = self.work_dir / "result.json"
        with open(output_path, "w") as f:
            json.dump(result.model_dump_for_mongo(), f, indent=2, default=str)

    def _save_to_database(self, result: VideoAnalysisResult) -> None:
        """Save result to MongoDB.

        Runs async database operations in sync context.
        """
        import asyncio

        async def _save() -> str:
            from src.database import get_db_manager

            db = get_db_manager()
            try:
                doc_id = await db.save_analysis(result)
                return doc_id
            finally:
                await db.close()

        try:
            doc_id = asyncio.run(_save())
            console.print(f"   [dim]Database: Saved to MongoDB (ID: {doc_id[:16]}...)[/dim]")
        except Exception as e:
            console.print(f"   [yellow]Database: Save failed: {e}[/yellow]")


def analyze_video(source: str, work_dir: Path | None = None) -> VideoAnalysisResult:
    """
    Convenience function to analyze a video.

    Args:
        source: YouTube URL, video URL, or local file path
        work_dir: Optional working directory

    Returns:
        VideoAnalysisResult
    """
    pipeline = LLMDrivenPipeline(work_dir)
    return pipeline.analyze(source)
