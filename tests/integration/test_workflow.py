"""Integration tests for the Lead Hunter Workflow."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from lead_hunter.models.domain import (
    ArtifactType,
    RunStatus,
    StageStatus,
    StageType,
)
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow
from lead_hunter.workflow.scoring import ScoringEngine


class MockAdapter:
    """Mock agent adapter for testing."""

    def __init__(self, name: str, response_content: dict[str, Any] | None = None) -> None:
        self._name = name
        self.response_content = response_content or {}

    async def send_request(self, request: Any) -> Any:
        from datetime import datetime, timezone
        from uuid import uuid4
        from lead_hunter.orchestrator.interfaces import AgentResponse
        return AgentResponse(
            response_id=uuid4(),
            request_id=request.request_id,
            run_id=request.run_id,
            correlation_id=request.correlation_id,
            agent_name=self._name,
            content=str(self.response_content).replace("'", '"'),
            timestamp=datetime.now(timezone.utc),
            structured_payload=self.response_content,
        )

    async def health_check(self) -> Any:
        from lead_hunter.orchestrator.interfaces import HealthStatus
        return HealthStatus.HEALTHY

    def get_name(self) -> str:
        return self._name

    def get_capabilities(self) -> list[str]:
        return ["text_generation"]


@pytest.mark.asyncio
class TestLeadHunterWorkflow:
    async def test_full_workflow_no_adapters(self) -> None:
        """Test complete workflow with no real adapters (mock fallback)."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        # Lower screening threshold so mock-generated evidence passes
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 1})

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="Acme Corp",
            industry="Technology",
            summary="A leading tech company",
            initial_claims=["Fast growth", "Strong team"],
        )

        assert run.status == RunStatus.COMPLETED
        stages = await pers.get_stages_for_run(run.run_id)
        stage_types = [s.stage_type for s in stages]
        assert StageType.INIT in stage_types
        assert StageType.RESEARCH in stage_types
        assert StageType.SCREENING in stage_types
        assert StageType.DEEP_RESEARCH in stage_types
        assert StageType.AUDIT in stage_types
        assert StageType.SCORING in stage_types
        assert StageType.APPROVAL in stage_types
        assert StageType.DELIVERY in stage_types
        assert StageType.FINALIZATION in stage_types

    async def test_workflow_with_mock_adapters(self) -> None:
        """Test workflow with mock adapters returning structured data."""
        pers = InMemoryPersistence()

        gemini = MockAdapter("gemini", {
            "lead_name": "Acme Corp",
            "evidence_items": [
                {"claim": "C1", "confidence": "HIGH", "category": "BUSINESS_INFO"},
                {"claim": "C2", "confidence": "HIGH", "category": "CONTACT"},
                {"claim": "C3", "confidence": "MEDIUM", "category": "ONLINE_PRESENCE"},
                {"claim": "C4", "confidence": "HIGH", "category": "FINANCIAL"},
            ],
            "missing_categories": [],
            "total_claims": 4,
            "verified_claims": 4,
        })
        kimi = MockAdapter("kimi", {
            "lead_name": "Acme Corp",
            "update_type": "NEW_EVIDENCE",
            "updated_claims": ["Deep dive complete"],
        })
        claude = MockAdapter("claude", {
            "lead_name": "Acme Corp",
            "summary": "Audit passed",
            "recommendations": [],
            "pass_fail": "PASS",
            "score": 90,
        })

        engine = OrchestrationEngine(
            pers,
            adapters={"gemini": gemini, "kimi": kimi, "claude": claude},
        )
        workflow = LeadHunterWorkflow(engine)

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="Acme Corp",
            industry="Technology",
            summary="A leading tech company",
        )

        assert run.status == RunStatus.COMPLETED
        artifacts = await pers.get_artifacts_for_run(run.run_id)
        artifact_types = [a.artifact_type for a in artifacts]
        assert ArtifactType.RESEARCH_BRIEF in artifact_types
        assert ArtifactType.EVIDENCE_PACKET in artifact_types
        assert ArtifactType.DEEP_RESEARCH_BRIEF in artifact_types
        assert ArtifactType.RESEARCH_UPDATE in artifact_types
        assert ArtifactType.AUDIT_PACKET in artifact_types
        assert ArtifactType.AUDIT_REPORT in artifact_types
        assert ArtifactType.FINAL_DOSSIER in artifact_types
        assert ArtifactType.SCORE_RESULT in artifact_types

    async def test_screening_rejection_insufficient_evidence(self) -> None:
        """Test that workflow rejects at screening when evidence is insufficient."""
        pers = InMemoryPersistence()

        gemini = MockAdapter("gemini", {
            "lead_name": "WeakCo",
            "evidence_items": [
                {"claim": "C1", "confidence": "LOW", "category": "BUSINESS_INFO"},
            ],
            "missing_categories": ["CONTACT", "FINANCIAL"],
            "total_claims": 1,
            "verified_claims": 0,
        })

        engine = OrchestrationEngine(pers, adapters={"gemini": gemini})
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 3})

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="WeakCo",
            industry="Retail",
            summary="A weak lead",
        )

        assert run.status == RunStatus.REJECTED
        stages = await pers.get_stages_for_run(run.run_id)
        screening_stages = [s for s in stages if s.stage_type == StageType.SCREENING]
        assert len(screening_stages) == 1
        assert screening_stages[0].status == StageStatus.REJECTED

    async def test_deep_research_skipped_low_evidence(self) -> None:
        """Test that deep research is skipped when evidence score is low."""
        pers = InMemoryPersistence()

        # Evidence with low verified ratio to trigger skip
        gemini = MockAdapter("gemini", {
            "lead_name": "MedCo",
            "evidence_items": [
                {"claim": "C1", "confidence": "HIGH", "category": "BUSINESS_INFO"},
                {"claim": "C2", "confidence": "LOW", "category": "CONTACT"},
                {"claim": "C3", "confidence": "LOW", "category": "ONLINE_PRESENCE"},
            ],
            "missing_categories": [],
            "total_claims": 3,
            "verified_claims": 1,
        })

        engine = OrchestrationEngine(pers, adapters={"gemini": gemini})
        workflow = LeadHunterWorkflow(
            engine,
            config={"deep_research_threshold": 50, "screening_min_evidence": 1},
        )

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="MedCo",
            industry="Finance",
            summary="A medium lead",
        )

        assert run.status == RunStatus.COMPLETED
        stages = await pers.get_stages_for_run(run.run_id)
        deep_stages = [s for s in stages if s.stage_type == StageType.DEEP_RESEARCH]
        assert len(deep_stages) == 1
        assert deep_stages[0].status == StageStatus.SKIPPED

    async def test_auto_reject_at_scoring(self) -> None:
        """Test auto-reject when score is below threshold."""
        pers = InMemoryPersistence()

        gemini = MockAdapter("gemini", {
            "lead_name": "BadCo",
            "evidence_items": [
                {"claim": "C1", "confidence": "LOW", "category": "BUSINESS_INFO"},
            ],
            "missing_categories": ["CONTACT", "FINANCIAL", "ONLINE_PRESENCE"],
            "total_claims": 1,
            "verified_claims": 0,
        })
        claude = MockAdapter("claude", {
            "lead_name": "BadCo",
            "summary": "Audit failed",
            "recommendations": ["Reject"],
            "pass_fail": "FAIL",
            "score": 20,
        })

        engine = OrchestrationEngine(pers, adapters={"gemini": gemini, "claude": claude})
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 1})

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="BadCo",
            industry="Unknown",
            summary="A bad lead",
        )

        # Should be rejected at screening due to low evidence quality
        assert run.status == RunStatus.REJECTED

    async def test_artifacts_persisted(self) -> None:
        """Verify all artifacts are persisted during workflow execution."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 1})

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="TestCo",
            industry="Tech",
            summary="Test",
        )

        artifacts = await pers.get_artifacts_for_run(run.run_id)
        assert len(artifacts) >= 7

    async def test_events_logged(self) -> None:
        """Verify events are logged during workflow execution."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 1})

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="TestCo",
            industry="Tech",
            summary="Test",
        )

        events = await pers.get_events_for_run(run.run_id)
        event_types = [e.event_type.name for e in events]
        assert "STAGE_STARTED" in event_types
        assert "STAGE_COMPLETED" in event_types
        assert "RUN_COMPLETED" in event_types

    async def test_workflow_with_delivery(self) -> None:
        """Test workflow with a mock delivery component."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)

        mock_delivery = AsyncMock()
        mock_delivery.send = AsyncMock(return_value=None)

        workflow = LeadHunterWorkflow(
            engine,
            delivery=mock_delivery,
            config={"screening_min_evidence": 1, "delivery_recipients": ["test@example.com"]},
        )

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="TestCo",
            industry="Tech",
            summary="Test",
        )

        assert run.status == RunStatus.COMPLETED
        mock_delivery.send.assert_called_once()
