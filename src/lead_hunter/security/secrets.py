"""Secret management for Lead Hunter."""
from __future__ import annotations

import os
from typing import Any

from lead_hunter.exceptions import SecretError
from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.security.sanitizer import mask_secret

logger = get_logger("security.secrets")


class SecretsManager:
    """Manages API keys and secrets from environment variables."""

    REQUIRED_SECRETS = [
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "MOONSHOT_API_KEY",
        "ANTHROPIC_API_KEY",
        "SMTP_PASSWORD",
    ]

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets: dict[str, str] = secrets or {}

    def load_from_env(self, prefix: str = "") -> None:
        """Load secrets from environment variables.

        Args:
            prefix: Optional prefix to strip from env var names.
        """
        for key in self.REQUIRED_SECRETS:
            env_key = f"{prefix}{key}" if prefix else key
            value = os.environ.get(env_key)
            if value:
                self._secrets[key] = value
                log_event(logger, "INFO", f"Loaded secret {key}")

    def get(self, key: str) -> str | None:
        """Get a secret value by key."""
        return self._secrets.get(key)

    def set(self, key: str, value: str) -> None:
        """Set a secret value."""
        self._secrets[key] = value

    def validate_required(self, keys: list[str] | None = None) -> None:
        """Validate that required secrets are present.

        Raises SecretError if any required secret is missing.
        """
        keys = keys or self.REQUIRED_SECRETS
        missing = [k for k in keys if not self._secrets.get(k)]
        if missing:
            raise SecretError(
                f"Missing required secrets: {', '.join(missing)}",
                details={"missing": missing},
            )

    def mask(self, key: str) -> str:
        """Return a masked version of a secret for logging."""
        value = self._secrets.get(key)
        if value is None:
            return "<not set>"
        return mask_secret(value)

    def list_keys(self) -> list[str]:
        """Return list of configured secret keys."""
        return list(self._secrets.keys())

    def is_configured(self, key: str) -> bool:
        """Check if a secret is configured."""
        return key in self._secrets and bool(self._secrets[key])
