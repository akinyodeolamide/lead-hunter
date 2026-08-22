"""Deterministic workflow state machine for Lead Hunter."""
from __future__ import annotations

from typing import TYPE_CHECKING

from lead_hunter.exceptions import StateMachineError
from lead_hunter.models.domain import RunStatus, StageStatus, StageType

if TYPE_CHECKING:
    from uuid import UUID


# Valid run status transitions: current -> {allowed next statuses}
RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PENDING: {RunStatus.QUEUED, RunStatus.CANCELLED},
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {
        RunStatus.PAUSED,
        RunStatus.REJECTED,
        RunStatus.FAILED,
        RunStatus.COMPLETED,
        RunStatus.CANCELLED,
    },
    RunStatus.PAUSED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.REJECTED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
    RunStatus.COMPLETED: set(),
}

# Valid stage status transitions
STAGE_TRANSITIONS: dict[StageStatus, set[StageStatus]] = {
    StageStatus.PENDING: {StageStatus.RUNNING, StageStatus.SKIPPED},
    StageStatus.RUNNING: {
        StageStatus.COMPLETED,
        StageStatus.FAILED,
        StageStatus.WAITING_FOR_APPROVAL,
        StageStatus.REJECTED,
        StageStatus.SKIPPED,
    },
    StageStatus.COMPLETED: set(),
    StageStatus.FAILED: {StageStatus.PENDING},
    StageStatus.WAITING_FOR_APPROVAL: {
        StageStatus.COMPLETED,
        StageStatus.REJECTED,
        StageStatus.PENDING,
    },
    StageStatus.REJECTED: set(),
    StageStatus.SKIPPED: set(),
}

# Workflow stage ordering
WORKFLOW_STAGES: list[StageType] = [
    StageType.INIT,
    StageType.RESEARCH,
    StageType.SCREENING,
    StageType.DEEP_RESEARCH,
    StageType.AUDIT,
    StageType.SCORING,
    StageType.APPROVAL,
    StageType.DELIVERY,
    StageType.FINALIZATION,
]


class StateMachine:
    """Deterministic state machine for run and stage transitions."""

    @staticmethod
    def can_transition_run(current: RunStatus, next_status: RunStatus) -> bool:
        """Check if a run status transition is valid."""
        if next_status == current:
            return True
        allowed = RUN_TRANSITIONS.get(current, set())
        return next_status in allowed

    @staticmethod
    def transition_run(current: RunStatus, next_status: RunStatus) -> RunStatus:
        """Execute a run status transition or raise."""
        if not StateMachine.can_transition_run(current, next_status):
            raise StateMachineError(
                f"Invalid run transition: {current.name} -> {next_status.name}"
            )
        return next_status

    @staticmethod
    def can_transition_stage(current: StageStatus, next_status: StageStatus) -> bool:
        """Check if a stage status transition is valid."""
        if next_status == current:
            return True
        allowed = STAGE_TRANSITIONS.get(current, set())
        return next_status in allowed

    @staticmethod
    def transition_stage(current: StageStatus, next_status: StageStatus) -> StageStatus:
        """Execute a stage status transition or raise."""
        if not StateMachine.can_transition_stage(current, next_status):
            raise StateMachineError(
                f"Invalid stage transition: {current.name} -> {next_status.name}"
            )
        return next_status

    @staticmethod
    def get_next_stage_type(current: StageType) -> StageType | None:
        """Get the next stage type in the workflow sequence."""
        try:
            idx = WORKFLOW_STAGES.index(current)
            if idx + 1 < len(WORKFLOW_STAGES):
                return WORKFLOW_STAGES[idx + 1]
        except ValueError:
            pass
        return None

    @staticmethod
    def is_run_terminal(status: RunStatus) -> bool:
        """Check if a run status is terminal."""
        return status in {
            RunStatus.REJECTED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.COMPLETED,
        }

    @staticmethod
    def is_stage_terminal(status: StageStatus) -> bool:
        """Check if a stage status is terminal."""
        return status in {
            StageStatus.COMPLETED,
            StageStatus.REJECTED,
            StageStatus.SKIPPED,
        }
