"""Artifact validation service."""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError as PydanticValidationError

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
)
from lead_hunter.exceptions import ArtifactValidationError
from lead_hunter.models.domain import ArtifactType


ARTIFACT_SCHEMA_MAP: dict[ArtifactType, type[ArtifactSchema]] = {
    ArtifactType.RESEARCH_BRIEF: ResearchBrief,
    ArtifactType.EVIDENCE_PACKET: EvidencePacket,
    ArtifactType.DEEP_RESEARCH_BRIEF: DeepResearchBrief,
    ArtifactType.RESEARCH_UPDATE: ResearchUpdate,
    ArtifactType.AUDIT_PACKET: AuditPacket,
    ArtifactType.AUDIT_REPORT: AuditReport,
    ArtifactType.FINAL_DOSSIER: FinalDossier,
    ArtifactType.SCORE_RESULT: ScoreResult,
}


class ArtifactValidationService:
    """Validates artifacts against their Pydantic schemas."""

    @staticmethod
    def validate(artifact_type: ArtifactType, payload: dict[str, Any]) -> ArtifactSchema:
        """Validate a payload against the schema for the given artifact type.

        Returns the validated Pydantic model.
        Raises ArtifactValidationError if validation fails.
        """
        schema_class = ARTIFACT_SCHEMA_MAP.get(artifact_type)
        if not schema_class:
            raise ArtifactValidationError(f"Unknown artifact type: {artifact_type.name}")

        try:
            return schema_class(**payload)
        except PydanticValidationError as exc:
            errors = []
            for error in exc.errors():
                errors.append(f"{'.'.join(str(x) for x in error['loc'])}: {error['msg']}")
            raise ArtifactValidationError(
                f"Artifact validation failed for {artifact_type.name}",
                details={"errors": errors, "payload": payload},
            )

    @staticmethod
    def get_json_schema(artifact_type: ArtifactType) -> dict[str, Any]:
        """Get the JSON Schema for an artifact type."""
        schema_class = ARTIFACT_SCHEMA_MAP.get(artifact_type)
        if not schema_class:
            raise ArtifactValidationError(f"Unknown artifact type: {artifact_type.name}")
        return schema_class.model_json_schema()

    @staticmethod
    def list_artifact_types() -> list[str]:
        """List all supported artifact type names."""
        return [at.name for at in ARTIFACT_SCHEMA_MAP.keys()]
