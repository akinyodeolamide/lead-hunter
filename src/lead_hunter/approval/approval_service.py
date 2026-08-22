"""Approval service for human-in-the-loop control.

Manages approval gates, human decisions, pause/resume, timeouts,
and recovery of waiting approvals.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from lead_hunter.exceptions import NotFoundError
from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.models.domain import (
    Approval,
    ApprovalDecision,
    ApprovalType,
    Event,
    EventType,
    Run,
    RunStatus,
    Stage,
    StageStatus,
)
from lead_hunter.orchestrator.state_machine import StateMachine

logger = get_logger("approval")


class ApprovalService:
    """Service for managing approval gates and human decisions."""

    def __init__(
        self,
        persistence: Any,
        stage_manager: Any,
        run_manager: Any,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.persistence = persistence
        self.stage_manager = stage_manager
        self.run_manager = run_manager
        self.config = config or {}
        self._default_timeout = self.config.get("approval_timeout_seconds", 86400)

    # ------------------------------------------------------------------
    # Create approval request
    # ------------------------------------------------------------------
    async def create_approval_request(
        self,
        run_id: UUID,
        stage_id: UUID,
        approval_type: ApprovalType = ApprovalType.MANUAL_REVIEW,
        request_details: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> Approval:
        """Create a new approval request.

        Sets the associated stage to WAITING_FOR_APPROVAL.
        """
        timeout = timeout_seconds or self._default_timeout
        deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout)

        approval = Approval(
            run_id=run_id,
            stage_id=stage_id,
            approval_type=approval_type,
            decision=ApprovalDecision.PENDING,
            request_details=request_details or {},
            deadline=deadline,
        )
        await self.persistence.create_approval(approval)

        # Set stage to waiting for approval
        stage = await self.persistence.get_stage(stage_id)
        if stage is not None:
            await self.stage_manager.request_approval(stage)

        log_event(
            logger,
            "INFO",
            f"Approval request created for run {run_id}, stage {stage_id}",
            run_id=run_id,
            stage_id=stage_id,
            context={
                "approval_id": str(approval.approval_id),
                "approval_type": approval_type.name,
                "deadline": deadline.isoformat(),
            },
        )
        await self.persistence.create_event(
            Event(
                run_id=run_id,
                stage_id=stage_id,
                event_type=EventType.APPROVAL_REQUESTED,
                payload={
                    "approval_id": str(approval.approval_id),
                    "approval_type": approval_type.name,
                    "deadline": deadline.isoformat(),
                    "request_details": request_details or {},
                },
            )
        )
        return approval

    # ------------------------------------------------------------------
    # Approve
    # ------------------------------------------------------------------
    async def approve(
        self,
        approval_id: UUID,
        decided_by: str,
        rationale: str | None = None,
    ) -> Approval:
        """Approve an approval request.

        Transitions the associated stage to COMPLETED.
        """
        approval = await self.persistence.get_approval(approval_id)
        if approval is None:
            raise NotFoundError(f"Approval {approval_id} not found")

        approval.decision = ApprovalDecision.APPROVED
        approval.decided_by = decided_by
        approval.decision_rationale = rationale or ""
        approval.decided_at = datetime.now(timezone.utc)
        await self.persistence.update_approval(approval)

        # Complete the associated stage
        stage = await self.persistence.get_stage(approval.stage_id)
        if stage is not None:
            await self.stage_manager.complete_stage(stage)

        log_event(
            logger,
            "INFO",
            f"Approval {approval_id} approved by {decided_by}",
            run_id=approval.run_id,
            stage_id=approval.stage_id,
            context={"rationale": rationale},
        )
        await self.persistence.create_event(
            Event(
                run_id=approval.run_id,
                stage_id=approval.stage_id,
                event_type=EventType.APPROVAL_DECIDED,
                payload={
                    "approval_id": str(approval_id),
                    "decision": "APPROVED",
                    "decided_by": decided_by,
                    "rationale": rationale,
                },
            )
        )
        return approval

    # ------------------------------------------------------------------
    # Reject
    # ------------------------------------------------------------------
    async def reject(
        self,
        approval_id: UUID,
        decided_by: str,
        rationale: str | None = None,
    ) -> Approval:
        """Reject an approval request.

        Transitions the associated stage to REJECTED and the run to REJECTED.
        """
        approval = await self.persistence.get_approval(approval_id)
        if approval is None:
            raise NotFoundError(f"Approval {approval_id} not found")

        approval.decision = ApprovalDecision.REJECTED
        approval.decided_by = decided_by
        approval.decision_rationale = rationale or ""
        approval.decided_at = datetime.now(timezone.utc)
        await self.persistence.update_approval(approval)

        # Reject the associated stage
        stage = await self.persistence.get_stage(approval.stage_id)
        if stage is not None:
            await self.stage_manager.reject_stage(
                stage, rationale or "Rejected at approval gate"
            )

        # Reject the run
        run = await self.persistence.get_run(approval.run_id)
        if run is not None:
            await self.run_manager.reject_run(
                run, rationale or "Rejected at approval gate"
            )

        log_event(
            logger,
            "INFO",
            f"Approval {approval_id} rejected by {decided_by}",
            run_id=approval.run_id,
            stage_id=approval.stage_id,
            context={"rationale": rationale},
        )
        await self.persistence.create_event(
            Event(
                run_id=approval.run_id,
                stage_id=approval.stage_id,
                event_type=EventType.APPROVAL_DECIDED,
                payload={
                    "approval_id": str(approval_id),
                    "decision": "REJECTED",
                    "decided_by": decided_by,
                    "rationale": rationale,
                },
            )
        )
        return approval

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------
    async def pause(self, run_id: UUID) -> Run:
        """Pause a run that is waiting for approval.

        Sets the run status to PAUSED and the approval decision to PAUSED.
        """
        run = await self.persistence.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")

        run.status = RunStatus.PAUSED
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)

        # Mark any pending approvals as paused
        approvals = await self.persistence.get_approvals_for_run(run_id)
        for approval in approvals:
            if approval.decision == ApprovalDecision.PENDING:
                approval.decision = ApprovalDecision.PAUSED
                await self.persistence.update_approval(approval)

        log_event(
            logger,
            "INFO",
            f"Run {run_id} paused",
            run_id=run_id,
        )
        await self.persistence.create_event(
            Event(
                run_id=run_id,
                event_type=EventType.RUN_PAUSED,
                payload={"reason": "Human pause request"},
            )
        )
        return run

    async def resume(self, run_id: UUID) -> Run:
        """Resume a paused run.

        Sets the run status back to RUNNING and restores pending approvals.
        """
        run = await self.persistence.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")

        run.status = RunStatus.RUNNING
        run.updated_at = datetime.now(timezone.utc)
        await self.persistence.update_run(run)

        # Restore paused approvals to pending
        approvals = await self.persistence.get_approvals_for_run(run_id)
        for approval in approvals:
            if approval.decision == ApprovalDecision.PAUSED:
                approval.decision = ApprovalDecision.PENDING
                await self.persistence.update_approval(approval)

        log_event(
            logger,
            "INFO",
            f"Run {run_id} resumed",
            run_id=run_id,
        )
        await self.persistence.create_event(
            Event(
                run_id=run_id,
                event_type=EventType.RUN_RESUMED,
                payload={"reason": "Human resume request"},
            )
        )
        return run

    # ------------------------------------------------------------------
    # Timeout handling
    # ------------------------------------------------------------------
    async def check_timeouts(self) -> list[Approval]:
        """Check for approvals that have exceeded their deadline.

        Auto-rejects timed-out approvals.
        Returns the list of approvals that were timed out.
        """
        now = datetime.now(timezone.utc)
        all_approvals = []
        # Collect all approvals from all runs — persistence doesn't have list_all
        # so we use get_approvals_for_run for each run we know about
        runs = await self.persistence.list_runs(limit=10000)
        timed_out: list[Approval] = []
        for run in runs:
            approvals = await self.persistence.get_approvals_for_run(run.run_id)
            for approval in approvals:
                if (
                    approval.decision == ApprovalDecision.PENDING
                    and approval.deadline is not None
                    and approval.deadline < now
                ):
                    timed_out.append(approval)

        for approval in timed_out:
            approval.decision = ApprovalDecision.TIMEOUT
            approval.decided_by = "system"
            approval.decision_rationale = "Approval deadline exceeded"
            approval.decided_at = now
            await self.persistence.update_approval(approval)

            # Reject the associated stage
            stage = await self.persistence.get_stage(approval.stage_id)
            if stage is not None:
                await self.stage_manager.reject_stage(
                    stage, "Approval timeout — auto-rejected"
                )

            # Reject the run
            run = await self.persistence.get_run(approval.run_id)
            if run is not None:
                await self.run_manager.reject_run(
                    run, "Approval timeout — auto-rejected"
                )

            log_event(
                logger,
                "WARNING",
                f"Approval {approval.approval_id} timed out and was auto-rejected",
                run_id=approval.run_id,
                stage_id=approval.stage_id,
            )
            await self.persistence.create_event(
                Event(
                    run_id=approval.run_id,
                    stage_id=approval.stage_id,
                    event_type=EventType.APPROVAL_DECIDED,
                    payload={
                        "approval_id": str(approval.approval_id),
                        "decision": "TIMEOUT",
                        "decided_by": "system",
                        "rationale": "Approval deadline exceeded",
                    },
                )
            )

        return timed_out

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    async def get_waiting_approvals(self) -> list[Approval]:
        """Return all approvals with PENDING decision."""
        runs = await self.persistence.list_runs(limit=10000)
        waiting: list[Approval] = []
        for run in runs:
            approvals = await self.persistence.get_approvals_for_run(run.run_id)
            for approval in approvals:
                if approval.decision == ApprovalDecision.PENDING:
                    waiting.append(approval)
        return waiting

    async def get_approvals_for_run(self, run_id: UUID) -> list[Approval]:
        """Return all approvals for a given run."""
        return await self.persistence.get_approvals_for_run(run_id)

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------
    async def recover_approval(self, approval_id: UUID) -> Approval | None:
        """Recover an approval after system restart.

        Returns the approval if it exists and is still pending,
        None otherwise.
        """
        approval = await self.persistence.get_approval(approval_id)
        if approval is None:
            return None
        if approval.decision != ApprovalDecision.PENDING:
            return None
        log_event(
            logger,
            "INFO",
            f"Approval {approval_id} recovered (still pending)",
            run_id=approval.run_id,
            stage_id=approval.stage_id,
        )
        return approval
