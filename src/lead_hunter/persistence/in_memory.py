"""In-memory persistence adapter for testing."""
from __future__ import annotations

from typing import Any
from uuid import UUID

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


class InMemoryPersistence(Persistence):
    """In-memory implementation of the Persistence interface."""

    def __init__(self) -> None:
        self._runs: dict[UUID, Run] = {}
        self._stages: dict[UUID, Stage] = {}
        self._approvals: dict[UUID, Approval] = {}
        self._events: dict[UUID, list[Event]] = {}
        self._artifacts: dict[UUID, Artifact] = {}
        self._errors: dict[UUID, list[ErrorRecord]] = {}
        self._configs: dict[str, Configuration] = {}
        self._campaigns: dict[UUID, Any] = {}

    async def create_run(self, run: Run) -> Run:
        self._runs[run.run_id] = run
        return run

    async def get_run(self, run_id: UUID) -> Run | None:
        return self._runs.get(run_id)

    async def update_run(self, run: Run) -> Run:
        self._runs[run.run_id] = run
        return run

    async def list_runs(self, status: RunStatus | None = None, limit: int = 1000) -> list[Run]:
        runs = list(self._runs.values())
        if status:
            runs = [r for r in runs if r.status == status]
        return runs[:limit]

    async def create_stage(self, stage: Stage) -> Stage:
        self._stages[stage.stage_id] = stage
        return stage

    async def get_stage(self, stage_id: UUID) -> Stage | None:
        return self._stages.get(stage_id)

    async def update_stage(self, stage: Stage) -> Stage:
        self._stages[stage.stage_id] = stage
        return stage

    async def get_stages_for_run(self, run_id: UUID) -> list[Stage]:
        return [s for s in self._stages.values() if s.run_id == run_id]

    async def create_approval(self, approval: Approval) -> Approval:
        self._approvals[approval.approval_id] = approval
        return approval

    async def get_approval(self, approval_id: UUID) -> Approval | None:
        return self._approvals.get(approval_id)

    async def update_approval(self, approval: Approval) -> Approval:
        self._approvals[approval.approval_id] = approval
        return approval

    async def get_approvals_for_run(self, run_id: UUID) -> list[Approval]:
        return [a for a in self._approvals.values() if a.run_id == run_id]

    async def create_event(self, event: Event) -> Event:
        self._events.setdefault(event.run_id or UUID(int=0), []).append(event)
        return event

    async def get_events_for_run(self, run_id: UUID) -> list[Event]:
        return self._events.get(run_id, [])

    async def create_artifact(self, artifact: Artifact) -> Artifact:
        self._artifacts[artifact.artifact_id] = artifact
        return artifact

    async def get_artifact(self, artifact_id: UUID) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    async def get_artifacts_for_run(self, run_id: UUID) -> list[Artifact]:
        return [a for a in self._artifacts.values() if a.run_id == run_id]

    async def create_error(self, error: ErrorRecord) -> ErrorRecord:
        self._errors.setdefault(error.run_id or UUID(int=0), []).append(error)
        return error

    async def get_errors_for_run(self, run_id: UUID) -> list[ErrorRecord]:
        return self._errors.get(run_id, [])

    async def get_runs_to_recover(self) -> list[Run]:
        return [
            r for r in self._runs.values()
            if r.status in {RunStatus.RUNNING, RunStatus.PAUSED}
        ]

    async def get_configuration(self, config_id: str) -> Configuration | None:
        return self._configs.get(config_id)

    async def save_configuration(self, config: Configuration) -> Configuration:
        self._configs[config.config_id] = config
        return config

    # Campaign persistence for scheduler recovery
    async def save_campaign(self, campaign: Any) -> Any:
        self._campaigns[campaign.campaign_id] = campaign
        return campaign

    async def get_campaign(self, campaign_id: UUID) -> Any | None:
        return self._campaigns.get(campaign_id)

    async def list_campaigns(self) -> list[Any]:
        return list(self._campaigns.values())

    async def delete_campaign(self, campaign_id: UUID) -> bool:
        if campaign_id in self._campaigns:
            del self._campaigns[campaign_id]
            return True
        return False
