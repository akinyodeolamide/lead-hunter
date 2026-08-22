"""Unit tests for exception hierarchy."""
from __future__ import annotations

import pytest

from lead_hunter.exceptions import (
    LeadHunterError,
    ConfigurationError,
    SecretError,
    StateMachineError,
    ValidationError,
    ArtifactValidationError,
    AgentError,
    AgentTimeoutError,
    AgentResponseError,
    PersistenceError,
    RecoveryError,
    ApprovalError,
    DeliveryError,
    SecurityError,
    PromptInjectionError,
    ScoringError,
    RetryExhaustedError,
    IdempotencyError,
)


class TestExceptionHierarchy:
    """Test that all exceptions inherit from LeadHunterError."""

    @pytest.mark.parametrize("exc_class", [
        ConfigurationError,
        SecretError,
        StateMachineError,
        ValidationError,
        ArtifactValidationError,
        AgentError,
        AgentTimeoutError,
        AgentResponseError,
        PersistenceError,
        RecoveryError,
        ApprovalError,
        DeliveryError,
        SecurityError,
        PromptInjectionError,
        ScoringError,
        RetryExhaustedError,
        IdempotencyError,
    ])
    def test_all_inherit_from_base(self, exc_class: type) -> None:
        assert issubclass(exc_class, LeadHunterError)

    def test_base_exception_message(self) -> None:
        exc = LeadHunterError("test message")
        assert str(exc) == "test message"
        assert exc.message == "test message"

    def test_base_exception_with_context(self) -> None:
        exc = LeadHunterError(
            "test message",
            run_id="run-123",
            stage_id="stage-456",
            details={"key": "value"},
        )
        assert exc.run_id == "run-123"
        assert exc.stage_id == "stage-456"
        assert exc.details == {"key": "value"}

    def test_base_exception_catch_all(self) -> None:
        with pytest.raises(LeadHunterError):
            raise ConfigurationError("config error")

    def test_prompt_injection_error(self) -> None:
        exc = PromptInjectionError("injection detected", details={"pattern": "ignore"})
        assert exc.details == {"pattern": "ignore"}
        assert isinstance(exc, SecurityError)

    def test_artifact_validation_error(self) -> None:
        exc = ArtifactValidationError("invalid schema")
        assert isinstance(exc, ValidationError)

    def test_agent_timeout_error(self) -> None:
        exc = AgentTimeoutError("timed out")
        assert isinstance(exc, AgentError)

    def test_agent_response_error(self) -> None:
        exc = AgentResponseError("bad response")
        assert isinstance(exc, AgentError)
