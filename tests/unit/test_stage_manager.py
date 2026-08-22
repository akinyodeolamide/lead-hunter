"""Unit tests for stage manager."""
from __future__ import annotations

import pytest

from lead_hunter.models.domain import StageStatus, StageType
from lead_hunter.orchestrator.stage_manager import StageManager
from lead_hunter.persistence.in_memory import InMemoryPersistence


@pytest.mark.asyncio
class TestStageManager:
    async def test_create_stage(self) -> None:
        pers = InMemoryPersistence()
        sm = StageManager(pers)
        from uuid import uuid4
        stage = await sm.create_stage(run_id=uuid4(), stage_type=StageType.RESEARCH)
        assert stage.status == StageStatus.PENDING
        assert stage.stage_type == StageType.RESEARCH
        assert stage.retry_count == 0

    async def test_start_and_complete_stage(self) -> None:
        pers = InMemoryPersistence()
        sm = StageManager(pers)
        from uuid import uuid4
        stage = await sm.create_stage(run_id=uuid4(), stage_type=StageType.RESEARCH)
        stage = await sm.start_stage(stage)
        assert stage.status == StageStatus.RUNNING
        stage = await sm.complete_stage(stage)
        assert stage.status == StageStatus.COMPLETED

    async def test_fail_and_retry_stage(self) -> None:
        pers = InMemoryPersistence()
        sm = StageManager(pers)
        from uuid import uuid4
        stage = await sm.create_stage(run_id=uuid4(), stage_type=StageType.RESEARCH, max_retries=3)
        stage = await sm.start_stage(stage)
        stage = await sm.fail_stage(stage, "timeout")
        assert stage.status == StageStatus.FAILED
        stage = await sm.retry_stage(stage)
        assert stage.status == StageStatus.PENDING
        assert stage.retry_count == 1

    async def test_max_retries_not_exceeded(self) -> None:
        pers = InMemoryPersistence()
        sm = StageManager(pers)
        from uuid import uuid4
        stage = await sm.create_stage(run_id=uuid4(), stage_type=StageType.RESEARCH, max_retries=1)
        stage = await sm.start_stage(stage)
        stage = await sm.fail_stage(stage, "timeout")
        stage = await sm.retry_stage(stage)
        assert stage.retry_count == 1
        stage = await sm.start_stage(stage)
        stage = await sm.fail_stage(stage, "timeout")
        stage = await sm.retry_stage(stage)
        assert stage.retry_count == 1  # max retries exceeded, no change

    async def test_skip_stage(self) -> None:
        pers = InMemoryPersistence()
        sm = StageManager(pers)
        from uuid import uuid4
        stage = await sm.create_stage(run_id=uuid4(), stage_type=StageType.RESEARCH)
        stage = await sm.skip_stage(stage)
        assert stage.status == StageStatus.SKIPPED

    async def test_request_approval(self) -> None:
        pers = InMemoryPersistence()
        sm = StageManager(pers)
        from uuid import uuid4
        stage = await sm.create_stage(run_id=uuid4(), stage_type=StageType.APPROVAL)
        stage = await sm.start_stage(stage)
        stage = await sm.request_approval(stage)
        assert stage.status == StageStatus.WAITING_FOR_APPROVAL
