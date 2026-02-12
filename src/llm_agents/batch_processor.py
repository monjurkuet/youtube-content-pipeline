"""Batch processing for transcript intelligence to handle long videos without data loss."""


from rich.console import Console

from src.core.schemas import (
    FrameExtractionMoment,
    FrameExtractionPlan,
    RawTranscript,
    TradingLevel,
    TradingSignal,
    TranscriptIntelligence,
)
from src.llm_agents.transcript_agent import TranscriptIntelligenceAgent

console = Console()


class BatchTranscriptProcessor:
    """
    Process long transcripts in batches to avoid LLM timeouts
    while preserving all data.
    """

    def __init__(self, chunk_duration_seconds: int = 180):  # 3 minutes per chunk
        self.chunk_duration = chunk_duration_seconds
        self.agent = TranscriptIntelligenceAgent()

    def process(self, transcript: RawTranscript) -> TranscriptIntelligence:
        """
        Process transcript in batches and merge results.

        Args:
            transcript: Full raw transcript

        Returns:
            Merged TranscriptIntelligence from all chunks
        """
        # Split into chunks
        chunks = self._split_into_chunks(transcript)
        console.print(f"   [dim]   Processing transcript in {len(chunks)} chunks...[/dim]")

        # Process each chunk with error tracking
        chunk_results: list[TranscriptIntelligence] = []
        failed_chunks: list[tuple[int, Exception]] = []

        for i, chunk in enumerate(chunks, 1):
            console.print(
                f"   [dim]   Chunk {i}/{len(chunks)} ({len(chunk.segments)} segments)...[/dim]"
            )

            try:
                # Try normal analysis first
                result = self.agent.analyze(chunk)
                chunk_results.append(result)
            except Exception as e:
                # Log failure but try fallback
                console.print(f"   [yellow]⚠ Chunk {i} initial analysis failed: {e}[/yellow]")

                try:
                    # Use fallback which has error recovery
                    result = self.agent.analyze_with_fallback(chunk, use_batch=False)
                    chunk_results.append(result)

                except Exception as e2:
                    # Complete failure - log and continue
                    failed_chunks.append((i, e2))
                    console.print(f"   [red]✗ Chunk {i} failed completely: {e2}[/red]")

        # Report results
        if failed_chunks:
            console.print(f"   [yellow]⚠ {len(failed_chunks)}/{len(chunks)} chunks failed[/yellow]")

        if not chunk_results:
            console.print("[red]✗ All chunks failed, returning empty result[/red]")
            return self._create_empty_result(transcript)

        # Merge all results
        merged = self._merge_results(chunk_results, transcript)
        console.print(
            f"   [dim]   Merged: {len(merged.signals)} signals, {len(merged.price_levels)} levels[/dim]"
        )

        return merged

    def _split_into_chunks(self, transcript: RawTranscript) -> list[RawTranscript]:
        """Split transcript into time-based chunks."""
        if not transcript.segments:
            return []

        chunks = []
        current_segments = []
        chunk_start_time = 0
        chunk_index = 0

        for segment in transcript.segments:
            # If this segment would exceed chunk duration, start new chunk
            if segment.start > chunk_start_time + self.chunk_duration and current_segments:
                # Create chunk (convert segments to dicts for Pydantic)
                chunk = RawTranscript(
                    video_id=f"{transcript.video_id}_chunk_{chunk_index}",
                    segments=[
                        {"text": s.text, "start": s.start, "duration": s.duration}
                        for s in current_segments
                    ],
                    source=transcript.source,
                    language=transcript.language,
                )
                chunks.append(chunk)

                # Start new chunk
                current_segments = [segment]
                chunk_start_time = segment.start
                chunk_index += 1
            else:
                current_segments.append(segment)

        # Add remaining segments as final chunk
        if current_segments:
            chunk = RawTranscript(
                video_id=f"{transcript.video_id}_chunk_{chunk_index}",
                segments=[
                    {"text": s.text, "start": s.start, "duration": s.duration}
                    for s in current_segments
                ],
                source=transcript.source,
                language=transcript.language,
            )
            chunks.append(chunk)

        return chunks

    def _merge_results(
        self,
        chunk_results: list[TranscriptIntelligence],
        original_transcript: RawTranscript,
    ) -> TranscriptIntelligence:
        """Merge results from all chunks into single intelligence."""
        if not chunk_results:
            # Return empty result
            return self._create_empty_result(original_transcript)

        if len(chunk_results) == 1:
            return chunk_results[0]

        # Use first chunk as base for classification
        base = chunk_results[0]

        # Merge all data
        all_signals: list[TradingSignal] = []
        all_price_levels: list[TradingLevel] = []
        all_assets: set = set()
        all_indicators: set = set()
        all_patterns: set = set()
        all_topics: set = set()
        all_moments: list[FrameExtractionMoment] = []

        # Track highest confidence classification
        best_content_type = base.content_type
        best_confidence = base.classification_confidence

        for i, result in enumerate(chunk_results):
            # Update classification if this chunk has higher confidence
            if result.classification_confidence > best_confidence:
                best_content_type = result.content_type
                best_confidence = result.classification_confidence

            # Merge signals (avoid duplicates based on price + direction)
            for signal in result.signals:
                if not self._signal_exists(signal, all_signals):
                    all_signals.append(signal)

            # Merge price levels (avoid duplicates based on price)
            for level in result.price_levels:
                if not self._level_exists(level, all_price_levels):
                    all_price_levels.append(level)

            # Merge sets
            all_assets.update(result.assets_discussed)
            all_indicators.update(result.indicators_mentioned)
            all_patterns.update(result.patterns_identified)
            all_topics.update(result.key_topics)

            # Adjust frame extraction moments for chunk offset
            chunk_offset = i * self.chunk_duration
            for moment in result.frame_extraction_plan.key_moments:
                adjusted_moment = FrameExtractionMoment(
                    time=moment.time + chunk_offset,
                    importance=moment.importance,
                    reason=moment.reason,
                )
                all_moments.append(adjusted_moment)

        # Build merged frame extraction plan
        # Calculate suggested count based on video duration
        video_duration = original_transcript.duration
        suggested_count = min(
            20, max(10, int(video_duration / 60))
        )  # 1 frame per minute, min 10, max 20

        # Deduplicate and sort moments by importance
        all_moments = sorted(all_moments, key=lambda m: m.importance, reverse=True)
        # Keep top moments but ensure coverage
        if len(all_moments) > suggested_count:
            # Take evenly distributed moments
            step = len(all_moments) / suggested_count
            all_moments = [all_moments[int(i * step)] for i in range(suggested_count)]

        merged_plan = FrameExtractionPlan(
            suggested_count=suggested_count,
            key_moments=sorted(all_moments, key=lambda m: m.time),
            coverage_interval_seconds=120,  # Ensure coverage every 2 minutes
        )

        # Build executive summary from all chunks
        summaries = [r.executive_summary for r in chunk_results if r.executive_summary]
        merged_summary = " ".join(summaries[:3])  # Take first 3 summaries
        if len(summaries) > 3:
            merged_summary += f" ... (analysis continues across {len(summaries)} segments)"

        # Merge full cleaned text
        all_text = " ".join([r.full_cleaned_text for r in chunk_results])

        return TranscriptIntelligence(
            content_type=best_content_type,
            primary_asset=base.primary_asset,  # Use from first chunk
            analysis_style=base.analysis_style,
            classification_confidence=best_confidence,
            assets_discussed=sorted(list(all_assets)),
            price_levels=all_price_levels,
            signals=all_signals,
            indicators_mentioned=sorted(list(all_indicators)),
            patterns_identified=sorted(list(all_patterns)),
            executive_summary=merged_summary,
            key_topics=sorted(list(all_topics))[:15],  # Limit topics
            market_context=base.market_context,  # Use from first chunk
            full_cleaned_text=all_text,
            frame_extraction_plan=merged_plan,
        )

    def _signal_exists(self, signal: TradingSignal, existing: list[TradingSignal]) -> bool:
        """Check if similar signal already exists."""
        for existing_signal in existing:
            if (
                existing_signal.asset == signal.asset
                and existing_signal.direction == signal.direction
                and existing_signal.entry_price == signal.entry_price
            ):
                return True
        return False

    def _level_exists(self, level: TradingLevel, existing: list[TradingLevel]) -> bool:
        """Check if similar price level already exists."""
        for existing_level in existing:
            if abs(existing_level.price - level.price) < 100:  # Within $100
                return True
        return False

    def _create_empty_result(self, transcript: RawTranscript) -> TranscriptIntelligence:
        """Create empty result when no chunks processed."""
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
            executive_summary=transcript.full_text[:500] + "..."
            if len(transcript.full_text) > 500
            else transcript.full_text,
            key_topics=[],
            market_context="neutral",
            full_cleaned_text=transcript.full_text,
            frame_extraction_plan=FrameExtractionPlan(
                suggested_count=10,
                key_moments=[
                    FrameExtractionMoment(time=i * 60, importance=0.5, reason="regular coverage")
                    for i in range(10)
                ],
                coverage_interval_seconds=60,
            ),
        )
