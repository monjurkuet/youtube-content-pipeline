"""Agent 2: Frame Intelligence - Analyzes and selects video frames."""

import base64
import json
from pathlib import Path

from src.core.config import get_settings
from src.core.exceptions import FrameAgentBatchError
from src.core.schemas import FrameAnalysis, FrameIntelligence, VisualFrameSummary
from src.llm_agents.base import BaseAgent


class FrameIntelligenceAgent(BaseAgent):
    """Analyzes video frames and selects the most informative ones."""

    @property
    def model(self) -> str:
        return get_settings().llm_frame_model

    @property
    def timeout(self) -> int:
        return get_settings().frame_timeout

    def _load_prompt_template(self) -> str:
        """Load the prompt template from file."""
        prompt_path = Path(__file__).parent / "prompts" / "frame_batch_analysis.txt"
        return prompt_path.read_text()

    def analyze_batch(self, frames: list[Path]) -> FrameIntelligence:
        """
        Analyze frames in batch (preferred method).

        Args:
            frames: List of frame file paths

        Returns:
            FrameIntelligence with analyses

        Raises:
            FrameAgentBatchError: If batch analysis fails (can retry individually)
        """
        if not frames:
            return FrameIntelligence(
                frame_analyses=[],
                summary=VisualFrameSummary(
                    total_frames_analyzed=0,
                    frames_selected=0,
                    redundancy_groups_found=0,
                    primary_assets_visualized=[],
                ),
            )

        try:
            # Build frame batch data
            frame_batch = self._build_frame_batch(frames)

            # Load and fill prompt
            template = self._load_prompt_template()
            # Use replace instead of format to avoid issues with curly braces in data
            frame_batch_json = json.dumps(frame_batch, indent=2)
            prompt = template.replace("{frame_batch_json}", frame_batch_json)

            # Call LLM and validate
            result = self._call_and_validate(
                prompt=prompt,
                schema_class=FrameIntelligence,
            )

            return result

        except Exception as e:
            raise FrameAgentBatchError(f"Batch frame analysis failed: {e}") from e

    def analyze_individually(self, frames: list[Path]) -> FrameIntelligence:
        """
        Analyze frames one by one (fallback method).

        Args:
            frames: List of frame file paths

        Returns:
            FrameIntelligence with analyses
        """
        from rich.console import Console

        console = Console()

        analyses = []
        console.print(f"   Analyzing {len(frames)} frames individually...")

        for i, frame_path in enumerate(frames, 1):
            try:
                console.print(f"   Frame {i}/{len(frames)}...", end=" ")
                analysis = self._analyze_single_frame(frame_path, i)
                analyses.append(analysis)
                console.print("[green]✓[/green]")
            except Exception as e:
                console.print(f"[red]✗ {str(e)[:30]}[/red]")
                # Add error frame
                analyses.append(
                    FrameAnalysis(
                        frame_number=i,
                        timestamp=self._extract_timestamp(frame_path),
                        keep=False,
                        importance_score=0.0,
                        redundancy_group=None,
                        reason=f"Analysis failed: {e}",
                    )
                )

        # Simple selection: keep top 50% by importance
        sorted_analyses = sorted(analyses, key=lambda x: x.importance_score, reverse=True)
        keep_count = max(1, len(sorted_analyses) // 2)

        for i, analysis in enumerate(sorted_analyses):
            if i < keep_count:
                analysis.keep = True

        # Identify assets (simplified)
        assets = set()
        for analysis in analyses:
            if analysis.keep and "asset" in analysis.analysis:
                assets.add(analysis.analysis["asset"].split("/")[0])

        return FrameIntelligence(
            frame_analyses=analyses,
            summary=VisualFrameSummary(
                total_frames_analyzed=len(frames),
                frames_selected=keep_count,
                redundancy_groups_found=0,
                primary_assets_visualized=list(assets),
            ),
        )

    def _build_frame_batch(self, frames: list[Path]) -> list[dict]:
        """Build JSON-serializable frame batch for LLM."""
        batch = []
        for i, frame_path in enumerate(frames, 1):
            timestamp = self._extract_timestamp(frame_path)
            batch.append(
                {
                    "frame_number": i,
                    "timestamp_seconds": timestamp,
                    "timestamp_formatted": f"{timestamp // 60}:{timestamp % 60:02d}",
                }
            )
        return batch

    def _extract_timestamp(self, frame_path: Path) -> int:
        """Extract timestamp from frame filename."""
        # Expected format: frame_0001_at_0045s.jpg
        try:
            stem = frame_path.stem
            parts = stem.split("_")
            if len(parts) >= 4 and parts[-1].endswith("s"):
                return int(parts[-1][:-1])
        except (ValueError, IndexError):
            pass
        return 0

    def _analyze_single_frame(self, frame_path: Path, frame_number: int) -> FrameAnalysis:
        """Analyze a single frame with vision model."""
        # Read and encode image
        with open(frame_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        timestamp = self._extract_timestamp(frame_path)

        # Simple prompt for single frame
        prompt = f"""Analyze this trading video frame at timestamp {timestamp // 60}:{timestamp % 60:02d}.

Describe what you see: charts, indicators, prices, patterns, sentiment.
Rate importance 0-1 and whether to keep this frame (true/false).

Output JSON:
{{
  "importance_score": 0.85,
  "keep": true,
  "content_type": "chart_analysis",
  "analysis": {{
    "asset": "BTC/USD",
    "timeframe": "4H",
    "current_price": "$67,450",
    "visible_indicators": ["EMA", "Volume"],
    "patterns": ["ascending_triangle"],
    "sentiment": "bullish"
  }}
}}"""

        # Call vision model
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}",
                            },
                        },
                    ],
                },
            ],
            max_tokens=1000,
            temperature=0.3,
            timeout=self.timeout,
        )

        content = response.choices[0].message.content or "{}"
        data, _ = self._parse_json_response(content)

        return FrameAnalysis(
            frame_number=frame_number,
            timestamp=timestamp,
            keep=data.get("keep", True),
            importance_score=data.get("importance_score", 0.5),
            redundancy_group=None,
            reason=None,
            content_type=data.get("content_type", "other"),
            analysis=data.get("analysis", {}),
        )

    def analyze_with_fallback(self, frames: list[Path]) -> FrameIntelligence:
        """
        Analyze frames with automatic fallback to individual analysis.

        Args:
            frames: List of frame file paths

        Returns:
            FrameIntelligence with analyses
        """
        settings = get_settings()

        # Try batch first
        try:
            return self.analyze_batch(frames)
        except FrameAgentBatchError as e:
            if settings.pipeline_retry_frames_individually:
                from rich.console import Console

                console = Console()
                console.print(f"[yellow]⚠ Batch analysis failed: {e}[/yellow]")
                console.print("[yellow]  Retrying with individual frame analysis...[/yellow]")
                return self.analyze_individually(frames)
            else:
                raise
