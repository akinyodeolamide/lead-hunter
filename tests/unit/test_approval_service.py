"""Unit tests for the ApprovalService."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from lead_hunter.approval.approval_service import ApprovalService
from lead_hunter.exceptions import NotFoundError
from lead_hunter.models.domain import (
    ApprovalDecision,
    ApprovalType,
    EventType,
    RunStatus,
    StageStatus,
    StageType,
)
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence


@pytest.mark.asyncio
class TestApprovalService:
    async def _make_service(self) -> tuple[ApprovalService, InMemoryPersistence, OrchestrationEngine]:
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)
        return svc, pers, engine

    async def test_create_approval_request(self) -> None:
        svc, pers, engine = await self._make_service()
        run = await engine.start_run(configuration_id="test")
        stage = await engine.stage_manager.create_stage(
            run_id=run.run_id, stage_type=StageType.APPROVAL
        )
        stage = await engine.stage_manager.start_stage(stage)

        approval = await svc.create_approval_request(
            run_id=run.run_id,
            stage_id=stage.stage_id,
            approval_type=ApprovalType.MANUAL_REVIEW,
            request_details={"lead_name": "TestCo", "score": 75},
            timeout_seconds=3600,
        )

        assert approval.decision == ApprovalDecision.PENDING
        assert approval.approval_type == ApprovalType.MANUAL_REVIEW
        assert approval.request_details["lead_name"] == "TestCo"
        assert approval.deadline is not None

        # Stage should be WAITING_FOR_APPROVAL
        updated_stage = await pers.get_stage(stage.stage_id)
        assert updated_stage is not None
        assert updated_stage.status == StageStatus.WAITING_FOR_APPROVAL

    async def test_approve_sets_decision(self) -> None:
        svc, pers, engine = await self._make_service()
        run = await engine.start_run(configuration_id="test")
        stage = await engine.stage_manager.create_stage(
            run_id=run.run_id, stage_type=StageType.APPROVAL
        )
        stage = await engine.stage_manager.start_stage(stage)

        approval = await svc.create_approval_request(
            run_id=run.run_id, stage_id=stage.stage_id, timeout_seconds=3600
        )
        result = await svc.approve(approval.approval_id, "admin", "Looks good")

        assert result.decision == ApprovalDecision.APPROVED
        assert result.decided_by == "admin"
        assert result.decision_rationale == "Looks good"
        assert result.decided_at is not None

        # Stage should be COMPLETED
        updated_stage = await pers.get_stage(stage.stage_id)
        assert updated_stage is not None
        assert updated_stage.status == StageStatus.COMPLETED

        # Event logged
        events = await pers.get_events_for_run(run.run_id)
        decided_events = [e for e in events if e.event_type == EventType.APPROVAL_DECIDED]
        assert len(decided_events) >= 1

    async def test_reject_sets_decision(self) -> None:
        svc, pers, engine = await self._make_service()
        run = await engine.start_run(configuration_id="test")
        stage = await engine.stage_manager.create_stage(
            run_id=run.run_id, stage_type=StageType.APPROVAL
        )
        stage = await engine.stage_manager.start_stage(stage)

        approval = await svc.create_approval_request(
            run_id=run.run_id, stage_id=stage.stage_id, timeout_seconds=3600
        )
        result = await svc.reject(approval.approval_id, "admin", "Insufficient evidence")

        assert result.decision == ApprovalDecision.REJECTED
        assert result.decided_by == "admin"

        # Stage should be REJECTED
        updated_stage = await pers.get_stage(stage.stage_id)
        assert updated_stage is not None
        assert updated_stage.status == StageStatus.REJECTED

        # Run should be REJECTED
        updated_run = await pers.get_run(run.run_id)
        assert updated_run is not None
        assert updated_run.status == RunStatus.REJECTED

    async def test_pause_run(self) -> None:
        svc, pers, engine = await self._make_service()
        run = await engine.start_run(configuration_id="test")
        stage = await engine.stage_manager.create_stage(
            run_id=run.run_id, stage_type=StageType.APPROVAL
        )
        stage = await engine.stage_manager.start_stage(stage)
        approval = await svc.create_approval_request(
            run_id=run.run_id, stage_id=stage.stage_id, timeout_seconds=3600
        )

        paused_run = await svc.pause(run.run_id)
        assert paused_run.status == RunStatus.PAUSED

        # Approval should be PAUSED
        updated = await pers.get_approval(approval.approval_id)
        assert updated is not None
        assert updated.decision == ApprovalDecision.PAUSED

        # Event logged
        events = await pers.get_events_for_run(run.run_id)
        pause_events = [e for e in events if e.event_type == EventType.RUN_PAUSED]
        assert len(pause_events) == 1

    async def test_resume_run(self) -> None:
        svc, pers, engine = await self._make_service()
        run = await engine.start_run(configuration_id="test")
        stage = await engine.stage_manager.create_stage(
            run_id=run.run_id, stage_type=StageType.APPROVAL
        )
        stage = await engine.stage_manager.start_stage(stage)
        approval = await svc.create_approval_request(
            run_id=run.run_id, stage_id=stage.stage_id, timeout_seconds=3600
        )
        await svc.pause(run.run_id)

        resumed_run = await svc.resume(run.run_id)
        assert resumed_run.status == RunStatus.RUNNING

        # Approval should be back to PENDING
        updated = await pers.get_approval(approval.approval_id)
        assert updated is not None
        assert updated.decision == ApprovalDecision.PENDING

        # Event logged
        events = await pers.get_events_for_run(run.run_id)
        resume_events = [e for e in events if e.event_type == EventType.RUN_RESUMED]
        assert len(resume_events) == 1

    async def test_timeout_auto_reject(self) -> None:
        svc, pers, engine = await self._make_service()
        run = await engine.start_run(configuration_id="test")
        stage = await engine.stage_manager.create_stage(
            run_id=run.run_id, stage_type=StageType.APPROVAL
        )
        stage = await engine.stage_manager.start_stage(stage)

        # Create approval with deadline in the past
        approval = await svc.create_approval_request(
            run_id=run.run_id,
            stage_id=stage.stage_id,
            timeout_seconds=-1,  # deadline already passed
        )

        timed_out = await svc.check_timeouts()
        assert len(timed_out) == 1
        assert timed_out[0].approval_id == approval.approval_id
        assert timed_out[0].decision == ApprovalDecision.TIMEOUT

        # Stage should be REJECTED
        updated_stage = await pers.get_stage(stage.stage_id)
        assert updated_stage is not None
        assert updated_stage.status == StageStatus.REJECTED

        # Run should be REJECTED
        updated_run = await pers.get_run(run.run_id)
        assert updated_run is not None
        assert updated_run.status == RunStatus.REJECTED

    async def test_get_waiting_approvals(self) -> None:
        svc, pers, engine = await self._make_service()
        run = await engine.start_run(configuration_id="test")
        stage = await engine.stage_manager.create_stage(
            run_id=run.run_id, stage_type=StageType.APPROVAL
        )
        stage = await engine.stage_manager.start_stage(stage)
        await svc.create_approval_request(
            run_id=run.run_id, stage_id=stage.stage_id, timeout_seconds=3600
        )

        waiting = await svc.get_waiting_approvals()
        assert len(waiting) == 1

        # After approval, should be empty
        await svc.approve(waiting[0].approval_id, "admin")
        waiting = await svc.get_waiting_approvals()
        assert len(waiting) == 0

    async def test_recover_approval(self) -> None:
        svc, pers, engine = await self._make_service()
        run = await engine.start_run(configuration_id="test")
        stage = await engine.stage_manager.create_stage(
            run_id=run.run_id, stage_type=StageType.APPROVAL
        )
        stage = await engine.stage_manager.start_stage(stage)
        approval = await svc.create_approval_request(
            run_id=run.run_id, stage_id=stage.stage_id, timeout_seconds=3600
        )

        recovered = await svc.recover_approval(approval.approval_id)
        assert recovered is not None
        assert recovered.approval_id == approval.approval_id

        # After decision, should return None
        await svc.approve(approval.approval_id, "admin")
        recovered = await svc.recover_approval(approval.approval_id)
        assert recovered is None

        # Nonexistent should return None
        assert await svc.recover_approval(uuid4()) is None

    async def test_approve_nonexistent_raises(self) -> None:
        svc, pers, engine = await self._make_service()
        with pytest.raises(NotFoundError, match="not found"):
            await svc.approve(uuid4(), "admin")
