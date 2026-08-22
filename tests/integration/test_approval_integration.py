"""Integration tests for approval flows."""
from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from lead_hunter.approval.approval_service import ApprovalService
from lead_hunter.models.domain import (
    ApprovalDecision,
    ApprovalType,
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
class TestApprovalIntegration:
    async def test_full_approval_flow(self) -> None:
        """Workflow stops at approval; external approve completes to finalization."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        approval_svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)

        # Use high auto_approve_threshold so REQUIRE_APPROVAL is triggered
        scoring = ScoringEngine(auto_approve_threshold=95, auto_reject_threshold=30)
        workflow = LeadHunterWorkflow(
            engine,
            scoring_engine=scoring,
            approval_service=approval_svc,
            config={"screening_min_evidence": 1, "approval_timeout_seconds": 3600},
        )

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="BorderlineCo",
            industry="Tech",
            summary="A borderline lead",
        )

        # Should stop at WAITING_FOR_APPROVAL
        assert run.status == RunStatus.RUNNING
        stages = await pers.get_stages_for_run(run.run_id)
        approval_stages = [s for s in stages if s.stage_type == StageType.APPROVAL]
        assert len(approval_stages) == 1
        assert approval_stages[-1].status == StageStatus.WAITING_FOR_APPROVAL

        # Verify approval record exists
        approvals = await pers.get_approvals_for_run(run.run_id)
        assert len(approvals) == 1
        assert approvals[0].decision == ApprovalDecision.PENDING

        # External approve
        await approval_svc.approve(approvals[0].approval_id, "human_reviewer", "Approved")

        # Stage should be COMPLETED
        updated_stage = await pers.get_stage(approval_stages[-1].stage_id)
        assert updated_stage is not None
        assert updated_stage.status == StageStatus.COMPLETED

        # Manually continue remaining stages (delivery + finalization)
        run2 = await pers.get_run(run.run_id)
        assert run2 is not None
        run2 = await workflow._execute_delivery_stage(run2, "BorderlineCo")
        run2 = await workflow._execute_finalization_stage(run2)
        assert run2.status == RunStatus.COMPLETED

    async def test_rejection_at_approval_gate(self) -> None:
        """External reject stops workflow, run becomes REJECTED."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        approval_svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)

        scoring = ScoringEngine(auto_approve_threshold=95, auto_reject_threshold=30)
        workflow = LeadHunterWorkflow(
            engine,
            scoring_engine=scoring,
            approval_service=approval_svc,
            config={"screening_min_evidence": 1},
        )

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="RejectCo",
            industry="Tech",
            summary="A rejectable lead",
        )

        # Should be waiting for approval
        approvals = await pers.get_approvals_for_run(run.run_id)
        assert len(approvals) == 1

        # External reject
        await approval_svc.reject(approvals[0].approval_id, "human_reviewer", "Not qualified")

        # Run should be REJECTED
        updated_run = await pers.get_run(run.run_id)
        assert updated_run is not None
        assert updated_run.status == RunStatus.REJECTED

        # Stage should be REJECTED
        updated_stage = await pers.get_stage(approvals[0].stage_id)
        assert updated_stage is not None
        assert updated_stage.status == StageStatus.REJECTED

    async def test_timeout_handling(self) -> None:
        """Approval with past deadline gets auto-rejected by check_timeouts."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        approval_svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)

        scoring = ScoringEngine(auto_approve_threshold=95, auto_reject_threshold=30)
        workflow = LeadHunterWorkflow(
            engine,
            scoring_engine=scoring,
            approval_service=approval_svc,
            config={"screening_min_evidence": 1, "approval_timeout_seconds": -1},
        )

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="TimeoutCo",
            industry="Tech",
            summary="A timeout lead",
        )

        approvals = await pers.get_approvals_for_run(run.run_id)
        assert len(approvals) == 1
        assert approvals[0].decision == ApprovalDecision.PENDING

        # Trigger timeout check
        timed_out = await approval_svc.check_timeouts()
        assert len(timed_out) == 1
        assert timed_out[0].decision == ApprovalDecision.TIMEOUT

        # Run should be REJECTED
        updated_run = await pers.get_run(run.run_id)
        assert updated_run is not None
        assert updated_run.status == RunStatus.REJECTED

    async def test_pause_resume(self) -> None:
        """Pause stops the run; resume restores it."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        approval_svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)

        scoring = ScoringEngine(auto_approve_threshold=95, auto_reject_threshold=30)
        workflow = LeadHunterWorkflow(
            engine,
            scoring_engine=scoring,
            approval_service=approval_svc,
            config={"screening_min_evidence": 1},
        )

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="PauseCo",
            industry="Tech",
            summary="A pausable lead",
        )

        # Pause
        paused = await approval_svc.pause(run.run_id)
        assert paused.status == RunStatus.PAUSED

        approvals = await pers.get_approvals_for_run(run.run_id)
        assert approvals[0].decision == ApprovalDecision.PAUSED

        # Resume
        resumed = await approval_svc.resume(run.run_id)
        assert resumed.status == RunStatus.RUNNING

        approvals = await pers.get_approvals_for_run(run.run_id)
        assert approvals[0].decision == ApprovalDecision.PENDING
