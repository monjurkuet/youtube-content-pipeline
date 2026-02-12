"""Data models for the Video Content Pipeline."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class VideoSegment:
    """A single segment of video content with timing."""

    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        """Calculate end time."""
        return self.start + self.duration


@dataclass
class SceneAnalysis:
    """Analysis of a single video scene/frame."""

    scene_id: int
    start_time: float
    end_time: float
    duration: float
    scene_change_score: float
    similarity_to_previous: float | None = None
    analysis: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoAnalysisResult:
    """Complete result of video analysis."""

    video_id: str
    source_type: Literal["youtube", "local", "url"]
    title: str | None
    metadata: dict[str, Any]
    scenes: list[SceneAnalysis]
    visual_entities: dict[str, list[str]]
    audio_transcript: str
    full_analysis: str
    extracted_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "video_id": self.video_id,
            "source_type": self.source_type,
            "title": self.title,
            "metadata": self.metadata,
            "scenes": [
                {
                    "scene_id": s.scene_id,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "duration": s.duration,
                    "scene_change_score": s.scene_change_score,
                    "similarity_to_previous": s.similarity_to_previous,
                    "analysis": s.analysis,
                }
                for s in self.scenes
            ],
            "visual_entities": self.visual_entities,
            "audio_transcript": self.audio_transcript,
            "full_analysis": self.full_analysis,
            "extracted_at": self.extracted_at.isoformat(),
        }


@dataclass
class TranscriptResult:
    """Result of audio transcript extraction."""

    video_id: str
    title: str | None
    segments: list[VideoSegment]
    source: Literal["youtube_api", "youtube_transcript_api", "gemini", "openvino_whisper"]
    language: str
    is_generated: bool
    fetched_at: datetime

    @property
    def full_text(self) -> str:
        """Concatenate all segments into full text."""
        return " ".join([s.text for s in self.segments])

    @property
    def duration(self) -> float:
        """Calculate total duration from segments."""
        if not self.segments:
            return 0.0
        return self.segments[-1].end


@dataclass
class AnalysisConfig:
    """Configuration for video analysis."""

    mode: str = "trading"  # trading, general, text, visual
    max_frames: int = 50
    scene_threshold: float = 0.3
    resolution: str = "1080p"
    include_audio: bool = True
