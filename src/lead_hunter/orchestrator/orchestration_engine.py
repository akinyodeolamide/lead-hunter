"""Core orchestration engine that coordinates workflow execution."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.models.domain import (
    Event,
    EventType,
    Run,
    RunStatus,
    Stage,
    StageStatus,
    StageType,
)
from lead_hunter.orchestrator.run_manager import RunManager
from lead_hunter.orchestrator.stage_manager import StageManager
from lead_hunter.orchestrator.state_machine import StateMachine

logger = get_logger("orchestration_engine")


class OrchestrationEngine:
    """Coordinates the lead hunter workflow from trigger to completion."""

    def __init__(
        self,
        persistence: Any,
        adapters: dict[str, Any] | None = None,
        scoring_engine: Any | None = None,
        delivery: Any | None = None,
    ) -> None:
        self.persistence = persistence
        self.run_manager = RunManager(persistence)
        self.stage_manager = StageManager(persistence)
        self.adapters = adapters or {}
        self.scoring_engine = scoring_engine
        self.delivery = delivery

    async def start_run(self, configuration_id: str = "default", metadata: dict[str, Any] | None = None) -> Run:
        """Create and start a new run, then execute the first stage."""
        run = await self.run_manager.create_run(configuration_id, metadata)
        run = await self.run_manager.queue_run(run)
        run = await self.run_manager.start_run(run)
        stage = await self.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=StageType.INIT,
        )
        stage = await self.stage_manager.start_stage(stage)
        stage = await self.stage_manager.complete_stage(stage)
        await self._advance_to_next_stage(run, StageType.INIT)
        return run

    async def _advance_to_next_stage(self, run: Run, current_stage_type: StageType) -> None:
        """Advance the run to the next stage in the workflow."""
        next_type = StateMachine.get_next_stage_type(current_stage_type)
        if next_type is None:
            if not StateMachine.is_run_terminal(run.status):
                await self.run_manager.complete_run(run)
            return

        if StateMachine.is_run_terminal(run.status):
            return

        stage = await self.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=next_type,
        )
        log_event(
            logger,
            "INFO",
            f"Advanced to stage {next_type.name}",
            run_id=run.run_id,
            stage_id=stage.stage_id,
        )

    async def approve_stage(self, stage: Stage, decided_by: str, rationale: str | None = None) -> Stage:
        """Approve a stage waiting for approval."""
        stage.status = StateMachine.transition_stage(stage.status, StageStatus.COMPLETED)
        await self.persistence.update_stage(stage)
        log_event(
            logger,
            "INFO",
            f"Stage {stage.stage_type.name} approved",
            run_id=stage.run_id,
            stage_id=stage.stage_id,
            context={"decided_by": decided_by},
        )
        await self.persistence.create_event(
            Event(
                run_id=stage.run_id,
                stage_id=stage.stage_id,
                event_type=EventType.APPROVAL_DECIDED,
                payload={"decision": "APPROVED", "decided_by": decided_by, "rationale": rationale},
            )
        )
        return stage

    async def reject_stage(self, stage: Stage, decided_by: str, rationale: str | None = None) -> Stage:
        """Reject a stage at approval gate."""
        stage = await self.stage_manager.reject_stage(stage, rationale or "Rejected at approval gate")
        run = await self.persistence.get_run(stage.run_id)
        if run and not StateMachine.is_run_terminal(run.status):
            await self.run_manager.reject_run(run, rationale or "Rejected at approval gate")
        return stage

    async def pause_run(self, run_id: UUID) -> Run | None:
        """Pause a running run."""
        run = await self.persistence.get_run(run_id)
        if not run:
            return None
        return await self.run_manager.pause_run(run)

    async def resume_run(self, run_id: UUID) -> Run | None:
        """Resume a paused run."""
        run = await self.persistence.get_run(run_id)
        if not run:
            return None
        return await self.run_manager.resume_run(run)

    async def cancel_run(self, run_id: UUID) -> Run | None:
        """Cancel a run."""
        run = await self.persistence.get_run(run_id)
        if not run:
            return None
        return await self.run_manager.cancel_run(run)

    async def retry_stage(self, stage_id: UUID) -> Stage | None:
        """Retry a failed stage."""
        stage = await self.persistence.get_stage(stage_id)
        if not stage:
            return None
        if stage.status != StageStatus.FAILED:
            raise ValueError(
                f"Stage {stage_id} is not in FAILED status (current: {stage.status.name})"
            )
        return await self.stage_manager.retry_stage(stage)
