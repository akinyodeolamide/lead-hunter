"""Unit tests for orchestration engine."""
from __future__ import annotations

import pytest

from lead_hunter.models.domain import RunStatus, StageType
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence


@pytest.mark.asyncio
class TestOrchestrationEngine:
    async def test_start_run(self) -> None:
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        run = await engine.start_run(configuration_id="test")
        assert run.status == RunStatus.RUNNING
        stages = await pers.get_stages_for_run(run.run_id)
        assert len(stages) >= 2  # INIT + next stage created
        assert stages[0].stage_type == StageType.INIT
        assert stages[0].status.name == "COMPLETED"

    async def test_pause_and_resume(self) -> None:
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        run = await engine.start_run()
        paused = await engine.pause_run(run.run_id)
        assert paused is not None
        assert paused.status == RunStatus.PAUSED
        resumed = await engine.resume_run(run.run_id)
        assert resumed is not None
        assert resumed.status == RunStatus.RUNNING

    async def test_cancel_run(self) -> None:
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        run = await engine.start_run()
        cancelled = await engine.cancel_run(run.run_id)
        assert cancelled is not None
        assert cancelled.status == RunStatus.CANCELLED

    async def test_approve_stage(self) -> None:
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        run = await engine.start_run()
        stages = await pers.get_stages_for_run(run.run_id)
        approval_stage = [s for s in stages if s.stage_type == StageType.APPROVAL]
        if approval_stage:
            stage = await engine.stage_manager.request_approval(approval_stage[0])
            stage = await engine.approve_stage(stage, "admin@example.com", "Looks good")
            assert stage.status.name == "COMPLETED"

    async def test_reject_stage(self) -> None:
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        run = await engine.start_run()
        stages = await pers.get_stages_for_run(run.run_id)
        # Find the first non-INIT stage and reject it
        for stage in stages:
            if stage.stage_type != StageType.INIT:
                stage = await engine.stage_manager.start_stage(stage)
                stage = await engine.reject_stage(stage, "admin", "Not qualified")
                assert stage.status.name == "REJECTED"
                run = await pers.get_run(run.run_id)
                assert run.status == RunStatus.REJECTED
                break
