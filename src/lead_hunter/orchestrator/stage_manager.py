"""Stage lifecycle management."""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.models.domain import Event, EventType, Stage, StageStatus, StageType
from lead_hunter.orchestrator.state_machine import StateMachine

logger = get_logger("stage_manager")


class StageManager:
    """Executes, transitions, and retries stages."""

    def __init__(self, persistence: Any) -> None:
        self.persistence = persistence

    async def create_stage(
        self,
        run_id: UUID,
        stage_type: StageType,
        max_retries: int = 3,
        metadata: dict[str, Any] | None = None,
    ) -> Stage:
        """Create a new stage for a run."""
        stage = Stage(
            run_id=run_id,
            stage_type=stage_type,
            status=StageStatus.PENDING,
            max_retries=max_retries,
            metadata=metadata or {},
        )
        await self.persistence.create_stage(stage)
        return stage

    async def start_stage(self, stage: Stage) -> Stage:
        """Mark a stage as running."""
        stage.status = StateMachine.transition_stage(stage.status, StageStatus.RUNNING)
        stage.started_at = datetime.now(timezone.utc)
        await self.persistence.update_stage(stage)
        log_event(
            logger,
            "INFO",
            f"Stage {stage.stage_type.name} started",
            run_id=stage.run_id,
            stage_id=stage.stage_id,
        )
        await self.persistence.create_event(
            Event(
                run_id=stage.run_id,
                stage_id=stage.stage_id,
                event_type=EventType.STAGE_STARTED,
                payload={"stage_type": stage.stage_type.name},
            )
        )
        return stage

    async def complete_stage(self, stage: Stage) -> Stage:
        """Mark a stage as completed."""
        stage.status = StateMachine.transition_stage(stage.status, StageStatus.COMPLETED)
        stage.completed_at = datetime.now(timezone.utc)
        await self.persistence.update_stage(stage)
        log_event(
            logger,
            "INFO",
            f"Stage {stage.stage_type.name} completed",
            run_id=stage.run_id,
            stage_id=stage.stage_id,
        )
        await self.persistence.create_event(
            Event(
                run_id=stage.run_id,
                stage_id=stage.stage_id,
                event_type=EventType.STAGE_COMPLETED,
                payload={"stage_type": stage.stage_type.name},
            )
        )
        return stage

    async def fail_stage(self, stage: Stage, error_message: str) -> Stage:
        """Mark a stage as failed. May trigger retry."""
        stage.status = StateMachine.transition_stage(stage.status, StageStatus.FAILED)
        await self.persistence.update_stage(stage)
        log_event(
            logger,
            "ERROR",
            f"Stage {stage.stage_type.name} failed",
            run_id=stage.run_id,
            stage_id=stage.stage_id,
            context={"error": error_message, "retry_count": stage.retry_count},
        )
        await self.persistence.create_event(
            Event(
                run_id=stage.run_id,
                stage_id=stage.stage_id,
                event_type=EventType.STAGE_FAILED,
                payload={"error": error_message, "retry_count": stage.retry_count},
            )
        )
        return stage

    async def retry_stage(self, stage: Stage, base_delay: float = 2.0, max_delay: float = 60.0) -> Stage:
        """Reset a failed stage for retry with exponential backoff + jitter."""
        if stage.retry_count >= stage.max_retries:
            log_event(
                logger,
                "ERROR",
                f"Stage {stage.stage_type.name} max retries exceeded",
                run_id=stage.run_id,
                stage_id=stage.stage_id,
            )
            return stage

        delay = min(base_delay * (2 ** stage.retry_count), max_delay)
        jitter = random.uniform(0, delay * 0.1)
        total_delay = delay + jitter

        stage.status = StateMachine.transition_stage(stage.status, StageStatus.PENDING)
        stage.retry_count += 1
        await self.persistence.update_stage(stage)

        log_event(
            logger,
            "INFO",
            f"Stage {stage.stage_type.name} scheduled for retry",
            run_id=stage.run_id,
            stage_id=stage.stage_id,
            context={
                "attempt": stage.retry_count,
                "backoff_seconds": round(total_delay, 2),
            },
        )
        await self.persistence.create_event(
            Event(
                run_id=stage.run_id,
                stage_id=stage.stage_id,
                event_type=EventType.STAGE_RETRIED,
                payload={
                    "attempt": stage.retry_count,
                    "backoff_seconds": round(total_delay, 2),
                },
            )
        )
        return stage

    async def skip_stage(self, stage: Stage) -> Stage:
        """Mark a stage as skipped."""
        stage.status = StateMachine.transition_stage(stage.status, StageStatus.SKIPPED)
        await self.persistence.update_stage(stage)
        log_event(
            logger,
            "INFO",
            f"Stage {stage.stage_type.name} skipped",
            run_id=stage.run_id,
            stage_id=stage.stage_id,
        )
        await self.persistence.create_event(
            Event(
                run_id=stage.run_id,
                stage_id=stage.stage_id,
                event_type=EventType.STAGE_SKIPPED,
                payload={"stage_type": stage.stage_type.name},
            )
        )
        return stage

    async def request_approval(self, stage: Stage) -> Stage:
        """Set stage to waiting for approval."""
        stage.status = StateMachine.transition_stage(
            stage.status, StageStatus.WAITING_FOR_APPROVAL
        )
        await self.persistence.update_stage(stage)
        log_event(
            logger,
            "INFO",
            f"Stage {stage.stage_type.name} waiting for approval",
            run_id=stage.run_id,
            stage_id=stage.stage_id,
        )
        await self.persistence.create_event(
            Event(
                run_id=stage.run_id,
                stage_id=stage.stage_id,
                event_type=EventType.APPROVAL_REQUESTED,
                payload={"stage_type": stage.stage_type.name},
            )
        )
        return stage

    async def reject_stage(self, stage: Stage, reason: str) -> Stage:
        """Mark a stage as rejected."""
        stage.status = StateMachine.transition_stage(stage.status, StageStatus.REJECTED)
        await self.persistence.update_stage(stage)
        log_event(
            logger,
            "INFO",
            f"Stage {stage.stage_type.name} rejected",
            run_id=stage.run_id,
            stage_id=stage.stage_id,
            context={"reason": reason},
        )
        await self.persistence.create_event(
            Event(
                run_id=stage.run_id,
                stage_id=stage.stage_id,
                event_type=EventType.STAGE_REJECTED,
                payload={"reason": reason},
            )
        )
        return stage
