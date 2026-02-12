"""
Adaptive Price Level Normalizer with SQLite Learning Database.

This module provides intelligent, context-aware normalization of price level types
with self-improving capabilities through SQLite storage and CLI reporting.
"""

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class NormalizationResult:
    """Result of a price level normalization."""

    original_type: str
    normalized_type: str
    confidence: float
    method: str  # 'exact', 'context_inference', 'pattern_match', 'default'
    context: str | None = None
    reasoning: str | None = None


class AdaptivePriceLevelNormalizer:
    """
    Self-improving price level type normalizer with SQLite backend.

    Features:
    - Context-aware classification (not just string matching)
    - Adaptive strictness based on confidence and context
    - SQLite learning database
    - Pattern matching and fuzzy logic
    """

    # Standard types
    VALID_TYPES = ["support", "resistance", "entry", "target", "stop_loss", "other"]

    # Confidence thresholds for adaptive strictness
    HIGH_CONFIDENCE = 0.85
    MEDIUM_CONFIDENCE = 0.60
    LOW_CONFIDENCE = 0.40

    # Context keywords for inference
    CONTEXT_KEYWORDS = {
        "support": ["support", "supporting", "bouncing", "hold", "floor", "bottom", "demand zone"],
        "resistance": [
            "resistance",
            "resisting",
            "ceiling",
            "ceiling",
            "top",
            "supply zone",
            "rejection",
        ],
        "entry": ["entry", "enter", "buy", "long", "get in", "position", "open position"],
        "target": [
            "target",
            "take profit",
            "tp",
            "profit",
            "profit taking",
            "exit",
            "close position",
        ],
        "stop_loss": ["stop", "stop loss", "sl", "risk", "cut loss", "protect", "safety"],
    }

    def __init__(self, db_path: Path | None = None):
        """
        Initialize the normalizer.

        Args:
            db_path: Path to SQLite database. If None, uses default location.
        """
        if db_path is None:
            db_path = Path.home() / ".config" / "video_pipeline" / "normalizer.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()
        self._load_patterns()

    def _init_database(self):
        """Initialize SQLite database with learning tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_level_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_type TEXT NOT NULL,
                    normalized_type TEXT NOT NULL,
                    context_keywords TEXT,  -- JSON array
                    frequency INTEGER DEFAULT 1,
                    confidence_score REAL DEFAULT 0.5,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS normalization_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_type TEXT NOT NULL,
                    normalized_type TEXT NOT NULL,
                    context TEXT,
                    confidence REAL,
                    method TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    video_id TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS context_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    inferred_type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    context_window TEXT,  -- 'before', 'after', 'both'
                    frequency INTEGER DEFAULT 1
                )
            """)

            conn.commit()

    def _load_patterns(self):
        """Load learned patterns from database."""
        self.learned_patterns: dict[str, tuple[str, float]] = {}

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT original_type, normalized_type, confidence_score
                   FROM price_level_patterns
                   WHERE confidence_score > 0.5
                   ORDER BY confidence_score DESC"""
            )

            for row in cursor.fetchall():
                original, normalized, confidence = row
                # Only store if confidence is good enough
                if original not in self.learned_patterns:
                    self.learned_patterns[original] = (normalized, confidence)

    def normalize(
        self,
        price_level_type: str,
        context: str | None = None,
        price: float | None = None,
        video_id: str | None = None,
    ) -> NormalizationResult:
        """
        Adaptively normalize a price level type based on context and learning.

        Args:
            price_level_type: The type string from LLM
            context: Surrounding text/context
            price: The price value (can help with inference)
            video_id: Video identifier for history tracking

        Returns:
            NormalizationResult with normalized type and metadata
        """
        original = price_level_type.strip().lower()

        # Method 1: Exact match
        if original in self.VALID_TYPES:
            return NormalizationResult(
                original_type=price_level_type,
                normalized_type=original,
                confidence=1.0,
                method="exact",
                context=context,
            )

        # Method 2: Learned pattern match
        if original in self.learned_patterns:
            normalized, confidence = self.learned_patterns[original]
            return NormalizationResult(
                original_type=price_level_type,
                normalized_type=normalized,
                confidence=confidence,
                method="pattern_match",
                context=context,
            )

        # Method 3: Context-aware inference (adaptive)
        if context:
            inferred_type, confidence = self._infer_from_context(original, context, price)
            if inferred_type and confidence >= self.LOW_CONFIDENCE:
                # Log for learning
                self._log_normalization(
                    original, inferred_type, context, confidence, "context_inference", video_id
                )
                return NormalizationResult(
                    original_type=price_level_type,
                    normalized_type=inferred_type,
                    confidence=confidence,
                    method="context_inference",
                    context=context,
                    reasoning="Inferred from context keywords",
                )

        # Method 4: Adaptive default based on common patterns
        default_type = self._adaptive_default(original)
        confidence = 0.3  # Low confidence for defaults

        self._log_normalization(original, default_type, context, confidence, "default", video_id)

        return NormalizationResult(
            original_type=price_level_type,
            normalized_type=default_type,
            confidence=confidence,
            method="default",
            context=context,
            reasoning="No confident match, using adaptive default",
        )

    def _infer_from_context(
        self, original: str, context: str, price: float | None
    ) -> tuple[str | None, float]:
        """
        Infer the price level type from context using adaptive analysis.

        This considers:
        - Keyword matching in context
        - Position relative to current price
        - Sentiment analysis (buy/sell signals)
        - Historical patterns
        """
        context_lower = context.lower()
        scores = defaultdict(float)

        # Score each type based on keyword presence
        for level_type, keywords in self.CONTEXT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in context_lower:
                    # Check proximity - closer keywords are more relevant
                    score = 1.0
                    if keyword in original:
                        score *= 1.5  # Bonus if keyword is in the type itself
                    scores[level_type] += score

        # Check for specific patterns
        if re.search(r"\b(buy|long|enter)\s+(?:at|around|near)\s+\$", context_lower):
            scores["entry"] += 2.0

        if re.search(r"\b(sell|short|take\s+profit)\s+(?:at|around)\s+\$", context_lower):
            scores["target"] += 2.0

        if re.search(r"\bstop\s+(?:loss|at)\s+(?:around)?\s*\$", context_lower):
            scores["stop_loss"] += 2.0

        # Price-based inference (if we have current market price)
        if price is not None:
            # This would require knowing current market price
            # For now, skip this enhancement
            pass

        # Get best match
        if scores:
            best_type = max(scores.items(), key=lambda x: x[1])[0]
            best_score = scores[best_type]

            # Calculate confidence based on score magnitude and uniqueness
            total_score = sum(scores.values())
            if total_score > 0:
                confidence = best_score / total_score
                # Boost confidence if clear winner
                other_scores = [scores[t] for t in scores if t != best_type]
                if other_scores and best_score >= 2 * max(other_scores):
                    confidence = min(1.0, confidence * 1.2)

                return best_type, confidence

        return None, 0.0

    def _adaptive_default(self, original: str) -> str:
        """Choose adaptive default based on string characteristics."""
        # Pattern-based defaults
        if any(word in original for word in ["buy", "long", "enter"]):
            return "entry"
        elif any(word in original for word in ["sell", "target", "profit"]):
            return "target"
        elif any(word in original for word in ["stop", "loss", "risk"]):
            return "stop_loss"
        elif any(word in original for word in ["support", "floor", "bottom"]):
            return "support"
        elif any(word in original for word in ["resistance", "ceiling", "top"]):
            return "resistance"

        return "other"

    def _log_normalization(
        self,
        original: str,
        normalized: str,
        context: str | None,
        confidence: float,
        method: str,
        video_id: str | None,
    ):
        """Log normalization to history and update learning patterns."""
        with sqlite3.connect(self.db_path) as conn:
            # Add to history
            conn.execute(
                """INSERT INTO normalization_history 
                   (original_type, normalized_type, context, confidence, method, video_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (original, normalized, context, confidence, method, video_id),
            )

            # Update or insert pattern
            conn.execute(
                """INSERT INTO price_level_patterns 
                   (original_type, normalized_type, confidence_score, frequency)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT DO UPDATE SET
                   frequency = frequency + 1,
                   confidence_score = (confidence_score * frequency + ?) / (frequency + 1),
                   last_seen = CURRENT_TIMESTAMP""",
                (original, normalized, confidence, confidence),
            )

            conn.commit()

    def review_recent_normalizations(
        self, limit: int = 50, min_confidence: float = 0.0, max_confidence: float = 1.0
    ) -> list[dict[str, Any]]:
        """
        Review recent normalizations for quality assurance.

        Args:
            limit: Number of recent entries to review
            min_confidence: Filter by minimum confidence
            max_confidence: Filter by maximum confidence

        Returns:
            List of normalization records
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT * FROM normalization_history
                   WHERE confidence >= ? AND confidence <= ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (min_confidence, max_confidence, limit),
            )

            return [dict(row) for row in cursor.fetchall()]

    def get_statistics(self) -> dict[str, Any]:
        """Get normalization statistics."""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}

            # Total normalizations
            cursor = conn.execute("SELECT COUNT(*) FROM normalization_history")
            stats["total_normalizations"] = cursor.fetchone()[0]

            # By method
            cursor = conn.execute(
                """SELECT method, COUNT(*) as count 
                   FROM normalization_history 
                   GROUP BY method"""
            )
            stats["by_method"] = dict(cursor.fetchall())

            # Average confidence by method
            cursor = conn.execute(
                """SELECT method, AVG(confidence) as avg_confidence
                   FROM normalization_history
                   GROUP BY method"""
            )
            stats["avg_confidence_by_method"] = dict(cursor.fetchall())

            # Learned patterns
            cursor = conn.execute(
                """SELECT COUNT(*) FROM price_level_patterns 
                   WHERE confidence_score > 0.5"""
            )
            stats["learned_patterns"] = cursor.fetchone()[0]

            # Low confidence normalizations (need review)
            cursor = conn.execute(
                """SELECT COUNT(*) FROM normalization_history 
                   WHERE confidence < 0.5"""
            )
            stats["low_confidence_count"] = cursor.fetchone()[0]

            return stats

    def correct_normalization(self, history_id: int, correct_type: str) -> bool:
        """
        Correct a previous normalization to improve learning.

        Args:
            history_id: ID from normalization_history table
            correct_type: The correct normalized type

        Returns:
            True if correction was applied
        """
        with sqlite3.connect(self.db_path) as conn:
            # Get the original record
            cursor = conn.execute(
                "SELECT original_type FROM normalization_history WHERE id = ?", (history_id,)
            )
            row = cursor.fetchone()

            if not row:
                return False

            original_type = row[0]

            # Update pattern with correction (boost confidence)
            conn.execute(
                """INSERT INTO price_level_patterns 
                   (original_type, normalized_type, confidence_score, frequency, success_count)
                   VALUES (?, ?, 0.95, 1, 1)
                   ON CONFLICT(original_type, normalized_type) DO UPDATE SET
                   confidence_score = MIN(0.99, confidence_score + 0.1),
                   success_count = success_count + 1""",
                (original_type, correct_type),
            )

            conn.commit()

            # Reload patterns
            self._load_patterns()

            return True


# Singleton instance for application-wide use
_normalizer_instance: AdaptivePriceLevelNormalizer | None = None


def get_normalizer() -> AdaptivePriceLevelNormalizer:
    """Get or create the global normalizer instance."""
    global _normalizer_instance
    if _normalizer_instance is None:
        _normalizer_instance = AdaptivePriceLevelNormalizer()
    return _normalizer_instance


def normalize_price_level(
    price_level_type: str,
    context: str | None = None,
    price: float | None = None,
    video_id: str | None = None,
) -> str:
    """
    Convenience function to normalize a price level type.

    Returns just the normalized string (not the full result object).
    """
    normalizer = get_normalizer()
    result = normalizer.normalize(price_level_type, context, price, video_id)
    return result.normalized_type
