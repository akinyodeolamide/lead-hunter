"""Unit tests for domain models."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from lead_hunter.models.domain import (
    Run,
    Stage,
    Approval,
    Event,
    Artifact,
    ErrorRecord,
    Configuration,
    RunStatus,
    StageStatus,
    StageType,
    ApprovalDecision,
    ApprovalType,
    RejectionCategory,
    EventType,
    ArtifactType,
    ConfidenceLevel,
    SourceType,
    EvidenceCategory,
    DeliveryStatus,
    ApprovalStatus,
    Source,
    EvidenceItem,
    RejectionReason,
)


class TestRunModel:
    """Test Run dataclass."""

    def test_default_creation(self) -> None:
        run = Run()
        assert isinstance(run.run_id, UUID)
        assert run.status == RunStatus.PENDING
        assert run.configuration_id == "default"
        assert isinstance(run.correlation_id, UUID)
        assert isinstance(run.created_at, datetime)
        assert isinstance(run.updated_at, datetime)
        assert run.started_at is None
        assert run.completed_at is None
        assert run.metadata == {}

    def test_custom_values(self) -> None:
        rid = uuid4()
        cid = uuid4()
        now = datetime.now(timezone.utc)
        run = Run(
            run_id=rid,
            status=RunStatus.RUNNING,
            configuration_id="campaign-1",
            correlation_id=cid,
            created_at=now,
            updated_at=now,
            started_at=now,
            metadata={"key": "value"},
        )
        assert run.run_id == rid
        assert run.status == RunStatus.RUNNING
        assert run.configuration_id == "campaign-1"
        assert run.correlation_id == cid
        assert run.metadata == {"key": "value"}


class TestStageModel:
    """Test Stage dataclass."""

    def test_default_creation(self) -> None:
        stage = Stage()
        assert isinstance(stage.stage_id, UUID)
        assert isinstance(stage.run_id, UUID)
        assert stage.stage_type == StageType.INIT
        assert stage.status == StageStatus.PENDING
        assert stage.retry_count == 0
        assert stage.max_retries == 3
        assert stage.started_at is None
        assert stage.completed_at is None

    def test_custom_stage_type(self) -> None:
        stage = Stage(stage_type=StageType.RESEARCH, status=StageStatus.RUNNING)
        assert stage.stage_type == StageType.RESEARCH
        assert stage.status == StageStatus.RUNNING


class TestApprovalModel:
    """Test Approval dataclass."""

    def test_default_creation(self) -> None:
        approval = Approval()
        assert isinstance(approval.approval_id, UUID)
        assert approval.decision == ApprovalDecision.PENDING
        assert approval.approval_type == ApprovalType.MANUAL_REVIEW
        assert approval.decided_by is None
        assert approval.decision_rationale is None
        assert approval.deadline is None
        assert approval.decided_at is None

    def test_approved(self) -> None:
        approval = Approval(
            decision=ApprovalDecision.APPROVED,
            decided_by="admin@example.com",
            decision_rationale="Looks good",
        )
        assert approval.decision == ApprovalDecision.APPROVED
        assert approval.decided_by == "admin@example.com"


class TestEventModel:
    """Test Event dataclass."""

    def test_default_creation(self) -> None:
        event = Event()
        assert isinstance(event.event_id, UUID)
        assert event.event_type == EventType.STARTUP
        assert event.payload == {}
        assert isinstance(event.timestamp, datetime)
        assert isinstance(event.correlation_id, UUID)

    def test_custom_event(self) -> None:
        event = Event(
            event_type=EventType.RUN_CREATED,
            payload={"run_id": str(uuid4())},
        )
        assert event.event_type == EventType.RUN_CREATED
        assert "run_id" in event.payload


class TestArtifactModel:
    """Test Artifact dataclass."""

    def test_default_creation(self) -> None:
        artifact = Artifact()
        assert isinstance(artifact.artifact_id, UUID)
        assert artifact.artifact_type == ArtifactType.RESEARCH_BRIEF
        assert artifact.schema_version == "1.0.0"
        assert artifact.payload == {}
        assert artifact.producer == ""

    def test_evidence_packet(self) -> None:
        artifact = Artifact(
            artifact_type=ArtifactType.EVIDENCE_PACKET,
            payload={"claims": ["claim1"]},
            producer="gemini",
        )
        assert artifact.artifact_type == ArtifactType.EVIDENCE_PACKET
        assert artifact.producer == "gemini"


class TestErrorRecordModel:
    """Test ErrorRecord dataclass."""

    def test_default_creation(self) -> None:
        error = ErrorRecord()
        assert isinstance(error.error_id, UUID)
        assert error.is_recoverable is False
        assert error.recovery_attempted is False
        assert error.stack_trace is None

    def test_with_stack_trace(self) -> None:
        error = ErrorRecord(
            error_type="AgentTimeoutError",
            error_message="Request timed out",
            stack_trace="Traceback...",
            is_recoverable=True,
        )
        assert error.error_type == "AgentTimeoutError"
        assert error.is_recoverable is True


class TestEvidenceItem:
    """Test EvidenceItem dataclass."""

    def test_default_creation(self) -> None:
        item = EvidenceItem()
        assert isinstance(item.evidence_id, UUID)
        assert item.confidence == ConfidenceLevel.UNVERIFIED
        assert item.category == EvidenceCategory.OTHER
        assert item.source is None

    def test_with_source(self) -> None:
        source = Source(
            source_type=SourceType.URL,
            source_url="https://example.com",
            source_title="Example",
        )
        item = EvidenceItem(
            claim="Company has 50 employees",
            source=source,
            confidence=ConfidenceLevel.HIGH,
            category=EvidenceCategory.BUSINESS_INFO,
            collector="gemini",
        )
        assert item.claim == "Company has 50 employees"
        assert item.source is not None
        assert item.source.source_type == SourceType.URL
        assert item.confidence == ConfidenceLevel.HIGH
        assert item.category == EvidenceCategory.BUSINESS_INFO
        assert item.collector == "gemini"


class TestRejectionReason:
    """Test RejectionReason dataclass."""

    def test_creation(self) -> None:
        reason = RejectionReason(
            category=RejectionCategory.INSUFFICIENT_EVIDENCE,
            reason="Not enough evidence in BUSINESS_INFO category",
            stage=StageType.SCREENING,
        )
        assert reason.category == RejectionCategory.INSUFFICIENT_EVIDENCE
        assert reason.stage == StageType.SCREENING
        assert isinstance(reason.timestamp, datetime)


class TestEnumValues:
    """Test that all enums have expected values."""

    def test_run_status_values(self) -> None:
        assert len(list(RunStatus)) == 8
        assert RunStatus.PENDING.name == "PENDING"
        assert RunStatus.COMPLETED.name == "COMPLETED"

    def test_stage_status_values(self) -> None:
        assert len(list(StageStatus)) == 7
        assert StageStatus.WAITING_FOR_APPROVAL.name == "WAITING_FOR_APPROVAL"

    def test_stage_type_values(self) -> None:
        assert len(list(StageType)) == 9
        assert StageType.INIT.name == "INIT"
        assert StageType.FINALIZATION.name == "FINALIZATION"

    def test_approval_decision_values(self) -> None:
        assert len(list(ApprovalDecision)) == 5

    def test_artifact_type_values(self) -> None:
        assert len(list(ArtifactType)) == 8

    def test_event_type_values(self) -> None:
        assert len(list(EventType)) >= 30  # many event types

    def test_confidence_level_str_values(self) -> None:
        assert ConfidenceLevel.HIGH.value == "HIGH"
        assert ConfidenceLevel.UNVERIFIED.value == "UNVERIFIED"

    def test_source_type_values(self) -> None:
        assert len(list(SourceType)) == 5

    def test_evidence_category_values(self) -> None:
        assert len(list(EvidenceCategory)) == 6
