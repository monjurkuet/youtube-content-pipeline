"""Base agent class for LLM-driven analysis."""

import json
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from src.core.config import get_settings
from src.core.exceptions import LLMAgentError, SchemaValidationError
from src.llm_agents.factory import get_llm_client
from src.llm_agents.response_utils import (
    JSONRepair,
    ResponseNormalizer,
)
from src.llm_agents.schema_repair_agent import SchemaRepairAgent

T = TypeVar("T", bound=BaseModel)


class BaseAgent(ABC):
    """Base class for all LLM agents."""

    def __init__(self, client: OpenAI | None = None):
        self.client = client or get_llm_client()
        self.settings = get_settings()

    @property
    @abstractmethod
    def model(self) -> str:
        """Model name for this agent."""
        pass

    @property
    @abstractmethod
    def timeout(self) -> int:
        """Timeout in seconds for this agent."""
        pass

    def _call_llm(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 4000,
        temperature: float = 0.3,
    ) -> str:
        """Call LLM with retry logic."""
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

        raise LLMAgentError(
            f"LLM call failed after {self.settings.max_retries} attempts: {last_error}"
        )

    def _parse_json_response(self, content: str) -> tuple[dict, list[str]]:
        """
        Extract and repair JSON from LLM response.

        Returns:
            Tuple of (parsed_data, repair_log)
        """
        # Extract JSON block from markdown or raw text
        json_str = self._extract_json_block(content)

        # Repair and parse JSON
        try:
            data, repairs = JSONRepair.repair_and_validate(json_str)
            return data, repairs
        except json.JSONDecodeError as e:
            # Last resort: try to extract partial data
            partial = JSONRepair.extract_partial(json_str)
            if partial:
                return partial, [f"Partial extraction after error: {e}"]
            raise SchemaValidationError(f"Failed to parse JSON: {e}\nContent: {content[:500]}")

    def _extract_json_block(self, content: str) -> str:
        """Extract JSON string from markdown code blocks or raw text."""
        # Look for ```json ... ```
        match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            return match.group(1)

        # Look for ``` ... ```
        match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            return match.group(1)

        # Look for { ... }
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return match.group(0)

        # Return as-is if no markers found
        return content

    def _validate_response(
        self,
        data: dict,
        schema_class: type[T],
        original_context: str = "",
        use_llm_repair: bool = True,
    ) -> tuple[T, list[str]]:
        """
        Validate parsed JSON against Pydantic schema with automatic normalization.

        Three-phase validation:
        1. Programmatic normalization (enums, types)
        2. Programmatic error fixes (defaults, fuzzy matching)
        3. LLM repair (fallback for complex errors)

        Args:
            data: Parsed JSON data
            schema_class: Target Pydantic schema
            original_context: Original transcript/text for hallucination prevention
            use_llm_repair: Whether to use LLM repair as fallback

        Returns:
            Tuple of (validated_instance, validation_log)
        """
        from rich.console import Console

        console = Console()
        validation_log = []

        # Phase 1: Programmatic normalization
        data, norm_changes = ResponseNormalizer.normalize(data)
        if norm_changes:
            validation_log.extend(["=== Phase 1: Normalization ==="] + norm_changes)

        try:
            validated = schema_class.model_validate(data)
            return validated, validation_log
        except ValidationError as e:
            # Phase 2: Programmatic error fixes
            data, fix_changes = self._fix_validation_errors(data, e, schema_class)
            if fix_changes:
                validation_log.extend(["=== Phase 2: Programmatic Fixes ==="] + fix_changes)

            try:
                validated = schema_class.model_validate(data)
                return validated, validation_log
            except ValidationError as e2:
                # Phase 3: LLM repair (fallback)
                if use_llm_repair and self.settings.enable_llm_repair:
                    try:
                        repair_agent = SchemaRepairAgent()
                        validated, repair_log = repair_agent.repair_with_logging(
                            data,
                            e2.errors(),
                            schema_class,
                            console=console,
                            original_transcript=original_context,
                        )
                        validation_log.extend(repair_log)
                        return validated, validation_log
                    except SchemaValidationError:
                        # LLM repair also failed
                        pass

                # All repair attempts failed
                raise SchemaValidationError(
                    f"Schema validation failed after all fixes:\n"
                    f"Programmatic normalizations: {len(norm_changes)}\n"
                    f"Programmatic fixes: {len(fix_changes)}\n"
                    f"LLM repair attempted: {use_llm_repair and self.settings.enable_llm_repair}\n"
                    f"Remaining errors: {e2}"
                )

    def _fix_validation_errors(
        self, data: dict, error: ValidationError, schema_class: type[T]
    ) -> tuple[dict, list[str]]:
        """
        Attempt to fix specific validation errors.

        Returns:
            Tuple of (fixed_data, fix_log)
        """
        fixes = []

        for err in error.errors():
            loc = err.get("loc", [])
            msg = err.get("msg", "")
            err_type = err.get("type", "")

            # Navigate to the problematic field
            current = data
            for key in loc[:-1]:
                if isinstance(current, dict) and key in current or isinstance(current, list) and isinstance(key, int) and key < len(current):
                    current = current[key]
                else:
                    break

            if not loc:
                continue

            field = loc[-1]

            # Fix enum errors
            if err_type == "enum":
                if isinstance(current, dict) and field in current:
                    old_val = current[field]
                    if isinstance(old_val, str):
                        # Try fuzzy matching
                        valid_values = self._get_enum_values(schema_class, loc)
                        if valid_values:
                            canonical = self._fuzzy_match_enum(old_val, valid_values)
                            if canonical:
                                current[field] = canonical
                                fixes.append(
                                    f"{' -> '.join(str(l) for l in loc)}: '{old_val}' -> '{canonical}'"
                                )

            # Fix missing required fields with defaults
            elif err_type == "missing":
                if isinstance(current, dict):
                    default_value = self._get_default_for_field(schema_class, loc)
                    if default_value is not None:
                        current[field] = default_value
                        fixes.append(
                            f"{' -> '.join(str(l) for l in loc)}: added default '{default_value}'"
                        )

        return data, fixes

    def _get_enum_values(self, schema_class: type[T], loc: tuple) -> list[str]:
        """Get valid enum values for a field from schema."""
        try:
            # Navigate to the field in the schema
            field_info = schema_class.model_fields
            for key in loc[:-1]:
                if key in field_info:
                    annotation = field_info[key].annotation
                    # Handle list types
                    if hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                        if annotation.__args__:
                            annotation = annotation.__args__[0]
                    field_info = getattr(annotation, "model_fields", {})

            # Get the final field
            final_field = loc[-1] if loc else None
            if final_field and final_field in field_info:
                # Extract enum values from Literal type
                import typing

                annotation = field_info[final_field].annotation
                if hasattr(annotation, "__origin__"):
                    if annotation.__origin__ is typing.Literal:
                        return list(annotation.__args__)
        except Exception:
            pass
        return []

    def _fuzzy_match_enum(self, value: str, valid_values: list[str]) -> str | None:
        """Fuzzy match a value to valid enum values."""
        value_lower = value.lower().strip()

        # Exact match
        if value_lower in [v.lower() for v in valid_values]:
            return next(v for v in valid_values if v.lower() == value_lower)

        # Partial match
        for valid in valid_values:
            if value_lower in valid.lower() or valid.lower() in value_lower:
                return valid

        return None

    def _get_default_for_field(self, schema_class: type[T], loc: tuple) -> Any:
        """Get default value for a field from schema."""
        try:
            field_info = schema_class.model_fields
            for key in loc[:-1]:
                if key in field_info:
                    annotation = field_info[key].annotation
                    if hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                        if annotation.__args__:
                            annotation = annotation.__args__[0]
                    field_info = getattr(annotation, "model_fields", {})

            final_field = loc[-1] if loc else None
            if final_field and final_field in field_info:
                default = field_info[final_field].default
                if default is not None:
                    return default
                # Check for Literal defaults
                import typing

                annotation = field_info[final_field].annotation
                if hasattr(annotation, "__origin__") and annotation.__origin__ is typing.Literal:
                    return annotation.__args__[-1]  # Return last option (often "unspecified")
        except Exception:
            pass
        return None

    def _call_and_validate(
        self,
        prompt: str,
        schema_class: type[T],
        system_message: str | None = None,
        original_context: str = "",
    ) -> T:
        """Call LLM and validate response against schema.

        Args:
            prompt: The prompt sent to LLM
            schema_class: Target Pydantic schema
            system_message: Optional system message
            original_context: Original transcript/text for hallucination prevention during repair
        """
        content = self._call_llm(prompt, system_message)
        data, repairs = self._parse_json_response(content)

        # Log repairs if any
        if repairs:
            import logging

            logging.getLogger(__name__).debug(f"JSON repairs: {repairs}")

        validated, norm_changes = self._validate_response(
            data, schema_class, original_context=original_context
        )

        # Log normalizations if any
        if norm_changes:
            import logging

            logging.getLogger(__name__).debug(f"Data normalizations: {norm_changes}")

        return validated
