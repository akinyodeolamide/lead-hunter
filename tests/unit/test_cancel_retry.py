"""Tests for cancel and retry operations."""
from __future__ import annotations

import pytest
from uuid import uuid4

from lead_hunter.models.domain import Run, RunStatus, Stage, StageStatus, StageType
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence


class TestCancelRun:
    @pytest.fixture
    def engine(self):
        pers = InMemoryPersistence()
        return OrchestrationEngine(pers)

    @pytest.mark.asyncio
    async def test_cancel_running_run(self, engine: OrchestrationEngine) -> None:
        run = Run(status=RunStatus.RUNNING)
        await engine.persistence.create_run(run)
        result = await engine.cancel_run(run.run_id)
        assert result is not None
        assert result.status == RunStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_run(self, engine: OrchestrationEngine) -> None:
        result = await engine.cancel_run(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_already_completed_run_fails(self, engine: OrchestrationEngine) -> None:
        run = Run(status=RunStatus.COMPLETED)
        await engine.persistence.create_run(run)
        with pytest.raises(Exception):
            await engine.cancel_run(run.run_id)


class TestRetryStage:
    @pytest.fixture
    def engine(self):
        pers = InMemoryPersistence()
        return OrchestrationEngine(pers)

    @pytest.mark.asyncio
    async def test_retry_failed_stage(self, engine: OrchestrationEngine) -> None:
        run = Run(status=RunStatus.RUNNING)
        await engine.persistence.create_run(run)
        stage = Stage(run_id=run.run_id, stage_type=StageType.RESEARCH, status=StageStatus.FAILED, retry_count=0, max_retries=3)
        await engine.persistence.create_stage(stage)
        result = await engine.retry_stage(stage.stage_id)
        assert result is not None
        assert result.status == StageStatus.PENDING
        assert result.retry_count == 1

    @pytest.mark.asyncio
    async def test_retry_non_failed_stage_fails(self, engine: OrchestrationEngine) -> None:
        run = Run(status=RunStatus.RUNNING)
        await engine.persistence.create_run(run)
        stage = Stage(run_id=run.run_id, stage_type=StageType.RESEARCH, status=StageStatus.COMPLETED)
        await engine.persistence.create_stage(stage)
        with pytest.raises(ValueError):
            await engine.retry_stage(stage.stage_id)

    @pytest.mark.asyncio
    async def test_retry_nonexistent_stage(self, engine: OrchestrationEngine) -> None:
        result = await engine.retry_stage(uuid4())
        assert result is None
