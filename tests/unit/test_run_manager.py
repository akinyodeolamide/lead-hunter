"""Unit tests for run manager."""
from __future__ import annotations

import pytest

from lead_hunter.models.domain import EventType, RunStatus
from lead_hunter.orchestrator.run_manager import RunManager
from lead_hunter.persistence.in_memory import InMemoryPersistence


@pytest.mark.asyncio
class TestRunManager:
    async def test_create_run(self) -> None:
        pers = InMemoryPersistence()
        rm = RunManager(pers)
        run = await rm.create_run(configuration_id="test-cfg", metadata={"campaign": "summer"})
        assert run.status == RunStatus.PENDING
        assert run.configuration_id == "test-cfg"
        assert run.metadata == {"campaign": "summer"}

    async def test_start_run(self) -> None:
        pers = InMemoryPersistence()
        rm = RunManager(pers)
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)
        assert run.status == RunStatus.RUNNING
        assert run.started_at is not None

    async def test_complete_run(self) -> None:
        pers = InMemoryPersistence()
        rm = RunManager(pers)
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)
        run = await rm.complete_run(run)
        assert run.status == RunStatus.COMPLETED
        assert run.completed_at is not None

    async def test_reject_run(self) -> None:
        pers = InMemoryPersistence()
        rm = RunManager(pers)
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)
        run = await rm.reject_run(run, "Insufficient evidence")
        assert run.status == RunStatus.REJECTED

    async def test_fail_run(self) -> None:
        pers = InMemoryPersistence()
        rm = RunManager(pers)
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)
        run = await rm.fail_run(run, "Agent timeout")
        assert run.status == RunStatus.FAILED

    async def test_pause_and_resume_run(self) -> None:
        pers = InMemoryPersistence()
        rm = RunManager(pers)
        run = await rm.create_run()
        run = await rm.queue_run(run)
        run = await rm.start_run(run)
        run = await rm.pause_run(run)
        assert run.status == RunStatus.PAUSED
        run = await rm.resume_run(run)
        assert run.status == RunStatus.RUNNING

    async def test_cancel_run(self) -> None:
        pers = InMemoryPersistence()
        rm = RunManager(pers)
        run = await rm.create_run()
        run = await rm.cancel_run(run)
        assert run.status == RunStatus.CANCELLED

    async def test_events_persisted(self) -> None:
        pers = InMemoryPersistence()
        rm = RunManager(pers)
        run = await rm.create_run()
        events = await pers.get_events_for_run(run.run_id)
        assert len(events) == 1
        assert events[0].event_type == EventType.RUN_CREATED
