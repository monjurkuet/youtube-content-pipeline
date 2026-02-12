"""Pydantic schemas for structured LLM-driven video analysis."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TradingLevel(BaseModel):
    """A price level identified in the video."""

    price: float = Field(..., description="Numeric price value")
    label: str = Field(..., description="Original text representation (e.g., '$65,200')")
    type: str = Field(..., description="Type of price level (will be normalized)")
    confidence: float = Field(ge=0, le=1)
    timestamp: int | None = Field(None, description="When mentioned in video (seconds)")
    context: str | None = Field(None, description="Surrounding discussion context")
    normalized_type: str | None = Field(None, description="Normalized type after validation")
    normalization_confidence: float | None = Field(None, description="Confidence of normalization")

    @field_validator("price")
    @classmethod
    def clean_price(cls, v):
        """Ensure price is positive."""
        if v <= 0:
            raise ValueError("Price must be positive")
        return v

    @field_validator("type")
    @classmethod
    def normalize_type(cls, v, info):
        """Normalize price level type using adaptive normalizer."""
        from src.core.normalizer import get_normalizer

        context = info.data.get("context", "")
        price = info.data.get("price")

        normalizer = get_normalizer()
        result = normalizer.normalize(v, context, price)

        # Store normalization metadata
        info.data["normalized_type"] = result.normalized_type
        info.data["normalization_confidence"] = result.confidence

        return result.normalized_type


class TradingSignal(BaseModel):
    """A trading signal extracted from the video."""

    asset: str = Field(..., description="Asset symbol (BTC, ETH, etc.)")
    direction: Literal["long", "short", "neutral"]
    entry_price: str | None = None
    target_price: str | None = None
    stop_loss: str | None = None
    timeframe: Literal[
        "scalp", "day_trade", "swing_trade", "position", "long_term", "unspecified"
    ] = "unspecified"
    confidence: float = Field(ge=0, le=1)
    timestamp: int | None = None
    rationale: str | None = None


class FrameExtractionMoment(BaseModel):
    """A suggested moment to extract a frame."""

    time: int = Field(..., description="Timestamp in seconds")
    importance: float = Field(ge=0, le=1, description="How critical this moment is")
    reason: str = Field(..., description="Why this moment matters")


class FrameExtractionPlan(BaseModel):
    """LLM-generated plan for frame extraction."""

    suggested_count: int = Field(ge=5, le=30, description="Recommended number of frames")
    key_moments: list[FrameExtractionMoment]
    coverage_interval_seconds: int = Field(default=180, description="Regular coverage interval")


class FrameAnalysis(BaseModel):
    """Analysis of a single video frame."""

    frame_number: int
    timestamp: int = Field(..., description="Seconds into video")
    keep: bool = Field(..., description="Whether to keep this frame")
    importance_score: float = Field(ge=0, le=1)
    redundancy_group: int | None = Field(default=None, description="Group ID for similar frames")
    reason: str | None = Field(default=None, description="Why frame was kept or rejected")
    content_type: Literal["chart_analysis", "ui_navigation", "speaker", "other"] = "other"
    analysis: dict = Field(default_factory=dict, description="Detailed visual analysis")


class VisualFrameSummary(BaseModel):
    """Summary of frame analysis batch."""

    total_frames_analyzed: int
    frames_selected: int
    redundancy_groups_found: int
    primary_assets_visualized: list[str]


class TranscriptIntelligence(BaseModel):
    """Output from Agent 1: Transcript Intelligence."""

    # Classification
    content_type: Literal[
        "bitcoin_analysis",
        "altcoin_analysis",
        "market_news",
        "trading_education",
        "portfolio_review",
        "general",
    ] = "general"
    primary_asset: str | None = None
    analysis_style: Literal["technical", "fundamental", "news", "mixed"] = "mixed"
    classification_confidence: float = Field(ge=0, le=1, default=0.8)

    # Structured Data
    assets_discussed: list[str] = Field(default_factory=list)
    price_levels: list[TradingLevel] = Field(default_factory=list)
    signals: list[TradingSignal] = Field(default_factory=list)
    indicators_mentioned: list[str] = Field(default_factory=list)
    patterns_identified: list[str] = Field(default_factory=list)

    # Cleaned Transcript
    executive_summary: str = ""
    key_topics: list[str] = Field(default_factory=list)
    market_context: Literal["bullish", "bearish", "neutral", "mixed"] = "neutral"
    full_cleaned_text: str = ""

    # Extraction Plan
    frame_extraction_plan: FrameExtractionPlan


class FrameIntelligence(BaseModel):
    """Output from Agent 2: Frame Intelligence."""

    frame_analyses: list[FrameAnalysis]
    summary: VisualFrameSummary

    @property
    def selected_frames(self) -> list[FrameAnalysis]:
        """Get only the frames marked for keeping."""
        return [f for f in self.frame_analyses if f.keep]


class SynthesisResult(BaseModel):
    """Output from Agent 3: Synthesis."""

    executive_summary: str
    detailed_analysis: str
    key_takeaways: list[str]
    consistency_notes: str | None = Field(
        None, description="Notes on transcript/visual conflicts and resolution"
    )


class ProcessingMetadata(BaseModel):
    """Metadata about the analysis process."""

    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    llm_calls_made: int = 0
    cache_hit: bool = False
    video_downloaded: bool = False
    audio_extracted: bool = False
    transcript_source: Literal["youtube_api", "whisper", "cached"] = "youtube_api"
    errors: list[str] = Field(default_factory=list)


class VideoAnalysisResult(BaseModel):
    """Complete structured analysis result."""

    # Identity
    video_id: str
    source_type: Literal["youtube", "url", "local"]
    source_url: str | None = None
    title: str | None = None
    duration_seconds: float
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)

    # Classification
    content_type: Literal[
        "bitcoin_analysis",
        "altcoin_analysis",
        "market_news",
        "trading_education",
        "portfolio_review",
        "general",
    ] = "general"
    primary_asset: str | None = None

    # Data from Agents
    transcript_intelligence: TranscriptIntelligence
    frame_intelligence: FrameIntelligence
    synthesis: SynthesisResult

    # Flattened Access (for queries)
    assets_discussed: list[str] = Field(default_factory=list)
    price_levels: list[TradingLevel] = Field(default_factory=list)
    signals: list[TradingSignal] = Field(default_factory=list)

    # Metadata
    processing: ProcessingMetadata

    def model_dump_for_mongo(self) -> dict:
        """Convert to dict suitable for MongoDB storage."""
        data = self.model_dump()
        # Convert datetime to ISO string for MongoDB
        data["analyzed_at"] = self.analyzed_at.isoformat()
        data["processing"]["started_at"] = self.processing.started_at.isoformat()
        if self.processing.completed_at:
            data["processing"]["completed_at"] = self.processing.completed_at.isoformat()
        return data

    @classmethod
    def from_agents(
        cls,
        video_id: str,
        source_type: str,
        source_url: str | None,
        title: str | None,
        duration: float,
        transcript_intel: TranscriptIntelligence,
        frame_intel: FrameIntelligence,
        synthesis: SynthesisResult,
        metadata: ProcessingMetadata,
    ) -> "VideoAnalysisResult":
        """Factory method to create result from agent outputs."""
        # Validate source_type is a valid literal value
        valid_sources = ("youtube", "url", "local")
        if source_type not in valid_sources:
            raise ValueError(f"Invalid source_type: {source_type}")

        return cls(
            video_id=video_id,
            source_type=source_type,  # type: ignore[arg-type]
            source_url=source_url,
            title=title,
            duration_seconds=duration,
            content_type=transcript_intel.content_type,
            primary_asset=transcript_intel.primary_asset,
            transcript_intelligence=transcript_intel,
            frame_intelligence=frame_intel,
            synthesis=synthesis,
            assets_discussed=transcript_intel.assets_discussed,
            price_levels=transcript_intel.price_levels,
            signals=transcript_intel.signals,
            processing=metadata,
        )


# Raw transcript models (input)
class TranscriptSegment(BaseModel):
    """A single transcript segment."""

    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


class RawTranscript(BaseModel):
    """Raw transcript before LLM processing."""

    video_id: str
    segments: list[TranscriptSegment]
    source: Literal["youtube_api", "whisper"]
    language: str = "en"

    @property
    def full_text(self) -> str:
        return " ".join([s.text for s in self.segments])

    @property
    def duration(self) -> float:
        if not self.segments:
            return 0.0
        return self.segments[-1].end
