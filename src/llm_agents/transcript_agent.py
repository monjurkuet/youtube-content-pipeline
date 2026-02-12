"""Agent 1: Transcript Intelligence - Extracts structured data from transcripts."""

from pathlib import Path

from src.core.config import get_settings
from src.core.exceptions import TranscriptAgentError
from src.core.schemas import (
    FrameExtractionMoment,
    FrameExtractionPlan,
    RawTranscript,
    TranscriptIntelligence,
)
from src.llm_agents.base import BaseAgent


class TranscriptIntelligenceAgent(BaseAgent):
    """Analyzes transcripts to extract structured trading data."""

    @property
    def model(self) -> str:
        return get_settings().llm_transcript_model

    @property
    def timeout(self) -> int:
        return get_settings().transcript_timeout

    def _load_prompt_template(self) -> str:
        """Load the prompt template from file."""
        prompt_path = Path(__file__).parent / "prompts" / "transcript_intelligence.txt"
        return prompt_path.read_text()

    def analyze(self, transcript: RawTranscript) -> TranscriptIntelligence:
        """
        Analyze raw transcript and extract structured intelligence.

        Args:
            transcript: RawTranscript object with segments

        Returns:
            TranscriptIntelligence with structured data
        """
        try:
            # Build transcript text with timestamps
            transcript_text = self._format_transcript_for_llm(transcript)

            # Load and fill prompt template
            template = self._load_prompt_template()
            # Use replace instead of format to avoid issues with curly braces in transcript
            prompt = template.replace("{transcript_text}", transcript_text)

            # Call LLM and validate (pass transcript for hallucination prevention during repair)
            result = self._call_and_validate(
                prompt=prompt,
                schema_class=TranscriptIntelligence,
                original_context=transcript_text[:2000],  # First 2000 chars for context
            )

            return result

        except Exception as e:
            raise TranscriptAgentError(f"Transcript analysis failed: {e}") from e

    def _format_transcript_for_llm(self, transcript: RawTranscript) -> str:
        """Format transcript segments for LLM input.

        Args:
            transcript: Raw transcript
        """
        lines = []

        for seg in transcript.segments:
            minutes = int(seg.start // 60)
            seconds = int(seg.start % 60)
            timestamp = f"[{minutes:02d}:{seconds:02d}]"
            line = f"{timestamp} {seg.text}"
            lines.append(line)

        return "\n".join(lines)

    def analyze_with_fallback(
        self, transcript: RawTranscript, use_batch: bool = True
    ) -> TranscriptIntelligence:
        """
        Analyze with automatic batch processing for long transcripts.

        For long transcripts (>3 minutes), splits into chunks and processes
        each chunk separately, then merges results. This preserves all data
        without truncation.

        Args:
            transcript: Raw transcript to analyze
            use_batch: Whether to use batch processing for long transcripts

        Returns:
            TranscriptIntelligence with structured data
        """
        from rich.console import Console

        console = Console()

        # Calculate transcript duration
        duration = transcript.duration if hasattr(transcript, "duration") else 0
        if transcript.segments:
            duration = transcript.segments[-1].end

        # Use batch processing for videos longer than 3 minutes
        if use_batch and duration > 180:
            console.print(
                f"   [dim]   Transcript duration: {duration:.0f}s, using batch processing...[/dim]"
            )
            from src.llm_agents.batch_processor import BatchTranscriptProcessor

            processor = BatchTranscriptProcessor(chunk_duration_seconds=180)
            return processor.process(transcript)

        # For shorter videos, process normally
        try:
            return self.analyze(transcript)
        except Exception as e:
            # Log the error for debugging
            console.print(f"[red]⚠ Transcript agent failed: {e}[/red]")
            import traceback

            console.print(f"[dim]{traceback.format_exc()[:500]}[/dim]")

            # Return minimal valid structure
            full_text = transcript.full_text
            return TranscriptIntelligence(
                content_type="general",
                primary_asset=None,
                analysis_style="mixed",
                classification_confidence=0.5,
                assets_discussed=[],
                price_levels=[],
                signals=[],
                indicators_mentioned=[],
                patterns_identified=[],
                executive_summary=full_text[:500] + "..." if len(full_text) > 500 else full_text,
                key_topics=[],
                market_context="neutral",
                full_cleaned_text=full_text,
                frame_extraction_plan=FrameExtractionPlan(
                    suggested_count=10,
                    key_moments=[
                        FrameExtractionMoment(
                            time=i * 60, importance=0.5, reason="regular coverage"
                        )
                        for i in range(10)
                    ],
                    coverage_interval_seconds=60,
                ),
            )
