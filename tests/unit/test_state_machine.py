"""Unit tests for state machine."""
from __future__ import annotations

import pytest

from lead_hunter.exceptions import StateMachineError
from lead_hunter.models.domain import RunStatus, StageStatus, StageType
from lead_hunter.orchestrator.state_machine import StateMachine


class TestRunTransitions:
    def test_pending_to_queued(self) -> None:
        assert StateMachine.can_transition_run(RunStatus.PENDING, RunStatus.QUEUED)

    def test_pending_to_cancelled(self) -> None:
        assert StateMachine.can_transition_run(RunStatus.PENDING, RunStatus.CANCELLED)

    def test_pending_to_running_invalid(self) -> None:
        assert not StateMachine.can_transition_run(RunStatus.PENDING, RunStatus.RUNNING)

    def test_queued_to_running(self) -> None:
        assert StateMachine.can_transition_run(RunStatus.QUEUED, RunStatus.RUNNING)

    def test_running_to_completed(self) -> None:
        assert StateMachine.can_transition_run(RunStatus.RUNNING, RunStatus.COMPLETED)

    def test_running_to_paused(self) -> None:
        assert StateMachine.can_transition_run(RunStatus.RUNNING, RunStatus.PAUSED)

    def test_running_to_rejected(self) -> None:
        assert StateMachine.can_transition_run(RunStatus.RUNNING, RunStatus.REJECTED)

    def test_running_to_failed(self) -> None:
        assert StateMachine.can_transition_run(RunStatus.RUNNING, RunStatus.FAILED)

    def test_completed_is_terminal(self) -> None:
        assert not StateMachine.can_transition_run(RunStatus.COMPLETED, RunStatus.RUNNING)

    def test_rejected_is_terminal(self) -> None:
        assert not StateMachine.can_transition_run(RunStatus.REJECTED, RunStatus.RUNNING)

    def test_same_status_idempotent(self) -> None:
        assert StateMachine.can_transition_run(RunStatus.RUNNING, RunStatus.RUNNING)

    def test_invalid_transition_raises(self) -> None:
        with pytest.raises(StateMachineError):
            StateMachine.transition_run(RunStatus.PENDING, RunStatus.COMPLETED)

    def test_is_run_terminal(self) -> None:
        assert StateMachine.is_run_terminal(RunStatus.COMPLETED)
        assert StateMachine.is_run_terminal(RunStatus.REJECTED)
        assert StateMachine.is_run_terminal(RunStatus.FAILED)
        assert StateMachine.is_run_terminal(RunStatus.CANCELLED)
        assert not StateMachine.is_run_terminal(RunStatus.RUNNING)


class TestStageTransitions:
    def test_pending_to_running(self) -> None:
        assert StateMachine.can_transition_stage(StageStatus.PENDING, StageStatus.RUNNING)

    def test_running_to_completed(self) -> None:
        assert StateMachine.can_transition_stage(StageStatus.RUNNING, StageStatus.COMPLETED)

    def test_running_to_failed(self) -> None:
        assert StateMachine.can_transition_stage(StageStatus.RUNNING, StageStatus.FAILED)

    def test_running_to_waiting(self) -> None:
        assert StateMachine.can_transition_stage(StageStatus.RUNNING, StageStatus.WAITING_FOR_APPROVAL)

    def test_running_to_rejected(self) -> None:
        assert StateMachine.can_transition_stage(StageStatus.RUNNING, StageStatus.REJECTED)

    def test_failed_to_pending_retry(self) -> None:
        assert StateMachine.can_transition_stage(StageStatus.FAILED, StageStatus.PENDING)

    def test_waiting_to_completed(self) -> None:
        assert StateMachine.can_transition_stage(StageStatus.WAITING_FOR_APPROVAL, StageStatus.COMPLETED)

    def test_waiting_to_rejected(self) -> None:
        assert StateMachine.can_transition_stage(StageStatus.WAITING_FOR_APPROVAL, StageStatus.REJECTED)

    def test_waiting_to_pending_pause(self) -> None:
        assert StateMachine.can_transition_stage(StageStatus.WAITING_FOR_APPROVAL, StageStatus.PENDING)

    def test_completed_is_terminal(self) -> None:
        assert StateMachine.is_stage_terminal(StageStatus.COMPLETED)

    def test_rejected_is_terminal(self) -> None:
        assert StateMachine.is_stage_terminal(StageStatus.REJECTED)

    def test_skipped_is_terminal(self) -> None:
        assert StateMachine.is_stage_terminal(StageStatus.SKIPPED)

    def test_invalid_transition_raises(self) -> None:
        with pytest.raises(StateMachineError):
            StateMachine.transition_stage(StageStatus.COMPLETED, StageStatus.RUNNING)


class TestWorkflowOrdering:
    def test_init_next_is_research(self) -> None:
        assert StateMachine.get_next_stage_type(StageType.INIT) == StageType.RESEARCH

    def test_research_next_is_screening(self) -> None:
        assert StateMachine.get_next_stage_type(StageType.RESEARCH) == StageType.SCREENING

    def test_finalization_has_no_next(self) -> None:
        assert StateMachine.get_next_stage_type(StageType.FINALIZATION) is None

    def test_full_sequence(self) -> None:
        from lead_hunter.orchestrator.state_machine import WORKFLOW_STAGES
        assert len(WORKFLOW_STAGES) == 9
        assert WORKFLOW_STAGES[0] == StageType.INIT
        assert WORKFLOW_STAGES[-1] == StageType.FINALIZATION
