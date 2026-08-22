"""Crash/restart recovery service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.models.domain import Event, EventType, RunStatus, StageStatus
from lead_hunter.orchestrator.state_machine import StateMachine

logger = get_logger("recovery")


class RecoveryService:
    """Inspects persisted state on startup and resumes in-flight runs."""

    def __init__(self, persistence: Any, engine: Any) -> None:
        self.persistence = persistence
        self.engine = engine

    async def recover(self) -> list[Any]:
        """Recover all runs that need resumption after restart."""
        runs = await self.persistence.get_runs_to_recover()
        recovered = []
        for run in runs:
            try:
                await self._recover_run(run)
                recovered.append(run)
            except Exception as exc:
                log_event(
                    logger,
                    "ERROR",
                    f"Failed to recover run {run.run_id}",
                    run_id=run.run_id,
                    context={"error": str(exc)},
                )
        return recovered

    async def _recover_run(self, run: Any) -> None:
        """Recover a single run."""
        stages = await self.persistence.get_stages_for_run(run.run_id)
        if not stages:
            run.status = RunStatus.PENDING
            await self.persistence.update_run(run)
            log_event(
                logger,
                "INFO",
                f"Run {run.run_id} reset to PENDING (no stages found)",
                run_id=run.run_id,
            )
            await self.persistence.create_event(
                Event(
                    run_id=run.run_id,
                    event_type=EventType.RECOVERY_ACTION,
                    payload={"action": "reset_to_pending", "reason": "no_stages"},
                )
            )
            return

        current_stage = None
        for stage in reversed(stages):
            if not StateMachine.is_stage_terminal(stage.status):
                current_stage = stage
                break

        if not current_stage:
            if not StateMachine.is_run_terminal(run.status):
                run.status = RunStatus.COMPLETED
                await self.persistence.update_run(run)
                log_event(
                    logger,
                    "INFO",
                    f"Run {run.run_id} marked COMPLETED (all stages terminal)",
                    run_id=run.run_id,
                )
            return

        if current_stage.status == StageStatus.RUNNING:
            current_stage.status = StageStatus.PENDING
            await self.persistence.update_stage(current_stage)
            log_event(
                logger,
                "INFO",
                f"Stage {current_stage.stage_id} reset to PENDING for replay",
                run_id=run.run_id,
                stage_id=current_stage.stage_id,
            )
            await self.persistence.create_event(
                Event(
                    run_id=run.run_id,
                    stage_id=current_stage.stage_id,
                    event_type=EventType.RECOVERY_ACTION,
                    payload={"action": "reset_stage_to_pending", "stage_type": current_stage.stage_type.name},
                )
            )

        elif current_stage.status == StageStatus.WAITING_FOR_APPROVAL:
            # Check if approval has timed out (only if engine is available)
            if self.engine is not None:
                from lead_hunter.approval.approval_service import ApprovalService
                approval_svc = ApprovalService(
                    self.persistence, self.engine.stage_manager, self.engine.run_manager
                )
                approvals = await self.persistence.get_approvals_for_run(run.run_id)
                stage_approval = None
                for approval in approvals:
                    if approval.stage_id == current_stage.stage_id:
                        stage_approval = approval
                        break

                if stage_approval and stage_approval.decision.name == "PENDING":
                    if stage_approval.deadline and stage_approval.deadline < datetime.now(timezone.utc):
                        await approval_svc.check_timeouts()
                        log_event(
                            logger,
                            "WARNING",
                            f"Run {run.run_id} approval timed out during recovery — auto-rejected",
                            run_id=run.run_id,
                            stage_id=current_stage.stage_id,
                        )
                        await self.persistence.create_event(
                            Event(
                                run_id=run.run_id,
                                stage_id=current_stage.stage_id,
                                event_type=EventType.RECOVERY_ACTION,
                                payload={
                                    "action": "approval_timeout_auto_rejected",
                                    "stage_type": current_stage.stage_type.name,
                                    "approval_id": str(stage_approval.approval_id),
                                },
                            )
                        )
                        return

            log_event(
                logger,
                "INFO",
                f"Run {run.run_id} restored at approval gate",
                run_id=run.run_id,
                stage_id=current_stage.stage_id,
            )
            await self.persistence.create_event(
                Event(
                    run_id=run.run_id,
                    stage_id=current_stage.stage_id,
                    event_type=EventType.RECOVERY_ACTION,
                    payload={"action": "restore_approval_gate", "stage_type": current_stage.stage_type.name},
                )
            )

        elif current_stage.status == StageStatus.PENDING:
            log_event(
                logger,
                "INFO",
                f"Run {run.run_id} has pending stage, ready to resume",
                run_id=run.run_id,
                stage_id=current_stage.stage_id,
            )
