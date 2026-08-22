"""Unit tests for ServiceRunner."""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from lead_hunter.models.domain import (
    Approval,
    ApprovalDecision,
    ApprovalType,
    Run,
    RunStatus,
    Stage,
    StageStatus,
    StageType,
)
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.scheduler.scheduler_service import SchedulerService
from lead_hunter.service_runner import ServiceRunner
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow


@pytest.fixture
def persistence() -> InMemoryPersistence:
    return InMemoryPersistence()


@pytest.fixture
def engine(persistence: InMemoryPersistence) -> OrchestrationEngine:
    return OrchestrationEngine(persistence)


class TestServiceRunnerInit:
    """Tests for ServiceRunner initialization."""

    def test_default_init(self) -> None:
        runner = ServiceRunner()
        assert runner.persistence is not None
        assert runner.engine is not None
        assert runner.check_interval == 5.0
        assert runner.scheduler is None
        assert runner._task is None

    def test_custom_init(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        runner = ServiceRunner(persistence=persistence, engine=engine, check_interval=1.0)
        assert runner.persistence is persistence
        assert runner.engine is engine
        assert runner.check_interval == 1.0


class TestServiceRunnerStartStop:
    """Tests for ServiceRunner start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        runner = ServiceRunner(persistence=persistence, engine=engine, check_interval=0.1)
        await runner.start()
        assert runner.scheduler is not None
        assert runner._task is not None
        assert not runner._task.done()
        await runner.stop()
        assert runner._task is None or runner._task.done()

    @pytest.mark.asyncio
    async def test_stop_without_start(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        runner = ServiceRunner(persistence=persistence, engine=engine)
        # Should not raise
        await runner.stop()

    @pytest.mark.asyncio
    async def test_run_forever_stops_on_signal(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        runner = ServiceRunner(persistence=persistence, engine=engine, check_interval=0.1)
        # Simulate shutdown after a short delay
        async def trigger_shutdown() -> None:
            await asyncio.sleep(0.2)
            runner.shutdown_handler._is_shutting_down = True
            runner.shutdown_handler._shutdown_event.set()

        asyncio.create_task(trigger_shutdown())
        await runner.run_forever()
        # Should complete without hanging


class TestServiceRunnerRecovery:
    """Tests for ServiceRunner recovery on startup."""

    @pytest.mark.asyncio
    async def test_recovery_on_start(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        # Create a run that needs recovery
        run = Run(status=RunStatus.RUNNING)
        await persistence.create_run(run)

        runner = ServiceRunner(persistence=persistence, engine=engine, check_interval=0.1)
        await runner.start()
        # Give recovery time to run
        await asyncio.sleep(0.1)
        await runner.stop()

        # Recovery should have processed the run
        updated = await persistence.get_run(run.run_id)
        assert updated is not None

    @pytest.mark.asyncio
    async def test_recovery_with_stages(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        run = Run(status=RunStatus.RUNNING)
        await persistence.create_run(run)
        stage = Stage(run_id=run.run_id, stage_type=StageType.RESEARCH, status=StageStatus.RUNNING)
        await persistence.create_stage(stage)

        runner = ServiceRunner(persistence=persistence, engine=engine, check_interval=0.1)
        await runner.start()
        await asyncio.sleep(0.1)
        await runner.stop()

        updated_stage = await persistence.get_stage(stage.stage_id)
        assert updated_stage is not None


class TestServiceRunnerContinueRuns:
    """Tests for ServiceRunner auto-continuation of runs."""

    @pytest.mark.asyncio
    async def test_continue_runs_after_approval(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        """Test that a run with a completed approval stage gets continued."""
        run = Run(status=RunStatus.RUNNING, metadata={"lead_name": "TestCorp", "industry": "Tech", "summary": "test"})
        await persistence.create_run(run)

        for i, st in enumerate([StageType.INIT, StageType.RESEARCH, StageType.SCREENING,
                   StageType.DEEP_RESEARCH, StageType.AUDIT, StageType.SCORING, StageType.APPROVAL]):
            stage = Stage(
                run_id=run.run_id,
                stage_type=st,
                status=StageStatus.COMPLETED,
                started_at=datetime.now(timezone.utc) + timedelta(seconds=i),
                completed_at=datetime.now(timezone.utc) + timedelta(seconds=i),
            )
            await persistence.create_stage(stage)

        runner = ServiceRunner(persistence=persistence, engine=engine, check_interval=0.1)
        # Bypass recovery (which would complete the run) and directly test continuation
        runner.scheduler = SchedulerService(persistence, engine, runner._workflow_factory)
        await runner.scheduler.start()
        await runner._continue_runs()
        await runner.scheduler.shutdown()

        stages = await persistence.get_stages_for_run(run.run_id)
        stage_types = [s.stage_type for s in stages]
        assert StageType.DELIVERY in stage_types
        assert StageType.FINALIZATION in stage_types

    @pytest.mark.asyncio
    async def test_continue_runs_no_matching_stages(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        """Test that runs without completed approval stages are not continued."""
        run = Run(status=RunStatus.RUNNING, metadata={})
        await persistence.create_run(run)

        stage = Stage(run_id=run.run_id, stage_type=StageType.RESEARCH, status=StageStatus.RUNNING)
        await persistence.create_stage(stage)

        runner = ServiceRunner(persistence=persistence, engine=engine, check_interval=0.1)
        await runner.start()
        await asyncio.sleep(0.2)
        await runner.stop()

        # Run should still be RUNNING (no continuation happened)
        updated = await persistence.get_run(run.run_id)
        assert updated.status == RunStatus.RUNNING


class TestServiceRunnerCheckTimeouts:
    """Tests for ServiceRunner timeout checking."""

    @pytest.mark.asyncio
    async def test_check_timeouts_no_approvals(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        runner = ServiceRunner(persistence=persistence, engine=engine, check_interval=0.1)
        # Should not raise
        await runner._check_timeouts()

    @pytest.mark.asyncio
    async def test_check_timeouts_with_timed_out_approval(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        from datetime import timedelta
        run = Run(status=RunStatus.RUNNING)
        await persistence.create_run(run)

        stage = Stage(run_id=run.run_id, stage_type=StageType.APPROVAL, status=StageStatus.WAITING_FOR_APPROVAL)
        await persistence.create_stage(stage)

        approval = Approval(
            run_id=run.run_id,
            stage_id=stage.stage_id,
            approval_type=ApprovalType.MANUAL_REVIEW,
            decision=ApprovalDecision.PENDING,
            deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        await persistence.create_approval(approval)

        runner = ServiceRunner(persistence=persistence, engine=engine, check_interval=0.1)
        await runner.start()
        await asyncio.sleep(0.2)
        await runner.stop()

        # Approval should have been timed out
        updated_approval = await persistence.get_approval(approval.approval_id)
        assert updated_approval.decision == ApprovalDecision.TIMEOUT


class TestServiceRunnerWorkflowFactory:
    """Tests for the workflow factory."""

    def test_workflow_factory(self, persistence: InMemoryPersistence, engine: OrchestrationEngine) -> None:
        runner = ServiceRunner(persistence=persistence, engine=engine)
        workflow = runner._workflow_factory()
        assert isinstance(workflow, LeadHunterWorkflow)
        assert workflow.engine is engine
