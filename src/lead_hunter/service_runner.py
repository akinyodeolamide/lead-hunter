"""Service runner for autonomous Lead Hunter operation.

Orchestrates scheduler, auto-continuation, recovery, and graceful shutdown.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from lead_hunter.approval.approval_service import ApprovalService
from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.models.domain import RunStatus, StageStatus, StageType
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.factory import create_persistence_sync
from lead_hunter.recovery.recovery_service import RecoveryService
from lead_hunter.scheduler.scheduler_service import SchedulerService
from lead_hunter.shutdown import ShutdownHandler
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow

logger = get_logger("service_runner")


class ServiceRunner:
    """Long-running service that manages scheduled workflows, auto-continuation,
    recovery, and graceful shutdown.
    """

    def __init__(
        self,
        persistence: Any | None = None,
        engine: Any | None = None,
        check_interval: float = 5.0,
    ) -> None:
        self.persistence = persistence or create_persistence_sync()
        self.engine = engine or OrchestrationEngine(self.persistence)
        self.check_interval = check_interval
        self.shutdown_handler = ShutdownHandler()
        self.scheduler: SchedulerService | None = None
        self.approval_service = ApprovalService(
            self.persistence, self.engine.stage_manager, self.engine.run_manager
        )
        self._task: asyncio.Task[Any] | None = None

    def _workflow_factory(self) -> LeadHunterWorkflow:
        """Create a fresh workflow instance."""
        return LeadHunterWorkflow(
            self.engine,
            approval_service=self.approval_service,
            config={"screening_min_evidence": 1},
        )

    async def start(self) -> None:
        """Start the service: recovery, scheduler, and main loop."""
        self.shutdown_handler.install_signal_handlers()
        self.shutdown_handler.register_cleanup(self._cleanup)

        # Recovery on startup
        await self._run_recovery()

        # Start scheduler
        self.scheduler = SchedulerService(
            self.persistence,
            self.engine,
            self._workflow_factory,
        )
        await self.scheduler.start()

        # Start main loop
        self._task = asyncio.create_task(self._main_loop())
        log_event(logger, "INFO", "Service runner started")

    async def run_forever(self) -> None:
        """Block until shutdown signal."""
        await self.start()
        await self.shutdown_handler.wait_for_shutdown()
        await self.stop()

    async def stop(self) -> None:
        """Stop the service gracefully."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.scheduler is not None:
            await self.scheduler.shutdown()
        await self.shutdown_handler.shutdown()
        log_event(logger, "INFO", "Service runner stopped")

    async def _main_loop(self) -> None:
        """Main service loop: check for runs needing continuation."""
        try:
            while not self.shutdown_handler.is_shutting_down:
                try:
                    await self._check_timeouts()
                    await self._continue_runs()
                except Exception as exc:
                    log_event(logger, "ERROR", f"Error in main loop: {exc}")
                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            log_event(logger, "INFO", "Main loop cancelled")
            raise

    async def _run_recovery(self) -> None:
        """Run recovery on startup."""
        recovery = RecoveryService(self.persistence, self.engine)
        try:
            recovered = await recovery.recover()
            log_event(
                logger,
                "INFO",
                f"Recovery completed: {len(recovered)} runs recovered",
            )
        except Exception as exc:
            log_event(logger, "ERROR", f"Recovery failed: {exc}")

    async def _check_timeouts(self) -> None:
        """Check for timed-out approvals."""
        try:
            timed_out = await self.approval_service.check_timeouts()
            if timed_out:
                log_event(
                    logger,
                    "WARNING",
                    f"Auto-rejected {len(timed_out)} timed-out approvals",
                )
        except Exception as exc:
            log_event(logger, "ERROR", f"Timeout check failed: {exc}")

    async def _continue_runs(self) -> None:
        """Detect and continue runs that are waiting for approval/resume."""
        try:
            runs = await self.persistence.list_runs(status=RunStatus.RUNNING, limit=1000)
            for run in runs:
                stages = await self.persistence.get_stages_for_run(run.run_id)
                if not stages:
                    continue
                current_stage = max(stages, key=lambda s: s.started_at or s.created_at)

                # If the latest stage is COMPLETED and it's APPROVAL, continue to delivery
                if (
                    current_stage.status == StageStatus.COMPLETED
                    and current_stage.stage_type == StageType.APPROVAL
                ):
                    log_event(
                        logger,
                        "INFO",
                        f"Continuing run {run.run_id} after approval",
                        run_id=run.run_id,
                    )
                    workflow = self._workflow_factory()
                    # Get lead name from run metadata
                    lead_name = run.metadata.get("lead_name", "unknown")
                    industry = run.metadata.get("industry", "")
                    summary = run.metadata.get("summary", "")
                    await workflow.continue_run(
                        run=run,
                        lead_name=lead_name,
                        industry=industry,
                        summary=summary,
                    )
        except Exception as exc:
            log_event(logger, "ERROR", f"Continue runs failed: {exc}")

    async def _cleanup(self) -> None:
        """Cleanup tasks on shutdown."""
        log_event(logger, "INFO", "Service cleanup complete")
