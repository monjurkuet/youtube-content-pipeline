"""
LLM Response Processing Utilities.

This module handles JSON repair and data normalization for LLM outputs.
It is SEPARATE from src/core/normalizer.py which focuses on price level type classification.

Usage:
    - JSONRepair: Fixes malformed JSON from LLM outputs
    - ResponseNormalizer: Normalizes enum values and coerces types
    - repair_and_normalize_response(): Complete pipeline
"""

import json
import re
from typing import Any


class JSONRepair:
    """Repair common JSON errors from LLM outputs."""

    @staticmethod
    def repair(json_str: str) -> str:
        """Apply all repair strategies in sequence."""
        original = json_str

        # Step 1: Clean up whitespace and newlines in strings
        json_str = JSONRepair._escape_newlines_in_strings(json_str)

        # Step 2: Fix trailing commas
        json_str = JSONRepair._fix_trailing_commas(json_str)

        # Step 3: Fix missing commas between objects/arrays
        json_str = JSONRepair._fix_missing_commas(json_str)

        # Step 4: Normalize quotes
        json_str = JSONRepair._normalize_quotes(json_str)

        # Step 5: Fix unclosed strings (aggressive)
        json_str = JSONRepair._fix_unclosed_strings(json_str)

        return json_str

    @staticmethod
    def _escape_newlines_in_strings(json_str: str) -> str:
        """Escape newlines within JSON string values."""
        result = []
        in_string = False
        escape_next = False

        for i, char in enumerate(json_str):
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == "\\" and in_string:
                result.append(char)
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                result.append(char)
            elif char in "\n\r\t" and in_string:
                # Replace with escaped version
                if char == "\n":
                    result.append("\\n")
                elif char == "\r":
                    result.append("\\r")
                elif char == "\t":
                    result.append("\\t")
            else:
                result.append(char)

        return "".join(result)

    @staticmethod
    def _fix_trailing_commas(json_str: str) -> str:
        """Remove trailing commas before } or ]."""
        # Remove commas followed by closing brackets
        json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
        return json_str

    @staticmethod
    def _fix_missing_commas(json_str: str) -> str:
        """Add missing commas between array elements and object properties."""
        # Fix between object properties: } { -> }, {
        json_str = re.sub(r"(}\s*)(?={)", r"\1,", json_str)

        # Fix between array elements: ] [ -> ], [
        json_str = re.sub(r"(]\s*)(?=\[)", r"\1,", json_str)

        # Fix between string and object: "..." { -> "...", {
        json_str = re.sub(r'("\s*)(?={)', r"\1,", json_str)

        # Fix between literal and string: true " -> true, "
        json_str = re.sub(r'(true|false|null|\d)\s*(?=")', r"\1,", json_str)

        return json_str

    @staticmethod
    def _normalize_quotes(json_str: str) -> str:
        """Normalize smart quotes and other quote variants."""
        # Replace smart quotes with regular quotes
        json_str = json_str.replace('"', '"').replace('"', '"')
        json_str = json_str.replace(""", "'").replace(""", "'")
        return json_str

    @staticmethod
    def _fix_unclosed_strings(json_str: str) -> str:
        """Attempt to fix unclosed strings by adding closing quote."""
        # This is a best-effort fix - count quotes and try to balance
        # Only apply if the string is clearly broken
        if json_str.count('"') % 2 != 0:
            # Odd number of quotes - try to find where to close
            # Look for common patterns that indicate end of string
            patterns = [
                r'("[^"]*)(?=\s*[,}\]])',  # Quote followed by comma, closing brace, or bracket
            ]
            for pattern in patterns:
                matches = list(re.finditer(pattern, json_str))
                if matches:
                    # Add closing quote before the delimiter
                    last_match = matches[-1]
                    if not json_str[last_match.end() :].startswith('"'):
                        json_str = json_str[: last_match.end()] + '"' + json_str[last_match.end() :]
                        break
        return json_str

    @staticmethod
    def extract_partial(json_str: str) -> dict[str, Any]:
        """Extract valid partial JSON data when full parsing fails."""
        decoder = json.JSONDecoder()
        results = {}

        # Try to extract top-level object
        try:
            obj, idx = decoder.raw_decode(json_str)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        # Try to extract individual fields using regex
        # Look for "key": value patterns
        field_pattern = r'"([^"]+)"\s*:\s*({|\[|"[^"]*"|\d+(\.\d+)?|true|false|null)'
        matches = re.finditer(field_pattern, json_str, re.DOTALL)

        for match in matches:
            key = match.group(1)
            value_str = match.group(0).split(":", 1)[1].strip()

            try:
                value, _ = decoder.raw_decode(value_str)
                results[key] = value
            except json.JSONDecodeError:
                # Try to extract as string
                try:
                    if value_str.startswith('"') and value_str.endswith('"'):
                        results[key] = value_str[1:-1]
                    elif value_str.startswith("["):
                        # Try to parse array
                        results[key] = JSONRepair._extract_array_elements(value_str)
                    elif value_str.startswith("{"):
                        # Try to parse nested object
                        results[key] = JSONRepair.extract_partial(value_str)
                except Exception:
                    pass

        return results

    @staticmethod
    def _extract_array_elements(array_str: str) -> list[Any]:
        """Extract elements from a JSON array string."""
        elements = []
        decoder = json.JSONDecoder()

        # Remove outer brackets
        content = array_str.strip()
        if content.startswith("["):
            content = content[1:]
        if content.endswith("]"):
            content = content[:-1]

        idx = 0
        while idx < len(content):
            try:
                # Skip whitespace and commas
                while idx < len(content) and content[idx] in " \t\n\r,":
                    idx += 1
                if idx >= len(content):
                    break

                # Try to decode next element
                element, end_idx = decoder.raw_decode(content, idx)
                elements.append(element)
                idx += end_idx
            except json.JSONDecodeError:
                # Move forward and try again
                idx += 1

        return elements

    @staticmethod
    def is_valid_json(json_str: str) -> bool:
        """Check if string is valid JSON."""
        try:
            json.loads(json_str)
            return True
        except json.JSONDecodeError:
            return False

    @staticmethod
    def repair_and_validate(json_str: str) -> tuple[dict[str, Any], list[str]]:
        """Repair JSON and return result with list of repairs made."""
        repairs = []

        # Try original first
        try:
            return json.loads(json_str), []
        except json.JSONDecodeError as e:
            repairs.append(f"Original JSON invalid: {e}")

        # Apply repairs
        repaired = JSONRepair.repair(json_str)

        try:
            result = json.loads(repaired)
            repairs.append("Successfully repaired JSON")
            return result, repairs
        except json.JSONDecodeError as e:
            repairs.append(f"Repair failed: {e}")

            # Try partial extraction
            partial = JSONRepair.extract_partial(repaired)
            if partial:
                repairs.append(f"Extracted {len(partial)} fields partially")
                return partial, repairs

            raise


class ResponseNormalizer:
    """
    Normalize LLM response data before Pydantic validation.

    This is different from src/core/normalizer.py which handles
    price level type classification with ML learning.

    This class handles:
    - Enum value normalization (e.g., "swing" -> "swing_trade")
    - Type coercion (e.g., price strings to float)
    - String cleaning
    """

    ENUM_MAPPINGS = {
        "timeframe": {
            # Variations -> canonical form
            "swing": "swing_trade",
            "swing trade": "swing_trade",
            "swingtrade": "swing_trade",
            "day": "day_trade",
            "daytrade": "day_trade",
            "day trade": "day_trade",
            "scalp": "scalp",
            "scalping": "scalp",
            "position": "position",
            "long": "long_term",
            "long term": "long_term",
            "long-term": "long_term",
            "longterm": "long_term",
            "short": "short_term",
            "short term": "short_term",
            "short-term": "short_term",
            "shortterm": "short_term",
            "hourly": "day_trade",
            "4h": "swing_trade",
            "daily": "swing_trade",
            "weekly": "position",
            "monthly": "long_term",
        },
        "direction": {
            "long": "long",
            "buy": "long",
            "bullish": "long",
            "up": "long",
            "short": "short",
            "sell": "short",
            "bearish": "short",
            "down": "short",
            "neutral": "neutral",
            "flat": "neutral",
            "sideways": "neutral",
        },
        "type": {
            "support": "support",
            "resistance": "resistance",
            "entry": "entry",
            "entry point": "entry",
            "entry zone": "entry",
            "target": "target",
            "take profit": "target",
            "tp": "target",
            "stop loss": "stop_loss",
            "stop-loss": "stop_loss",
            "stoploss": "stop_loss",
            "sl": "stop_loss",
            "other": "other",
        },
        "market_context": {
            "bullish": "bullish",
            "bearish": "bearish",
            "neutral": "neutral",
            "mixed": "mixed",
            "sideways": "neutral",
            "ranging": "neutral",
            "uptrend": "bullish",
            "downtrend": "bearish",
        },
        "analysis_style": {
            "technical": "technical",
            "fundamental": "fundamental",
            "news": "news",
            "mixed": "mixed",
            "sentiment": "mixed",
        },
    }

    @classmethod
    def normalize(cls, data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Normalize data and return with list of changes."""
        changes = []
        data = cls._deep_copy(data)

        # Normalize enums
        data, enum_changes = cls._normalize_enums(data)
        changes.extend(enum_changes)

        # Coerce types
        data, type_changes = cls._coerce_types(data)
        changes.extend(type_changes)

        # Clean strings
        data, clean_changes = cls._clean_strings(data)
        changes.extend(clean_changes)

        return data, changes

    @classmethod
    def _deep_copy(cls, data: Any) -> Any:
        """Create a deep copy of data."""
        if isinstance(data, dict):
            return {k: cls._deep_copy(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls._deep_copy(item) for item in data]
        return data

    @classmethod
    def _normalize_enums(
        cls, data: dict[str, Any], path: str = ""
    ) -> tuple[dict[str, Any], list[str]]:
        """Normalize enum fields to valid values."""
        changes = []

        if not isinstance(data, dict):
            return data, changes

        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key

            if isinstance(value, str):
                # Check if this field has enum mappings
                value_lower = value.lower().strip()

                for enum_field, mappings in cls.ENUM_MAPPINGS.items():
                    if key == enum_field or (enum_field in key.lower()):
                        if value_lower in mappings:
                            canonical = mappings[value_lower]
                            if value != canonical:
                                changes.append(f"{current_path}: '{value}' -> '{canonical}'")
                                data[key] = canonical
                            break

            # Recurse into nested structures
            if isinstance(value, dict):
                data[key], sub_changes = cls._normalize_enums(value, current_path)
                changes.extend(sub_changes)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        data[key][i], sub_changes = cls._normalize_enums(
                            item, f"{current_path}[{i}]"
                        )
                        changes.extend(sub_changes)

        return data, changes

    @classmethod
    def _coerce_types(
        cls, data: dict[str, Any], path: str = ""
    ) -> tuple[dict[str, Any], list[str]]:
        """Coerce types to expected formats."""
        changes = []

        if not isinstance(data, dict):
            return data, changes

        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key

            # Coerce price to float
            if key == "price" and isinstance(value, str):
                try:
                    # Remove currency symbols and commas
                    cleaned = value.replace("$", "").replace(",", "").strip()
                    data[key] = float(cleaned)
                    changes.append(f"{current_path}: '{value}' -> {data[key]}")
                except (ValueError, TypeError):
                    pass

            # Coerce confidence to float
            elif key == "confidence":
                if isinstance(value, str):
                    try:
                        data[key] = float(value)
                        changes.append(f"{current_path}: '{value}' -> {data[key]}")
                    except (ValueError, TypeError):
                        pass
                elif isinstance(value, int):
                    data[key] = float(value)

            # Coerce timestamp to int
            elif key == "timestamp" and isinstance(value, str):
                try:
                    data[key] = int(float(value))
                    changes.append(f"{current_path}: '{value}' -> {data[key]}")
                except (ValueError, TypeError):
                    pass

            # Coerce suggested_count to int
            elif key == "suggested_count" or key == "coverage_interval_seconds":
                if isinstance(value, str):
                    try:
                        data[key] = int(value)
                        changes.append(f"{current_path}: '{value}' -> {data[key]}")
                    except (ValueError, TypeError):
                        pass
                elif isinstance(value, float):
                    data[key] = int(value)

            # Ensure price fields are strings (target_price, entry_price, stop_loss)
            elif key in ["target_price", "entry_price", "stop_loss"]:
                if isinstance(value, (int, float)):
                    # Convert number to formatted string
                    if value == int(value):
                        data[key] = f"${int(value):,}"
                    else:
                        data[key] = f"${value:,.2f}"
                    changes.append(f"{current_path}: {value} -> '{data[key]}'")
                elif isinstance(value, str):
                    # Ensure it has $ prefix if it's a price
                    if value and not value.startswith("$") and not value.startswith("N"):
                        # Check if it's a numeric string
                        try:
                            float(value.replace(",", ""))
                            data[key] = f"${value}"
                            changes.append(f"{current_path}: '{value}' -> '{data[key]}'")
                        except (ValueError, TypeError):
                            pass

            # Note: Recursion happens AFTER field processing, not in elif
            # This ensures we always process nested structures

            # Recurse into nested structures
            if isinstance(value, dict):
                data[key], sub_changes = cls._coerce_types(value, current_path)
                changes.extend(sub_changes)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        data[key][i], sub_changes = cls._coerce_types(item, f"{current_path}[{i}]")
                        changes.extend(sub_changes)

        return data, changes

    @classmethod
    def _clean_strings(
        cls, data: dict[str, Any], path: str = ""
    ) -> tuple[dict[str, Any], list[str]]:
        """Clean string values (strip whitespace, etc.)."""
        changes = []

        if not isinstance(data, dict):
            return data, changes

        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key

            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned != value:
                    data[key] = cleaned
                    changes.append(f"{current_path}: trimmed whitespace")

            # Recurse into nested structures
            if isinstance(value, dict):
                data[key], sub_changes = cls._clean_strings(value, current_path)
                changes.extend(sub_changes)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        data[key][i], sub_changes = cls._clean_strings(item, f"{current_path}[{i}]")
                        changes.extend(sub_changes)

        return data, changes


def repair_and_normalize_response(json_str: str) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Complete pipeline: repair JSON then normalize response data.

    This is the main entry point for processing LLM responses.
    It handles both JSON syntax repair and data normalization.

    Returns:
        Tuple of (data, json_repairs, normalization_changes)
    """
    # Step 1: Repair JSON syntax
    data, json_repairs = JSONRepair.repair_and_validate(json_str)

    # Step 2: Normalize response data (enums, types, etc.)
    # Note: This is separate from price level normalization in src/core/normalizer.py
    data, norm_changes = ResponseNormalizer.normalize(data)

    return data, json_repairs, norm_changes
