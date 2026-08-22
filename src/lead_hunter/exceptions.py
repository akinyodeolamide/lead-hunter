"""Custom exception hierarchy for Lead Hunter."""
from __future__ import annotations

from typing import Any


class LeadHunterError(Exception):
    """Base exception for all Lead Hunter errors."""

    def __init__(self, message: str, *, run_id: str | None = None, stage_id: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.run_id = run_id
        self.stage_id = stage_id
        self.details = details or {}


class NotFoundError(LeadHunterError):
    """Requested resource not found."""


class ConfigurationError(LeadHunterError):
    """Invalid or missing configuration."""


class SecretError(LeadHunterError):
    """Missing or invalid secret."""


class StateMachineError(LeadHunterError):
    """Invalid state transition."""


class ValidationError(LeadHunterError):
    """Schema or data validation failure."""


class ArtifactValidationError(ValidationError):
    """Artifact failed schema validation."""


class AgentError(LeadHunterError):
    """Agent adapter failure."""


class AgentTimeoutError(AgentError):
    """Agent request timed out."""


class AgentResponseError(AgentError):
    """Agent returned malformed or unexpected response."""


class PersistenceError(LeadHunterError):
    """Database or persistence failure."""


class RecoveryError(LeadHunterError):
    """Crash/restart recovery failure."""


class ApprovalError(LeadHunterError):
    """Approval gate failure."""


class DeliveryError(LeadHunterError):
    """Email delivery failure."""


class SecurityError(LeadHunterError):
    """Security-related failure (e.g., prompt injection detected)."""


class RateLimitError(SecurityError):
    """Rate limit exceeded."""


class PromptInjectionError(SecurityError):
    """Suspected prompt injection detected in external content."""


class ScoringError(LeadHunterError):
    """Scoring engine failure."""


class RetryExhaustedError(LeadHunterError):
    """Max retries exceeded for a recoverable operation."""


class IdempotencyError(LeadHunterError):
    """Idempotency violation detected."""
