"""Tests for SQL persistence adapter."""
from __future__ import annotations

import pytest
import pytest_asyncio
from uuid import uuid4

from lead_hunter.config.config import PersistenceConfig
from lead_hunter.models.domain import (
    Approval,
    ApprovalDecision,
    ApprovalType,
    Artifact,
    ArtifactType,
    Configuration,
    ErrorRecord,
    Event,
    EventType,
    Run,
    RunStatus,
    Stage,
    StageStatus,
    StageType,
)
from lead_hunter.persistence.database import DatabaseManager
from lead_hunter.persistence.sql_adapter import SQLPersistence


@pytest_asyncio.fixture
async def sql_pers():
    """Create a SQL persistence adapter with an in-memory test database."""
    cfg = PersistenceConfig(database_url="sqlite+aiosqlite:///:memory:")
    db = DatabaseManager(cfg)
    db.initialize()
    await db.create_tables()
    pers = SQLPersistence(db)
    yield pers
    await db.close()


@pytest.mark.asyncio
class TestSQLRunCRUD:
    async def test_create_and_get_run(self, sql_pers) -> None:
        run = Run(status=RunStatus.PENDING, configuration_id="test")
        created = await sql_pers.create_run(run)
        assert created.run_id == run.run_id

        fetched = await sql_pers.get_run(run.run_id)
        assert fetched is not None
        assert fetched.status == RunStatus.PENDING
        assert fetched.configuration_id == "test"

    async def test_update_run(self, sql_pers) -> None:
        run = Run(status=RunStatus.PENDING)
        await sql_pers.create_run(run)
        run.status = RunStatus.RUNNING
        run.started_at = run.created_at
        updated = await sql_pers.update_run(run)
        assert updated.status == RunStatus.RUNNING

        fetched = await sql_pers.get_run(run.run_id)
        assert fetched.status == RunStatus.RUNNING
        assert fetched.started_at is not None

    async def test_list_runs_by_status(self, sql_pers) -> None:
        r1 = Run(status=RunStatus.COMPLETED)
        r2 = Run(status=RunStatus.RUNNING)
        r3 = Run(status=RunStatus.COMPLETED)
        await sql_pers.create_run(r1)
        await sql_pers.create_run(r2)
        await sql_pers.create_run(r3)

        completed = await sql_pers.list_runs(status=RunStatus.COMPLETED)
        assert len(completed) == 2

        running = await sql_pers.list_runs(status=RunStatus.RUNNING)
        assert len(running) == 1

        all_runs = await sql_pers.list_runs()
        assert len(all_runs) == 3

    async def test_get_run_not_found(self, sql_pers) -> None:
        result = await sql_pers.get_run(uuid4())
        assert result is None


@pytest.mark.asyncio
class TestSQLStageCRUD:
    async def test_create_and_get_stage(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        stage = Stage(run_id=run.run_id, stage_type=StageType.RESEARCH)
        created = await sql_pers.create_stage(stage)
        assert created.stage_id == stage.stage_id

        fetched = await sql_pers.get_stage(stage.stage_id)
        assert fetched is not None
        assert fetched.stage_type == StageType.RESEARCH

    async def test_update_stage(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        stage = Stage(run_id=run.run_id, stage_type=StageType.RESEARCH)
        await sql_pers.create_stage(stage)
        stage.status = StageStatus.RUNNING
        stage.retry_count = 1
        await sql_pers.update_stage(stage)

        fetched = await sql_pers.get_stage(stage.stage_id)
        assert fetched.status == StageStatus.RUNNING
        assert fetched.retry_count == 1

    async def test_get_stages_for_run(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        s1 = Stage(run_id=run.run_id, stage_type=StageType.RESEARCH)
        s2 = Stage(run_id=run.run_id, stage_type=StageType.SCREENING)
        await sql_pers.create_stage(s1)
        await sql_pers.create_stage(s2)

        stages = await sql_pers.get_stages_for_run(run.run_id)
        assert len(stages) == 2
        types = {s.stage_type for s in stages}
        assert StageType.RESEARCH in types
        assert StageType.SCREENING in types


@pytest.mark.asyncio
class TestSQLApprovalCRUD:
    async def test_create_and_get_approval(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        stage = Stage(run_id=run.run_id)
        await sql_pers.create_stage(stage)
        approval = Approval(
            run_id=run.run_id,
            stage_id=stage.stage_id,
            approval_type=ApprovalType.MANUAL_REVIEW,
            decision=ApprovalDecision.PENDING,
        )
        created = await sql_pers.create_approval(approval)
        assert created.approval_id == approval.approval_id

        fetched = await sql_pers.get_approval(approval.approval_id)
        assert fetched is not None
        assert fetched.decision == ApprovalDecision.PENDING

    async def test_update_approval(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        stage = Stage(run_id=run.run_id)
        await sql_pers.create_stage(stage)
        approval = Approval(run_id=run.run_id, stage_id=stage.stage_id)
        await sql_pers.create_approval(approval)
        approval.decision = ApprovalDecision.APPROVED
        approval.decided_by = "admin@example.com"
        await sql_pers.update_approval(approval)

        fetched = await sql_pers.get_approval(approval.approval_id)
        assert fetched.decision == ApprovalDecision.APPROVED
        assert fetched.decided_by == "admin@example.com"

    async def test_get_approvals_for_run(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        stage = Stage(run_id=run.run_id)
        await sql_pers.create_stage(stage)
        a1 = Approval(run_id=run.run_id, stage_id=stage.stage_id)
        a2 = Approval(run_id=run.run_id, stage_id=stage.stage_id)
        await sql_pers.create_approval(a1)
        await sql_pers.create_approval(a2)

        approvals = await sql_pers.get_approvals_for_run(run.run_id)
        assert len(approvals) == 2


@pytest.mark.asyncio
class TestSQLEventCRUD:
    async def test_create_and_get_events(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        event = Event(
            run_id=run.run_id,
            event_type=EventType.RUN_CREATED,
            payload={"key": "value"},
        )
        await sql_pers.create_event(event)

        events = await sql_pers.get_events_for_run(run.run_id)
        assert len(events) == 1
        assert events[0].event_type == EventType.RUN_CREATED
        assert events[0].payload == {"key": "value"}


@pytest.mark.asyncio
class TestSQLArtifactCRUD:
    async def test_create_and_get_artifact(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        artifact = Artifact(
            run_id=run.run_id,
            artifact_type=ArtifactType.RESEARCH_BRIEF,
            payload={"claims": ["claim1"]},
            producer="gemini",
        )
        await sql_pers.create_artifact(artifact)

        fetched = await sql_pers.get_artifact(artifact.artifact_id)
        assert fetched is not None
        assert fetched.artifact_type == ArtifactType.RESEARCH_BRIEF
        assert fetched.producer == "gemini"

    async def test_get_artifacts_for_run(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        a1 = Artifact(run_id=run.run_id, artifact_type=ArtifactType.RESEARCH_BRIEF)
        a2 = Artifact(run_id=run.run_id, artifact_type=ArtifactType.EVIDENCE_PACKET)
        await sql_pers.create_artifact(a1)
        await sql_pers.create_artifact(a2)

        artifacts = await sql_pers.get_artifacts_for_run(run.run_id)
        assert len(artifacts) == 2


@pytest.mark.asyncio
class TestSQLErrorCRUD:
    async def test_create_and_get_errors(self, sql_pers) -> None:
        run = Run()
        await sql_pers.create_run(run)
        error = ErrorRecord(
            run_id=run.run_id,
            error_type="AgentTimeoutError",
            error_message="Request timed out",
            is_recoverable=True,
        )
        await sql_pers.create_error(error)

        errors = await sql_pers.get_errors_for_run(run.run_id)
        assert len(errors) == 1
        assert errors[0].error_type == "AgentTimeoutError"
        assert errors[0].is_recoverable is True


@pytest.mark.asyncio
class TestSQLRecovery:
    async def test_get_runs_to_recover(self, sql_pers) -> None:
        r1 = Run(status=RunStatus.RUNNING)
        r2 = Run(status=RunStatus.PAUSED)
        r3 = Run(status=RunStatus.COMPLETED)
        await sql_pers.create_run(r1)
        await sql_pers.create_run(r2)
        await sql_pers.create_run(r3)

        to_recover = await sql_pers.get_runs_to_recover()
        assert len(to_recover) == 2
        statuses = {r.status for r in to_recover}
        assert RunStatus.RUNNING in statuses
        assert RunStatus.PAUSED in statuses


@pytest.mark.asyncio
class TestSQLConfigurationCRUD:
    async def test_save_and_get_configuration(self, sql_pers) -> None:
        config = Configuration(
            config_id="campaign-1",
            config_data={"threshold": 85},
        )
        await sql_pers.save_configuration(config)

        fetched = await sql_pers.get_configuration("campaign-1")
        assert fetched is not None
        assert fetched.config_id == "campaign-1"
        assert fetched.config_data == {"threshold": 85}

    async def test_update_configuration(self, sql_pers) -> None:
        config = Configuration(config_id="campaign-1", config_data={"threshold": 85})
        await sql_pers.save_configuration(config)
        config.config_data = {"threshold": 90}
        await sql_pers.save_configuration(config)

        fetched = await sql_pers.get_configuration("campaign-1")
        assert fetched.config_data == {"threshold": 90}

    async def test_get_configuration_not_found(self, sql_pers) -> None:
        result = await sql_pers.get_configuration("nonexistent")
        assert result is None
