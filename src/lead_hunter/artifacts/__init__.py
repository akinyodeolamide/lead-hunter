"""Artifact protocol for Lead Hunter."""
from lead_hunter.artifacts.schemas import (
    ArtifactSchema,
    ResearchBrief,
    EvidencePacket,
    DeepResearchBrief,
    ResearchUpdate,
    AuditPacket,
    AuditReport,
    FinalDossier,
    ScoreResult,
    EvidenceItemModel,
    AuditItemModel,
)
from lead_hunter.artifacts.validation import ArtifactValidationService
from lead_hunter.artifacts.factory import ArtifactFactory
from lead_hunter.artifacts.serialization import ArtifactSerializer

__all__ = [
    "ArtifactSchema",
    "ResearchBrief",
    "EvidencePacket",
    "DeepResearchBrief",
    "ResearchUpdate",
    "AuditPacket",
    "AuditReport",
    "FinalDossier",
    "ScoreResult",
    "EvidenceItemModel",
    "AuditItemModel",
    "ArtifactValidationService",
    "ArtifactFactory",
    "ArtifactSerializer",
]
