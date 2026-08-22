"""Tests for recovery service."""
from __future__ import annotations

import pytest
import pytest_asyncio

from lead_hunter.models.domain import (
    Run,
    RunStatus,
    Stage,
    StageStatus,
    StageType,
)
from lead_hunter.orchestrator.run_manager import RunManager
from lead_hunter.orchestrator.stage_manager import StageManager
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.recovery.recovery_service import RecoveryService


@pytest_asyncio.fixture
async def recovery_setup():
    pers = InMemoryPersistence()
    engine = None
    recovery = RecoveryService(pers, engine)
    rm = RunManager(pers)
    sm = StageManager(pers)
    return pers, recovery, rm, sm


@pytest.mark.asyncio
class TestRecoveryService:
    async def test_recover_running_run_resets_stage(self, recovery_setup) -> None:
        pers, recovery, rm, sm = recovery_setup
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)
        stage = await sm.create_stage(run.run_id, StageType.RESEARCH)
        stage = await sm.start_stage(stage)
        assert stage.status == StageStatus.RUNNING

        recovered = await recovery.recover()
        assert len(recovered) == 1
        assert recovered[0].run_id == run.run_id

        stages = await pers.get_stages_for_run(run.run_id)
        assert stages[0].status == StageStatus.PENDING

    async def test_recover_paused_run_at_approval(self, recovery_setup) -> None:
        pers, recovery, rm, sm = recovery_setup
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)
        stage = await sm.create_stage(run.run_id, StageType.APPROVAL)
        stage = await sm.start_stage(stage)
        stage = await sm.request_approval(stage)
        assert stage.status == StageStatus.WAITING_FOR_APPROVAL

        recovered = await recovery.recover()
        assert len(recovered) == 1

        stages = await pers.get_stages_for_run(run.run_id)
        assert stages[0].status == StageStatus.WAITING_FOR_APPROVAL

    async def test_recover_all_stages_terminal_marks_completed(self, recovery_setup) -> None:
        pers, recovery, rm, sm = recovery_setup
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)
        stage = await sm.create_stage(run.run_id, StageType.RESEARCH)
        stage = await sm.start_stage(stage)
        stage = await sm.complete_stage(stage)
        assert stage.status == StageStatus.COMPLETED

        recovered = await recovery.recover()
        assert len(recovered) == 1

        fetched = await pers.get_run(run.run_id)
        assert fetched.status == RunStatus.COMPLETED

    async def test_recover_no_stages_resets_to_pending(self, recovery_setup) -> None:
        pers, recovery, rm, sm = recovery_setup
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)

        recovered = await recovery.recover()
        assert len(recovered) == 1

        fetched = await pers.get_run(run.run_id)
        assert fetched.status == RunStatus.PENDING

    async def test_recover_only_completed_runs(self, recovery_setup) -> None:
        pers, recovery, rm, sm = recovery_setup
        r1 = await rm.create_run()
        r1 = await rm.queue_run(r1)
        r1 = await rm.start_run(r1)
        r2 = await rm.create_run()
        r2 = await rm.queue_run(r2)
        r2 = await rm.start_run(r2)
        r2 = await rm.complete_run(r2)

        recovered = await recovery.recover()
        assert len(recovered) == 1
        assert recovered[0].run_id == r1.run_id

    async def test_recover_failed_run_not_recovered(self, recovery_setup) -> None:
        pers, recovery, rm, sm = recovery_setup
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)
        run = await rm.fail_run(run, "error")

        recovered = await recovery.recover()
        assert len(recovered) == 0
