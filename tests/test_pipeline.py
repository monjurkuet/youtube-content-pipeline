"""Tests for the transcription pipeline."""

from datetime import datetime, timezone

import pytest

from src.core.schemas import ProcessingResult, RawTranscript, TranscriptSegment


class TestSchemas:
    """Test Pydantic schemas."""

    def test_transcript_segment(self):
        """Test TranscriptSegment model."""
        segment = TranscriptSegment(text="Hello world", start=0.0, duration=5.0)
        assert segment.text == "Hello world"
        assert segment.start == 0.0
        assert segment.duration == 5.0
        assert segment.end == 5.0

    def test_raw_transcript(self):
        """Test RawTranscript model."""
        segments = [
            TranscriptSegment(text="Hello", start=0.0, duration=5.0),
            TranscriptSegment(text="World", start=5.0, duration=5.0),
        ]
        transcript = RawTranscript(
            video_id="test123",
            segments=segments,
            source="youtube_api",
            language="en",
        )

        assert transcript.video_id == "test123"
        assert len(transcript.segments) == 2
        assert transcript.full_text == "Hello World"
        assert transcript.duration == 10.0

    def test_processing_result(self):
        """Test ProcessingResult model."""
        result = ProcessingResult(
            video_id="test123",
            source_type="youtube",
            transcript_source="youtube_api",
            segment_count=10,
            duration_seconds=60.0,
            total_text_length=500,
            language="en",
            started_at=datetime.now(timezone.utc),
            duration_seconds_total=5.0,
            saved_to_db=True,
        )

        assert result.video_id == "test123"
        assert result.source_type == "youtube"
        assert result.segment_count == 10


class TestIdentifySourceType:
    """Test source type identification."""

    def test_youtube_watch_url(self):
        """Test YouTube watch URL parsing."""
        from src.transcription.handler import identify_source_type

        source_type, video_id = identify_source_type("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert source_type == "youtube"
        assert video_id == "dQw4w9WgXcQ"

    def test_youtube_short_url(self):
        """Test YouTube short URL parsing."""
        from src.transcription.handler import identify_source_type

        source_type, video_id = identify_source_type("https://youtu.be/dQw4w9WgXcQ")
        assert source_type == "youtube"
        assert video_id == "dQw4w9WgXcQ"

    def test_youtube_video_id_only(self):
        """Test YouTube video ID only."""
        from src.transcription.handler import identify_source_type

        source_type, video_id = identify_source_type("dQw4w9WgXcQ")
        assert source_type == "youtube"
        assert video_id == "dQw4w9WgXcQ"

    def test_invalid_source(self):
        """Test invalid source raises error."""
        from src.transcription.handler import identify_source_type

        with pytest.raises(ValueError, match="Unknown source type"):
            identify_source_type("not-a-valid-source")
