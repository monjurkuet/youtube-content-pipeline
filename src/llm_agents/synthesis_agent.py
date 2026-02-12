"""Agent 3: Synthesis - Combines transcript and visual data into final analysis."""

import json
from pathlib import Path

from src.core.config import get_settings
from src.core.exceptions import SynthesisAgentError
from src.core.schemas import (
    FrameIntelligence,
    SynthesisResult,
    TranscriptIntelligence,
)
from src.llm_agents.base import BaseAgent


class SynthesisAgent(BaseAgent):
    """Combines transcript and visual intelligence into final analysis."""

    @property
    def model(self) -> str:
        return get_settings().llm_synthesis_model

    @property
    def timeout(self) -> int:
        return get_settings().synthesis_timeout

    def _load_prompt_template(self) -> str:
        """Load the prompt template from file."""
        prompt_path = Path(__file__).parent / "prompts" / "synthesis.txt"
        return prompt_path.read_text()

    def synthesize(
        self,
        transcript_intel: TranscriptIntelligence,
        frame_intel: FrameIntelligence,
    ) -> SynthesisResult:
        """
        Combine transcript and visual data into final analysis.

        Args:
            transcript_intel: Structured transcript data
            frame_intel: Selected frame analyses

        Returns:
            SynthesisResult with final analysis
        """
        from rich.console import Console

        console = Console()

        try:
            # Prepare data for prompt
            transcript_data = self._prepare_transcript_data(transcript_intel)
            frame_data = self._prepare_frame_data(frame_intel)

            # Load and fill prompt
            template = self._load_prompt_template()
            # Use replace instead of format to avoid issues with curly braces in data
            transcript_json = json.dumps(transcript_data, indent=2, default=str)
            frame_json = json.dumps(frame_data, indent=2, default=str)
            prompt = template.replace("{transcript_data_json}", transcript_json).replace(
                "{frame_data_json}", frame_json
            )

            # Check prompt size
            console.print(f"   [dim]   Synthesis prompt size: {len(prompt)} chars[/dim]")

            # If prompt is too large, use fallback immediately
            if len(prompt) > 8000:
                console.print(
                    "   [yellow]   Prompt too large ({len(prompt)} chars), using fallback synthesis[/yellow]"
                )
                raise SynthesisAgentError(f"Prompt too large: {len(prompt)} chars")

            # Call LLM and validate with shorter timeout
            result = self._call_and_validate(
                prompt=prompt,
                schema_class=SynthesisResult,
            )

            return result

        except Exception as e:
            raise SynthesisAgentError(f"Synthesis failed: {e}") from e

    def _prepare_transcript_data(self, intel: TranscriptIntelligence) -> dict:
        """Prepare transcript intelligence for prompt."""
        # Limit data to avoid large prompts
        max_levels = 10
        max_signals = 5

        return {
            "content_type": intel.content_type,
            "primary_asset": intel.primary_asset,
            "market_context": intel.market_context,
            "executive_summary": intel.executive_summary,
            "key_topics": intel.key_topics[:10],  # Limit topics
            "assets_discussed": intel.assets_discussed[:5],  # Limit assets
            "price_levels": [
                {
                    "price": level.price,
                    "label": level.label,
                    "type": level.type,
                    "confidence": level.confidence,
                    "timestamp": level.timestamp,
                    "context": level.context[:100] if level.context else None,  # Truncate context
                }
                for level in intel.price_levels[:max_levels]  # Limit price levels
            ],
            "signals": [
                {
                    "asset": signal.asset,
                    "direction": signal.direction,
                    "entry": signal.entry_price,
                    "target": signal.target_price,
                    "stop_loss": signal.stop_loss,
                    "timeframe": signal.timeframe,
                    "confidence": signal.confidence,
                    "rationale": signal.rationale[:100] if signal.rationale else None,  # Truncate
                }
                for signal in intel.signals[:max_signals]  # Limit signals
            ],
            "indicators_mentioned": intel.indicators_mentioned[:10],  # Limit indicators
            "patterns_identified": intel.patterns_identified[:5],  # Limit patterns
            "full_cleaned_text": intel.full_cleaned_text[:1500],  # Truncate for context
        }

    def _prepare_frame_data(self, intel: FrameIntelligence) -> dict:
        """Prepare frame intelligence for prompt."""
        selected = intel.selected_frames

        return {
            "total_frames_analyzed": intel.summary.total_frames_analyzed,
            "frames_selected": intel.summary.frames_selected,
            "primary_assets": intel.summary.primary_assets_visualized,
            "frame_analyses": [
                {
                    "frame_number": frame.frame_number,
                    "timestamp": frame.timestamp,
                    "content_type": frame.content_type,
                    "analysis": frame.analysis,
                }
                for frame in selected[:10]  # Limit to top 10 frames
            ],
        }

    def synthesize_with_fallback(
        self,
        transcript_intel: TranscriptIntelligence,
        frame_intel: FrameIntelligence,
    ) -> SynthesisResult:
        """
        Synthesize with basic fallback if LLM fails.

        Returns a minimal valid SynthesisResult even if LLM fails.
        """
        try:
            return self.synthesize(transcript_intel, frame_intel)
        except Exception:
            # Build basic synthesis from available data
            parts = []
            parts.append("## Executive Summary\n")
            parts.append(transcript_intel.executive_summary)

            parts.append("\n## Key Trading Insights\n")
            if transcript_intel.signals:
                parts.append("### Signals\n")
                for signal in transcript_intel.signals:
                    parts.append(
                        f"- {signal.asset} {signal.direction}: Entry {signal.entry_price}, Target {signal.target_price}"
                    )

            if transcript_intel.price_levels:
                parts.append("\n### Price Levels\n")
                for level in transcript_intel.price_levels:
                    parts.append(f"- {level.type.upper()}: {level.label}")

            parts.append("\n## Visual Analysis\n")
            parts.append(
                f"Analyzed {frame_intel.summary.total_frames_analyzed} frames, selected {frame_intel.summary.frames_selected} key frames."
            )
            if frame_intel.summary.primary_assets_visualized:
                parts.append(
                    f"Assets visualized: {', '.join(frame_intel.summary.primary_assets_visualized)}"
                )

            takeaways = []
            if transcript_intel.market_context != "neutral":
                takeaways.append(f"Overall market sentiment: {transcript_intel.market_context}")
            if transcript_intel.signals:
                takeaways.append(
                    f"Primary trade setup: {transcript_intel.signals[0].asset} {transcript_intel.signals[0].direction}"
                )

            return SynthesisResult(
                executive_summary=transcript_intel.executive_summary,
                detailed_analysis="\n".join(parts),
                key_takeaways=takeaways if takeaways else ["Review full analysis for details"],
                consistency_notes="Generated from structured data (LLM synthesis failed)",
            )
