"""Abstract domain models for Lead Hunter.

These models define the core entities independent of persistence technology.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any
from uuid import UUID, uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(Enum):
    """Top-level status of a workflow run."""
    PENDING = auto()
    QUEUED = auto()
    RUNNING = auto()
    PAUSED = auto()
    REJECTED = auto()
    FAILED = auto()
    CANCELLED = auto()
    COMPLETED = auto()


class StageStatus(Enum):
    """Status of an individual stage within a run."""
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    WAITING_FOR_APPROVAL = auto()
    REJECTED = auto()
    SKIPPED = auto()


class StageType(Enum):
    """Types of stages in the lead hunter workflow."""
    INIT = auto()
    RESEARCH = auto()
    SCREENING = auto()
    DEEP_RESEARCH = auto()
    AUDIT = auto()
    SCORING = auto()
    APPROVAL = auto()
    DELIVERY = auto()
    FINALIZATION = auto()


class ApprovalDecision(Enum):
    """Possible decisions at an approval gate."""
    PENDING = auto()
    APPROVED = auto()
    REJECTED = auto()
    PAUSED = auto()
    TIMEOUT = auto()


class ApprovalType(Enum):
    """Types of approval gates."""
    MANUAL_REVIEW = auto()
    AUTO_APPROVE = auto()
    ESCALATION = auto()


class RejectionCategory(Enum):
    """Categories for rejection reasons."""
    INSUFFICIENT_EVIDENCE = auto()
    QUALITY_FAILURE = auto()
    AUDIT_FAILURE = auto()
    HUMAN_DECISION = auto()
    SYSTEM_ERROR = auto()
    OTHER = auto()


class EventType(Enum):
    """Types of events logged by the system."""
    RUN_CREATED = auto()
    RUN_STARTED = auto()
    RUN_COMPLETED = auto()
    RUN_FAILED = auto()
    RUN_REJECTED = auto()
    RUN_PAUSED = auto()
    RUN_RESUMED = auto()
    RUN_CANCELLED = auto()
    STAGE_STARTED = auto()
    STAGE_COMPLETED = auto()
    STAGE_FAILED = auto()
    STAGE_RETRIED = auto()
    STAGE_REJECTED = auto()
    STAGE_SKIPPED = auto()
    APPROVAL_REQUESTED = auto()
    APPROVAL_DECIDED = auto()
    AGENT_REQUEST_SENT = auto()
    AGENT_RESPONSE_RECEIVED = auto()
    AGENT_REQUEST_FAILED = auto()
    ARTIFACT_CREATED = auto()
    ARTIFACT_VALIDATED = auto()
    ARTIFACT_REJECTED = auto()
    SCORE_COMPUTED = auto()
    DELIVERY_ATTEMPTED = auto()
    DELIVERY_SUCCEEDED = auto()
    DELIVERY_FAILED = auto()
    RECOVERY_ACTION = auto()
    CONFIGURATION_LOADED = auto()
    STARTUP = auto()
    SHUTDOWN = auto()


class ArtifactType(Enum):
    """Types of artifacts in the artifact protocol."""
    RESEARCH_BRIEF = auto()
    EVIDENCE_PACKET = auto()
    DEEP_RESEARCH_BRIEF = auto()
    RESEARCH_UPDATE = auto()
    AUDIT_PACKET = auto()
    AUDIT_REPORT = auto()
    FINAL_DOSSIER = auto()
    SCORE_RESULT = auto()


class ConfidenceLevel(Enum):
    """Confidence levels for evidence and scores."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNVERIFIED = "UNVERIFIED"


class SourceType(Enum):
    """Types of evidence sources."""
    URL = "URL"
    DATABASE = "DATABASE"
    DOCUMENT = "DOCUMENT"
    INFERENCE = "INFERENCE"
    AGENT_GENERATED = "AGENT_GENERATED"


class EvidenceCategory(Enum):
    """Categories for evidence items."""
    BUSINESS_INFO = "BUSINESS_INFO"
    ONLINE_PRESENCE = "ONLINE_PRESENCE"
    FINANCIAL = "FINANCIAL"
    CONTACT = "CONTACT"
    REPUTATION = "REPUTATION"
    OTHER = "OTHER"


class DeliveryStatus(Enum):
    """Status of email delivery."""
    PENDING = auto()
    SENT = auto()
    FAILED = auto()


class ApprovalStatus(Enum):
    """Status of a lead dossier approval."""
    PENDING = auto()
    APPROVED = auto()
    REJECTED = auto()
    PAUSED = auto()


@dataclass(frozen=True)
class Source:
    """A source for a piece of evidence."""
    source_type: SourceType
    source_url: str | None = None
    source_title: str | None = None
    access_date: datetime | None = None
    excerpt: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    """A single piece of evidence."""
    evidence_id: UUID = field(default_factory=uuid4)
    claim: str = ""
    source: Source | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.UNVERIFIED
    category: EvidenceCategory = EvidenceCategory.OTHER
    collected_at: datetime = field(default_factory=_utcnow)
    collector: str = ""


@dataclass(frozen=True)
class RejectionReason:
    """Structured rejection reason."""
    category: RejectionCategory
    reason: str
    stage: StageType
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class Run:
    """A single execution of the lead hunter workflow."""
    run_id: UUID = field(default_factory=uuid4)
    status: RunStatus = RunStatus.PENDING
    configuration_id: str = "default"
    correlation_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Stage:
    """A phase within a run."""
    stage_id: UUID = field(default_factory=uuid4)
    run_id: UUID = field(default_factory=uuid4)
    stage_type: StageType = StageType.INIT
    status: StageStatus = StageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Approval:
    """An approval gate record."""
    approval_id: UUID = field(default_factory=uuid4)
    run_id: UUID = field(default_factory=uuid4)
    stage_id: UUID = field(default_factory=uuid4)
    approval_type: ApprovalType = ApprovalType.MANUAL_REVIEW
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decided_by: str | None = None
    request_details: dict[str, Any] = field(default_factory=dict)
    decision_rationale: str | None = None
    deadline: datetime | None = None
    created_at: datetime = field(default_factory=_utcnow)
    decided_at: datetime | None = None


@dataclass
class Event:
    """A log of something that happened in the system."""
    event_id: UUID = field(default_factory=uuid4)
    run_id: UUID | None = None
    stage_id: UUID | None = None
    event_type: EventType = EventType.STARTUP
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    correlation_id: UUID = field(default_factory=uuid4)


@dataclass
class Artifact:
    """A structured, schema-validated data object passed between agents."""
    artifact_id: UUID = field(default_factory=uuid4)
    run_id: UUID = field(default_factory=uuid4)
    artifact_type: ArtifactType = ArtifactType.RESEARCH_BRIEF
    schema_version: str = "1.0.0"
    payload: dict[str, Any] = field(default_factory=dict)
    producer: str = ""
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class ErrorRecord:
    """A recorded failure in the system."""
    error_id: UUID = field(default_factory=uuid4)
    run_id: UUID | None = None
    stage_id: UUID | None = None
    error_type: str = ""
    error_message: str = ""
    stack_trace: str | None = None
    is_recoverable: bool = False
    recovery_attempted: bool = False
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class Configuration:
    """A configuration record for a run or campaign."""
    config_id: str = "default"
    config_data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
