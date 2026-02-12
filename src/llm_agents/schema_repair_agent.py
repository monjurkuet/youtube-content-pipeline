"""LLM-based schema repair agent for fixing validation errors."""

import json
import re
from difflib import unified_diff
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src.core.config import get_settings
from src.core.exceptions import SchemaValidationError

T = TypeVar("T", bound=BaseModel)


class SchemaRepairAgent:
    """
    Uses LLM to fix schema validation errors as a fallback.
    Standalone class (not inheriting from BaseAgent) to avoid circular imports.

    Features:
    - Semantic validation to prevent hallucinations
    - Detailed diff logging
    - Structured repair with constraints
    """

    def __init__(self):
        from src.llm_agents.factory import get_llm_client

        self.client = get_llm_client()
        self.settings = get_settings()

    @property
    def model(self) -> str:
        """Use same model as main analysis for consistency."""
        return self.settings.llm_transcript_model

    @property
    def timeout(self) -> int:
        return 60  # Repairs should be quick

    def _call_llm(
        self,
        prompt: str,
        system_message: str = None,
        max_tokens: int = 4000,
        temperature: float = 0.3,
    ) -> str:
        """Call LLM for repair."""
        from time import sleep

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        last_error = None
        for attempt in range(self.settings.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=self.timeout,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                last_error = e
                if attempt < self.settings.max_retries - 1:
                    sleep(self.settings.retry_delay * (attempt + 1))
                continue

        raise SchemaValidationError(f"LLM repair call failed: {last_error}")

    def repair(
        self,
        invalid_data: dict,
        validation_errors: list,
        schema_class: type[T],
        original_transcript: str = "",
    ) -> tuple[T, list[str]]:
        """
        Attempt to repair invalid data using LLM.

        Args:
            invalid_data: The data that failed validation
            validation_errors: List of Pydantic validation errors
            schema_class: Target schema class
            original_transcript: Original transcript for context (to prevent hallucinations)

        Returns:
            Tuple of (repaired_instance, repair_log)

        Raises:
            SchemaValidationError: If repair fails
        """
        repair_log = []

        # Build repair prompt with constraints
        prompt = self._build_repair_prompt(
            invalid_data, validation_errors, schema_class, original_transcript
        )

        try:
            # Call LLM for repair
            content = self._call_llm(
                prompt, temperature=self.settings.llm_repair_temperature, max_tokens=4000
            )

            # Parse the repaired JSON
            repaired_data = self._extract_json(content)

            # Validate the repair worked
            try:
                validated = schema_class.model_validate(repaired_data)
            except ValidationError as e:
                raise SchemaValidationError(f"LLM repair output still invalid: {e}")

            # Check for hallucinations (semantic validation)
            hallucination_check = self._check_for_hallucinations(
                invalid_data, repaired_data, validation_errors
            )
            if hallucination_check:
                repair_log.append(f"⚠ Hallucination warning: {hallucination_check}")

            # Generate detailed diff
            diff = self._generate_diff(invalid_data, repaired_data)
            repair_log.append("=== LLM Schema Repair ===")
            repair_log.append(f"Fixed {len(validation_errors)} validation errors")
            repair_log.append("\nDetailed Changes:")
            repair_log.extend(diff)

            return validated, repair_log

        except Exception as e:
            raise SchemaValidationError(f"LLM repair failed: {e}")

    def _build_repair_prompt(
        self,
        data: dict,
        errors: list,
        schema_class: type[T],
        original_transcript: str = "",
    ) -> str:
        """Build a focused repair prompt with strict constraints."""

        error_details = self._format_errors_detailed(errors)
        schema_hints = self._get_schema_hints(schema_class)

        # Context from transcript to prevent hallucinations
        transcript_context = ""
        if original_transcript:
            # Extract relevant portion if too long
            transcript_context = (
                f"\n\nORIGINAL TRANSCRIPT (for context):\n{original_transcript[:2000]}..."
            )

        return f"""You are a JSON repair specialist. Fix the validation errors in the provided data.

=== VALIDATION ERRORS ===
{error_details}

=== SCHEMA CONSTRAINTS ===
{schema_hints}

=== CURRENT (INVALID) DATA ===
```json
{json.dumps(data, indent=2, default=str)}
```{transcript_context}

=== REPAIR INSTRUCTIONS ===
1. Fix ONLY the fields mentioned in validation errors
2. Keep all other values EXACTLY as they are
3. Do not add new fields or remove existing ones
4. Do not invent data - use context from transcript if needed
5. Ensure types match exactly:
   - Integers: 5, 10, 100 (not "5", not 5.5, not null)
   - Strings: "text" (with quotes)
   - Arrays: [] (not {{}})
   - Objects: {{}} (not null)
6. For null/None values: Replace with appropriate default or extract from context

=== ANTI-HALLUCINATION RULES ===
- If a field is null/None, check transcript context or use sensible default
- Do not invent price levels or signals not mentioned in data
- Keep all timestamps and references accurate
- Preserve the original meaning and intent

Return ONLY the corrected JSON, no explanation:"""

    def _format_errors_detailed(self, errors: list) -> str:
        """Format validation errors with detailed information."""
        lines = []
        for i, err in enumerate(errors, 1):
            loc = ".".join(str(x) for x in err.get("loc", []))
            msg = err.get("msg", "")
            err_type = err.get("type", "")
            input_val = err.get("input", "N/A")

            lines.append(f"{i}. Field: {loc}")
            lines.append(f"   Error: {msg}")
            lines.append(f"   Type: {err_type}")
            lines.append(f"   Current Value: {input_val}")
            lines.append("")
        return "\n".join(lines)

    def _get_schema_hints(self, schema_class: type[T]) -> str:
        """Extract relevant schema constraints for the prompt."""
        hints = []

        # Get field information from the schema
        for field_name, field_info in schema_class.model_fields.items():
            annotation = field_info.annotation

            # Handle Literal types (enums)
            if hasattr(annotation, "__origin__") and annotation.__origin__ is not None:
                import typing

                if annotation.__origin__ is typing.Literal:
                    values = annotation.__args__
                    hints.append(f"{field_name}: Must be one of {list(values)}")

            # Handle List types
            elif hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                hints.append(f"{field_name}: Must be an array [item1, item2, ...]")

            # Basic type hints
            elif annotation == int:
                hints.append(f"{field_name}: Must be an integer")
            elif annotation == float:
                hints.append(f"{field_name}: Must be a number")
            elif annotation == str:
                hints.append(f"{field_name}: Must be a string")

        return "\n".join(hints[:20]) if hints else "See current data for structure"

    def _extract_json(self, content: str) -> dict:
        """Extract JSON from LLM response."""
        # Try to find JSON block
        patterns = [
            r"```json\s*(.*?)\s*```",
            r"```\s*(.*?)\s*```",
            r"(\{.*\})",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        # Try parsing entire content
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise SchemaValidationError(f"Could not extract valid JSON from repair: {e}")

    def _check_for_hallucinations(self, original: dict, repaired: dict, errors: list) -> str:
        """
        Check if LLM introduced hallucinations during repair.

        Returns warning message if hallucinations detected, empty string otherwise.
        """
        warnings = []

        # Check for added fields at top level
        original_keys = set(original.keys())
        repaired_keys = set(repaired.keys())
        added_keys = repaired_keys - original_keys
        if added_keys:
            warnings.append(f"Added fields: {added_keys}")

        # Check for removed fields
        removed_keys = original_keys - repaired_keys
        if removed_keys:
            warnings.append(f"Removed fields: {removed_keys}")

        # Check for value changes in fields that weren't broken
        error_locations = set()
        for err in errors:
            loc = err.get("loc", [])
            if loc:
                error_locations.add(loc[0])  # Top-level field

        for key in original_keys & repaired_keys:
            if key not in error_locations:
                orig_val = original[key]
                rep_val = repaired[key]

                # Simple comparison for primitives
                if isinstance(orig_val, (str, int, float, bool)):
                    if orig_val != rep_val:
                        warnings.append(
                            f"Unchanged field '{key}' was modified: {orig_val} -> {rep_val}"
                        )

        if warnings:
            return "; ".join(warnings)
        return ""

    def _generate_diff(self, original: dict, repaired: dict) -> list[str]:
        """Generate a readable diff between original and repaired data."""
        try:
            orig_str = json.dumps(original, indent=2, sort_keys=True, default=str)
            rep_str = json.dumps(repaired, indent=2, sort_keys=True, default=str)

            # Generate unified diff
            diff = list(
                unified_diff(
                    orig_str.splitlines(keepends=True),
                    rep_str.splitlines(keepends=True),
                    fromfile="original",
                    tofile="repaired",
                    lineterm="",
                )
            )

            if diff:
                # Filter to show only changes (remove header lines)
                changes = [line for line in diff if line.startswith("+") or line.startswith("-")]
                return changes[:50]  # Limit diff size

            return ["No structural changes detected"]
        except Exception:
            return ["Could not generate diff"]

    def repair_with_logging(
        self,
        invalid_data: dict,
        validation_errors: list,
        schema_class: type[T],
        console=None,
        original_transcript: str = "",
    ) -> tuple[T, list[str]]:
        """
        Repair with console logging for visibility.

        Args:
            console: Rich console for output (optional)

        Returns:
            Same as repair() method
        """
        from rich.console import Console

        if console is None:
            console = Console()

        console.print("[yellow]   Attempting LLM schema repair...[/yellow]")

        try:
            result, log = self.repair(
                invalid_data, validation_errors, schema_class, original_transcript
            )

            # Print summary
            console.print("[green]   ✓ LLM repair successful[/green]")
            for line in log:
                if line.startswith("+") or line.startswith("-"):
                    color = "green" if line.startswith("+") else "red"
                    console.print(f"   [{color}]{line[:100]}...[/color]")

            return result, log

        except SchemaValidationError as e:
            console.print(f"[red]   ✗ LLM repair failed: {e}[/red]")
            raise
