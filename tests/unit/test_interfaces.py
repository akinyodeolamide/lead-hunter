"""Unit tests for abstract interfaces."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from lead_hunter.orchestrator.interfaces import (
    AgentRequest,
    AgentResponse,
    HealthStatus,
)


class TestAgentRequest:
    """Test AgentRequest dataclass."""

    def test_default_creation(self) -> None:
        req = AgentRequest(
            request_id=uuid4(),
            run_id=uuid4(),
            correlation_id=uuid4(),
            stage_id=uuid4(),
            agent_name="gemini",
            prompt="Research this company",
            context={},
        )
        assert req.agent_name == "gemini"
        assert req.max_tokens == 2048
        assert req.temperature == 0.0
        assert req.timeout_seconds == 60.0
        assert req.attempt_number == 1

    def test_custom_values(self) -> None:
        req = AgentRequest(
            request_id=uuid4(),
            run_id=uuid4(),
            correlation_id=uuid4(),
            stage_id=uuid4(),
            agent_name="claude",
            prompt="Audit this evidence",
            context={"run": "data"},
            max_tokens=4096,
            temperature=0.5,
            timeout_seconds=120.0,
            attempt_number=2,
        )
        assert req.max_tokens == 4096
        assert req.temperature == 0.5
        assert req.timeout_seconds == 120.0
        assert req.attempt_number == 2


class TestAgentResponse:
    """Test AgentResponse dataclass."""

    def test_creation(self) -> None:
        resp = AgentResponse(
            response_id=uuid4(),
            request_id=uuid4(),
            run_id=uuid4(),
            correlation_id=uuid4(),
            agent_name="gemini",
            content="Research findings",
            timestamp=datetime.now(timezone.utc),
        )
        assert resp.agent_name == "gemini"
        assert resp.content == "Research findings"
        assert resp.structured_payload is None
        assert resp.usage is None
        assert resp.latency_ms == 0.0

    def test_with_payload(self) -> None:
        resp = AgentResponse(
            response_id=uuid4(),
            request_id=uuid4(),
            run_id=uuid4(),
            correlation_id=uuid4(),
            agent_name="gemini",
            content="Research findings",
            structured_payload={"claims": ["c1"]},
            usage={"prompt_tokens": 100, "completion_tokens": 200},
            latency_ms=1500.0,
            timestamp=datetime.now(timezone.utc),
        )
        assert resp.structured_payload == {"claims": ["c1"]}
        assert resp.usage == {"prompt_tokens": 100, "completion_tokens": 200}
        assert resp.latency_ms == 1500.0


class TestHealthStatus:
    """Test HealthStatus enum."""

    def test_values(self) -> None:
        assert len(list(HealthStatus)) == 4
        assert HealthStatus.HEALTHY.name == "HEALTHY"
        assert HealthStatus.UNHEALTHY.name == "UNHEALTHY"
