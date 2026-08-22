"""SQL persistence adapter implementing the Persistence interface."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select

from lead_hunter.models.domain import (
    Approval,
    Artifact,
    Configuration,
    ErrorRecord,
    Event,
    Run,
    RunStatus,
    Stage,
)
from lead_hunter.orchestrator.interfaces import Persistence
from lead_hunter.persistence.database import DatabaseManager
from lead_hunter.persistence.orm_models import (
    ApprovalORM,
    ArtifactORM,
    CampaignORM,
    ConfigurationORM,
    ErrorORM,
    EventORM,
    RunORM,
    StageORM,
)


def _run_to_orm(run: Run) -> RunORM:
    return RunORM(
        run_id=run.run_id,
        status=run.status.name,
        configuration_id=run.configuration_id,
        correlation_id=run.correlation_id,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        metadata_json=run.metadata,
    )


def _run_from_orm(orm: RunORM) -> Run:
    return Run(
        run_id=orm.run_id,
        status=RunStatus[orm.status],
        configuration_id=orm.configuration_id,
        correlation_id=orm.correlation_id,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        started_at=orm.started_at,
        completed_at=orm.completed_at,
        metadata=orm.metadata_json,
    )


def _stage_to_orm(stage: Stage) -> StageORM:
    return StageORM(
        stage_id=stage.stage_id,
        run_id=stage.run_id,
        stage_type=stage.stage_type.name,
        status=stage.status.name,
        retry_count=stage.retry_count,
        max_retries=stage.max_retries,
        started_at=stage.started_at,
        completed_at=stage.completed_at,
        metadata_json=stage.metadata,
    )


def _stage_from_orm(orm: StageORM) -> Stage:
    from lead_hunter.models.domain import StageStatus, StageType
    return Stage(
        stage_id=orm.stage_id,
        run_id=orm.run_id,
        stage_type=StageType[orm.stage_type],
        status=StageStatus[orm.status],
        retry_count=orm.retry_count,
        max_retries=orm.max_retries,
        started_at=orm.started_at,
        completed_at=orm.completed_at,
        metadata=orm.metadata_json,
    )


def _approval_to_orm(approval: Approval) -> ApprovalORM:
    return ApprovalORM(
        approval_id=approval.approval_id,
        run_id=approval.run_id,
        stage_id=approval.stage_id,
        approval_type=approval.approval_type.name,
        decision=approval.decision.name,
        decided_by=approval.decided_by,
        request_details=approval.request_details,
        decision_rationale=approval.decision_rationale,
        deadline=approval.deadline,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
    )


def _approval_from_orm(orm: ApprovalORM) -> Approval:
    from lead_hunter.models.domain import ApprovalDecision, ApprovalType
    return Approval(
        approval_id=orm.approval_id,
        run_id=orm.run_id,
        stage_id=orm.stage_id,
        approval_type=ApprovalType[orm.approval_type],
        decision=ApprovalDecision[orm.decision],
        decided_by=orm.decided_by,
        request_details=orm.request_details,
        decision_rationale=orm.decision_rationale,
        deadline=orm.deadline,
        created_at=orm.created_at,
        decided_at=orm.decided_at,
    )


def _event_to_orm(event: Event) -> EventORM:
    return EventORM(
        event_id=event.event_id,
        run_id=event.run_id,
        stage_id=event.stage_id,
        event_type=event.event_type.name,
        payload=event.payload,
        timestamp=event.timestamp,
        correlation_id=event.correlation_id,
    )


def _event_from_orm(orm: EventORM) -> Event:
    from lead_hunter.models.domain import EventType
    return Event(
        event_id=orm.event_id,
        run_id=orm.run_id,
        stage_id=orm.stage_id,
        event_type=EventType[orm.event_type],
        payload=orm.payload,
        timestamp=orm.timestamp,
        correlation_id=orm.correlation_id,
    )


def _artifact_to_orm(artifact: Artifact) -> ArtifactORM:
    return ArtifactORM(
        artifact_id=artifact.artifact_id,
        run_id=artifact.run_id,
        artifact_type=artifact.artifact_type.name,
        schema_version=artifact.schema_version,
        payload=artifact.payload,
        producer=artifact.producer,
        created_at=artifact.created_at,
    )


def _artifact_from_orm(orm: ArtifactORM) -> Artifact:
    from lead_hunter.models.domain import ArtifactType
    return Artifact(
        artifact_id=orm.artifact_id,
        run_id=orm.run_id,
        artifact_type=ArtifactType[orm.artifact_type],
        schema_version=orm.schema_version,
        payload=orm.payload,
        producer=orm.producer,
        created_at=orm.created_at,
    )


def _error_to_orm(error: ErrorRecord) -> ErrorORM:
    return ErrorORM(
        error_id=error.error_id,
        run_id=error.run_id,
        stage_id=error.stage_id,
        error_type=error.error_type,
        error_message=error.error_message,
        stack_trace=error.stack_trace,
        is_recoverable=error.is_recoverable,
        recovery_attempted=error.recovery_attempted,
        created_at=error.created_at,
    )


def _error_from_orm(orm: ErrorORM) -> ErrorRecord:
    return ErrorRecord(
        error_id=orm.error_id,
        run_id=orm.run_id,
        stage_id=orm.stage_id,
        error_type=orm.error_type,
        error_message=orm.error_message,
        stack_trace=orm.stack_trace,
        is_recoverable=orm.is_recoverable,
        recovery_attempted=orm.recovery_attempted,
        created_at=orm.created_at,
    )


class SQLPersistence(Persistence):
    """SQLAlchemy-based persistence adapter."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    async def create_run(self, run: Run) -> Run:
        async with self.db.session() as sess:
            sess.add(_run_to_orm(run))
        return run

    async def get_run(self, run_id: UUID) -> Run | None:
        async with self.db.session() as sess:
            result = await sess.execute(select(RunORM).where(RunORM.run_id == run_id))
            orm = result.scalar_one_or_none()
            return _run_from_orm(orm) if orm else None

    async def update_run(self, run: Run) -> Run:
        async with self.db.session() as sess:
            existing = await sess.get(RunORM, run.run_id)
            if existing:
                existing.status = run.status.name
                existing.updated_at = run.updated_at
                existing.started_at = run.started_at
                existing.completed_at = run.completed_at
                existing.metadata_json = run.metadata
        return run

    async def list_runs(self, status: RunStatus | None = None, limit: int = 1000) -> list[Run]:
        async with self.db.session() as sess:
            stmt = select(RunORM)
            if status:
                stmt = stmt.where(RunORM.status == status.name)
            stmt = stmt.limit(limit)
            result = await sess.execute(stmt)
            return [_run_from_orm(r) for r in result.scalars().all()]

    async def create_stage(self, stage: Stage) -> Stage:
        async with self.db.session() as sess:
            sess.add(_stage_to_orm(stage))
        return stage

    async def get_stage(self, stage_id: UUID) -> Stage | None:
        async with self.db.session() as sess:
            result = await sess.execute(select(StageORM).where(StageORM.stage_id == stage_id))
            orm = result.scalar_one_or_none()
            return _stage_from_orm(orm) if orm else None

    async def update_stage(self, stage: Stage) -> Stage:
        async with self.db.session() as sess:
            existing = await sess.get(StageORM, stage.stage_id)
            if existing:
                existing.status = stage.status.name
                existing.retry_count = stage.retry_count
                existing.started_at = stage.started_at
                existing.completed_at = stage.completed_at
                existing.metadata_json = stage.metadata
        return stage

    async def get_stages_for_run(self, run_id: UUID) -> list[Stage]:
        async with self.db.session() as sess:
            result = await sess.execute(select(StageORM).where(StageORM.run_id == run_id))
            return [_stage_from_orm(s) for s in result.scalars().all()]

    async def create_approval(self, approval: Approval) -> Approval:
        async with self.db.session() as sess:
            sess.add(_approval_to_orm(approval))
        return approval

    async def get_approval(self, approval_id: UUID) -> Approval | None:
        async with self.db.session() as sess:
            result = await sess.execute(select(ApprovalORM).where(ApprovalORM.approval_id == approval_id))
            orm = result.scalar_one_or_none()
            return _approval_from_orm(orm) if orm else None

    async def update_approval(self, approval: Approval) -> Approval:
        async with self.db.session() as sess:
            existing = await sess.get(ApprovalORM, approval.approval_id)
            if existing:
                existing.decision = approval.decision.name
                existing.decided_by = approval.decided_by
                existing.decision_rationale = approval.decision_rationale
                existing.decided_at = approval.decided_at
        return approval

    async def get_approvals_for_run(self, run_id: UUID) -> list[Approval]:
        async with self.db.session() as sess:
            result = await sess.execute(select(ApprovalORM).where(ApprovalORM.run_id == run_id))
            return [_approval_from_orm(a) for a in result.scalars().all()]

    async def create_event(self, event: Event) -> Event:
        async with self.db.session() as sess:
            sess.add(_event_to_orm(event))
        return event

    async def get_events_for_run(self, run_id: UUID) -> list[Event]:
        async with self.db.session() as sess:
            result = await sess.execute(select(EventORM).where(EventORM.run_id == run_id))
            return [_event_from_orm(e) for e in result.scalars().all()]

    async def create_artifact(self, artifact: Artifact) -> Artifact:
        async with self.db.session() as sess:
            sess.add(_artifact_to_orm(artifact))
        return artifact

    async def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        async with self.db.session() as sess:
            result = await sess.execute(select(ArtifactORM).where(ArtifactORM.artifact_id == artifact_id))
            orm = result.scalar_one_or_none()
            return _artifact_from_orm(orm) if orm else None

    async def get_artifacts_for_run(self, run_id: UUID) -> list[Artifact]:
        async with self.db.session() as sess:
            result = await sess.execute(select(ArtifactORM).where(ArtifactORM.run_id == run_id))
            return [_artifact_from_orm(a) for a in result.scalars().all()]

    async def create_error(self, error: ErrorRecord) -> ErrorRecord:
        async with self.db.session() as sess:
            sess.add(_error_to_orm(error))
        return error

    async def get_errors_for_run(self, run_id: UUID) -> list[ErrorRecord]:
        async with self.db.session() as sess:
            result = await sess.execute(select(ErrorORM).where(ErrorORM.run_id == run_id))
            return [_error_from_orm(e) for e in result.scalars().all()]

    async def get_runs_to_recover(self) -> list[Run]:
        async with self.db.session() as sess:
            result = await sess.execute(
                select(RunORM).where(RunORM.status.in_(["RUNNING", "PAUSED"]))
            )
            return [_run_from_orm(r) for r in result.scalars().all()]

    async def get_configuration(self, config_id: str) -> Configuration | None:
        async with self.db.session() as sess:
            result = await sess.execute(select(ConfigurationORM).where(ConfigurationORM.config_id == config_id))
            orm = result.scalar_one_or_none()
            if orm:
                return Configuration(
                    config_id=orm.config_id,
                    config_data=orm.config_data,
                    created_at=orm.created_at,
                    updated_at=orm.updated_at,
                )
            return None

    async def save_configuration(self, config: Configuration) -> Configuration:
        async with self.db.session() as sess:
            existing = await sess.get(ConfigurationORM, config.config_id)
            if existing:
                existing.config_data = config.config_data
                existing.updated_at = config.updated_at
            else:
                sess.add(ConfigurationORM(
                    config_id=config.config_id,
                    config_data=config.config_data,
                    created_at=config.created_at,
                    updated_at=config.updated_at,
                ))
        return config

    # Campaign persistence
    async def save_campaign(self, campaign: Any) -> Any:
        from lead_hunter.scheduler.campaign import CampaignSchedule, CampaignStatus, ScheduleType
        async with self.db.session() as sess:
            existing = await sess.get(CampaignORM, campaign.campaign_id)
            if existing:
                existing.name = campaign.name
                existing.description = campaign.description
                existing.status = campaign.status.value
                existing.schedule_type = campaign.schedule_type.value
                existing.schedule_config = campaign.schedule_config
                existing.configuration_id = campaign.configuration_id
                existing.lead_name_template = campaign.lead_name_template
                existing.industry = campaign.industry
                existing.summary_template = campaign.summary_template
                existing.initial_claims = campaign.initial_claims
                existing.updated_at = campaign.updated_at
                existing.last_run_at = campaign.last_run_at
                existing.next_run_at = campaign.next_run_at
                existing.run_count = campaign.run_count
                existing.max_runs = campaign.max_runs
                existing.metadata_json = campaign.metadata
            else:
                sess.add(CampaignORM(
                    campaign_id=campaign.campaign_id,
                    name=campaign.name,
                    description=campaign.description,
                    status=campaign.status.value,
                    schedule_type=campaign.schedule_type.value,
                    schedule_config=campaign.schedule_config,
                    configuration_id=campaign.configuration_id,
                    lead_name_template=campaign.lead_name_template,
                    industry=campaign.industry,
                    summary_template=campaign.summary_template,
                    initial_claims=campaign.initial_claims,
                    created_at=campaign.created_at,
                    updated_at=campaign.updated_at,
                    last_run_at=campaign.last_run_at,
                    next_run_at=campaign.next_run_at,
                    run_count=campaign.run_count,
                    max_runs=campaign.max_runs,
                    metadata_json=campaign.metadata,
                ))
        return campaign

    async def get_campaign(self, campaign_id: UUID) -> Any | None:
        from lead_hunter.scheduler.campaign import CampaignSchedule, CampaignStatus, ScheduleType
        async with self.db.session() as sess:
            result = await sess.execute(select(CampaignORM).where(CampaignORM.campaign_id == campaign_id))
            orm = result.scalar_one_or_none()
            if orm:
                return CampaignSchedule(
                    campaign_id=orm.campaign_id,
                    name=orm.name,
                    description=orm.description,
                    status=CampaignStatus(orm.status),
                    schedule_type=ScheduleType(orm.schedule_type),
                    schedule_config=orm.schedule_config,
                    configuration_id=orm.configuration_id,
                    lead_name_template=orm.lead_name_template,
                    industry=orm.industry,
                    summary_template=orm.summary_template,
                    initial_claims=orm.initial_claims,
                    created_at=orm.created_at,
                    updated_at=orm.updated_at,
                    last_run_at=orm.last_run_at,
                    next_run_at=orm.next_run_at,
                    run_count=orm.run_count,
                    max_runs=orm.max_runs,
                    metadata=orm.metadata_json,
                )
            return None

    async def list_campaigns(self) -> list[Any]:
        from lead_hunter.scheduler.campaign import CampaignSchedule, CampaignStatus, ScheduleType
        async with self.db.session() as sess:
            result = await sess.execute(select(CampaignORM))
            campaigns = []
            for orm in result.scalars().all():
                campaigns.append(CampaignSchedule(
                    campaign_id=orm.campaign_id,
                    name=orm.name,
                    description=orm.description,
                    status=CampaignStatus(orm.status),
                    schedule_type=ScheduleType(orm.schedule_type),
                    schedule_config=orm.schedule_config,
                    configuration_id=orm.configuration_id,
                    lead_name_template=orm.lead_name_template,
                    industry=orm.industry,
                    summary_template=orm.summary_template,
                    initial_claims=orm.initial_claims,
                    created_at=orm.created_at,
                    updated_at=orm.updated_at,
                    last_run_at=orm.last_run_at,
                    next_run_at=orm.next_run_at,
                    run_count=orm.run_count,
                    max_runs=orm.max_runs,
                    metadata=orm.metadata_json,
                ))
            return campaigns

    async def delete_campaign(self, campaign_id: UUID) -> bool:
        async with self.db.session() as sess:
            orm = await sess.get(CampaignORM, campaign_id)
            if orm:
                await sess.delete(orm)
                return True
            return False
