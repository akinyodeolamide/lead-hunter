"""Security utilities for prompt injection protection and input sanitization."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from lead_hunter.exceptions import PromptInjectionError


class Sanitizer:
    """Sanitizes external content to prevent prompt injection attacks."""

    DEFAULT_PATTERNS = [
        "ignore previous instructions",
        "ignore all previous instructions",
        "system prompt",
        "you are now",
        "you are a",
        "you have been",
        "new instructions",
        "override instructions",
        "disregard",
        "forget everything",
    ]

    def __init__(self, injection_patterns: list[str] | None = None, max_control_chars_ratio: float = 0.05) -> None:
        self.injection_patterns = [p.lower() for p in (injection_patterns or self.DEFAULT_PATTERNS)]
        self.max_control_chars_ratio = max_control_chars_ratio

    def sanitize(self, text: str) -> str:
        """Sanitize a string by normalizing unicode and stripping dangerous content.

        Returns the sanitized text.
        Raises PromptInjectionError if dangerous content is detected.
        """
        if not isinstance(text, str):
            text = str(text)

        # Normalize unicode to prevent homoglyph attacks
        text = unicodedata.normalize("NFKC", text)

        # Check for prompt injection patterns
        lower_text = text.lower()
        for pattern in self.injection_patterns:
            if pattern in lower_text:
                raise PromptInjectionError(
                    f"Prompt injection pattern detected: {pattern!r}",
                    details={"pattern": pattern, "text_preview": text[:200]},
                )

        # Check for delimiter-breaking sequences
        if self._has_delimiter_breaking(text):
            raise PromptInjectionError(
                "Delimiter-breaking sequence detected in external content",
                details={"text_preview": text[:200]},
            )

        # Check for excessive control characters
        if self._has_excessive_control_chars(text):
            raise PromptInjectionError(
                "Excessive control characters detected in external content",
                details={"text_preview": text[:200]},
            )

        # Escape or strip control characters
        text = self._strip_control_chars(text)

        return text

    def _has_delimiter_breaking(self, text: str) -> bool:
        """Detect sequences that might break prompt delimiters."""
        dangerous = [
            r"```\s*\n",
            r"<\s*/\s*system\s*>",
            r"<\s*/\s*instruction\s*>",
            r"<\s*/\s*prompt\s*>",
            r"\]\s*\]\s*>\s*",
            r"\{\{\s*end\s*\}\}",
        ]
        for pattern in dangerous:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _has_excessive_control_chars(self, text: str) -> bool:
        """Check if the ratio of control characters exceeds the threshold."""
        control_count = sum(1 for c in text if unicodedata.category(c).startswith("C") and c not in "\n\r\t")
        if len(text) == 0:
            return False
        ratio = control_count / len(text)
        return ratio > self.max_control_chars_ratio

    def _strip_control_chars(self, text: str) -> str:
        """Remove dangerous control characters while preserving whitespace."""
        allowed = {"\n", "\r", "\t", " "}
        return "".join(c for c in text if c in allowed or not unicodedata.category(c).startswith("C"))

    def sanitize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively sanitize all string values in a dictionary."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.sanitize(value)
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = self.sanitize_list(value)
            else:
                result[key] = value
        return result

    def sanitize_list(self, data: list[Any]) -> list[Any]:
        """Recursively sanitize all string values in a list."""
        result: list[Any] = []
        for item in data:
            if isinstance(item, str):
                result.append(self.sanitize(item))
            elif isinstance(item, dict):
                result.append(self.sanitize_dict(item))
            elif isinstance(item, list):
                result.append(self.sanitize_list(item))
            else:
                result.append(item)
        return result


def mask_secret(value: str, visible_prefix: int = 4, visible_suffix: int = 2) -> str:
    """Mask a secret value, showing only prefix and suffix."""
    if not value:
        return ""
    if len(value) <= visible_prefix + visible_suffix:
        return "*" * len(value)
    return value[:visible_prefix] + "*" * (len(value) - visible_prefix - visible_suffix) + value[-visible_suffix:]
