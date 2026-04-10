"""Tests for the transcription pipeline."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

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
            started_at=datetime.now(UTC),
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

        with pytest.raises(ValueError, match="Could not identify source type"):
            identify_source_type("not-a-valid-source")


class TestTranscriptPipelinePersistence:
    """Test transcript persistence side effects."""

    def test_save_to_database_marks_youtube_video_completed(self):
        """Saving a YouTube transcript should also update video metadata status."""
        from src.core.schemas import TranscriptDocument
        from src.pipeline.transcript import TranscriptPipeline

        raw = RawTranscript(
            video_id="dQw4w9WgXcQ",
            segments=[TranscriptSegment(text="hello", start=0.0, duration=1.0)],
            source="youtube_api",
            language="en",
        )
        doc = TranscriptDocument.from_raw_transcript(raw, source_type="youtube")

        mock_db = AsyncMock()
        mock_db.save_transcript.return_value = "transcript-123"
        mock_db.mark_transcript_completed.return_value = True

        mock_manager = AsyncMock()
        mock_manager.__aenter__.return_value = mock_db
        mock_manager.__aexit__.return_value = None

        with patch("src.database.MongoDBManager", return_value=mock_manager):
            pipeline = TranscriptPipeline()
            doc_id = pipeline._save_to_database(doc)

        assert doc_id == "transcript-123"
        mock_db.save_transcript.assert_awaited_once()
        mock_db.mark_transcript_completed.assert_awaited_once_with(
            "dQw4w9WgXcQ", "transcript-123"
        )
