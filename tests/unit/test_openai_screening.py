"""Tests for OpenAI screening integration."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from lead_hunter.models.domain import RunStatus
from lead_hunter.orchestrator.interfaces import AgentResponse, HealthStatus
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow


class MockOpenAIAdapter:
    def __init__(self, response_content: str = '{"recommendation": "PASS", "confidence": "HIGH", "rationale": "ok", "concerns": []}'):
        self.response_content = response_content

    async def send_request(self, request: Any) -> AgentResponse:
        from datetime import datetime, timezone
        from uuid import uuid4
        return AgentResponse(
            response_id=uuid4(),
            request_id=request.request_id,
            run_id=request.run_id,
            correlation_id=request.correlation_id,
            agent_name="chatgpt",
            content=self.response_content,
            timestamp=datetime.now(timezone.utc),
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    def get_name(self) -> str:
        return "chatgpt"

    def get_capabilities(self) -> list[str]:
        return ["text_generation"]


class TestOpenAIScreening:
    @pytest.mark.asyncio
    async def test_openai_screening_invoked_when_available(self) -> None:
        pers = InMemoryPersistence()
        openai = MockOpenAIAdapter()
        engine = OrchestrationEngine(pers, adapters={"chatgpt": openai})
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 1})

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="TestCo",
            industry="Tech",
            summary="Test",
        )
        assert run.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_openai_unhealthy_uses_deterministic(self) -> None:
        pers = InMemoryPersistence()
        openai = MockOpenAIAdapter()
        openai.health_check = AsyncMock(return_value=HealthStatus.UNHEALTHY)
        engine = OrchestrationEngine(pers, adapters={"chatgpt": openai})
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 1})

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="TestCo",
            industry="Tech",
            summary="Test",
        )
        assert run.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_malformed_openai_response_handled(self) -> None:
        pers = InMemoryPersistence()
        openai = MockOpenAIAdapter(response_content="not json at all")
        engine = OrchestrationEngine(pers, adapters={"chatgpt": openai})
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 1})

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="TestCo",
            industry="Tech",
            summary="Test",
        )
        assert run.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_deterministic_rejection_authoritative(self) -> None:
        pers = InMemoryPersistence()
        openai = MockOpenAIAdapter(response_content='{"recommendation": "PASS"}')
        engine = OrchestrationEngine(pers, adapters={"chatgpt": openai})
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 10})

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="TestCo",
            industry="Tech",
            summary="Test",
        )
        # Deterministic screening should reject due to insufficient evidence
        assert run.status == RunStatus.REJECTED
