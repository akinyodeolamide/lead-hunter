"""Run lifecycle management."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.models.domain import Event, EventType, Run, RunStatus
from lead_hunter.orchestrator.state_machine import StateMachine

logger = get_logger("run_manager")


class RunManager:
    """Creates, tracks, and finalizes runs."""

    def __init__(self, persistence: Any) -> None:
        self.persistence = persistence

    async def create_run(
        self,
        configuration_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> Run:
        """Create a new run."""
        run = Run(
            status=RunStatus.PENDING,
            configuration_id=configuration_id,
            metadata=metadata or {},
        )
        await self.persistence.create_run(run)
        log_event(
            logger,
            "INFO",
            "Run created",
            run_id=run.run_id,
            correlation_id=run.correlation_id,
            context={"configuration_id": configuration_id},
        )
        await self.persistence.create_event(
            Event(
                run_id=run.run_id,
                event_type=EventType.RUN_CREATED,
                payload={"configuration_id": configuration_id},
                correlation_id=run.correlation_id,
            )
        )
        return run

    async def queue_run(self, run: Run) -> Run:
        """Mark a run as queued."""
        run.status = StateMachine.transition_run(run.status, RunStatus.QUEUED)
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)
        log_event(logger, "INFO", "Run queued", run_id=run.run_id, correlation_id=run.correlation_id)
        await self.persistence.create_event(
            Event(
                run_id=run.run_id,
                event_type=EventType.RUN_STARTED,  # reuse for queue
                correlation_id=run.correlation_id,
            )
        )
        return run

    async def start_run(self, run: Run) -> Run:
        """Mark a run as running."""
        run.status = StateMachine.transition_run(run.status, RunStatus.RUNNING)
        run.started_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)
        log_event(logger, "INFO", "Run started", run_id=run.run_id, correlation_id=run.correlation_id)
        await self.persistence.create_event(
            Event(
                run_id=run.run_id,
                event_type=EventType.RUN_STARTED,
                correlation_id=run.correlation_id,
            )
        )
        return run

    async def complete_run(self, run: Run) -> Run:
        """Mark a run as completed."""
        run.status = StateMachine.transition_run(run.status, RunStatus.COMPLETED)
        run.completed_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)
        log_event(logger, "INFO", "Run completed", run_id=run.run_id, correlation_id=run.correlation_id)
        await self.persistence.create_event(
            Event(
                run_id=run.run_id,
                event_type=EventType.RUN_COMPLETED,
                correlation_id=run.correlation_id,
            )
        )
        return run

    async def reject_run(self, run: Run, reason: str) -> Run:
        """Mark a run as rejected."""
        run.status = StateMachine.transition_run(run.status, RunStatus.REJECTED)
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)
        log_event(
            logger,
            "INFO",
            "Run rejected",
            run_id=run.run_id,
            correlation_id=run.correlation_id,
            context={"reason": reason},
        )
        await self.persistence.create_event(
            Event(
                run_id=run.run_id,
                event_type=EventType.RUN_REJECTED,
                payload={"reason": reason},
                correlation_id=run.correlation_id,
            )
        )
        return run

    async def fail_run(self, run: Run, error_message: str) -> Run:
        """Mark a run as failed."""
        run.status = StateMachine.transition_run(run.status, RunStatus.FAILED)
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)
        log_event(
            logger,
            "ERROR",
            "Run failed",
            run_id=run.run_id,
            correlation_id=run.correlation_id,
            context={"error": error_message},
        )
        await self.persistence.create_event(
            Event(
                run_id=run.run_id,
                event_type=EventType.RUN_FAILED,
                payload={"error": error_message},
                correlation_id=run.correlation_id,
            )
        )
        return run

    async def pause_run(self, run: Run) -> Run:
        """Pause a running run."""
        run.status = StateMachine.transition_run(run.status, RunStatus.PAUSED)
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)
        log_event(logger, "INFO", "Run paused", run_id=run.run_id, correlation_id=run.correlation_id)
        await self.persistence.create_event(
            Event(
                run_id=run.run_id,
                event_type=EventType.RUN_PAUSED,
                correlation_id=run.correlation_id,
            )
        )
        return run

    async def resume_run(self, run: Run) -> Run:
        """Resume a paused run."""
        run.status = StateMachine.transition_run(run.status, RunStatus.RUNNING)
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)
        log_event(logger, "INFO", "Run resumed", run_id=run.run_id, correlation_id=run.correlation_id)
        await self.persistence.create_event(
            Event(
                run_id=run.run_id,
                event_type=EventType.RUN_RESUMED,
                correlation_id=run.correlation_id,
            )
        )
        return run

    async def cancel_run(self, run: Run) -> Run:
        """Cancel a run."""
        run.status = StateMachine.transition_run(run.status, RunStatus.CANCELLED)
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)
        log_event(
            logger,
            "INFO",
            "Run cancelled",
            run_id=run.run_id,
            correlation_id=run.correlation_id,
        )
        await self.persistence.create_event(
            Event(
                run_id=run.run_id,
                event_type=EventType.RUN_CANCELLED,
                correlation_id=run.correlation_id,
            )
        )
        return run
