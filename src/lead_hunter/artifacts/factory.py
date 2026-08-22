"""Artifact factory for creating and versioning artifacts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from lead_hunter.artifacts.schemas import ArtifactSchema
from lead_hunter.artifacts.validation import ArtifactValidationService
from lead_hunter.models.domain import Artifact, ArtifactType


class ArtifactFactory:
    """Factory for creating validated artifacts."""

    @staticmethod
    def create(
        run_id: UUID,
        artifact_type: ArtifactType,
        payload: dict[str, Any],
        producer: str,
        schema_version: str = "1.0.0",
    ) -> Artifact:
        """Create a validated artifact.

        Validates the payload against the schema before creating the artifact.
        """
        # Validate the payload
        validated = ArtifactValidationService.validate(artifact_type, payload)

        return Artifact(
            artifact_id=uuid4(),
            run_id=run_id,
            artifact_type=artifact_type,
            schema_version=schema_version,
            payload=validated.model_dump(mode="json"),
            producer=producer,
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def create_from_model(
        run_id: UUID,
        artifact_type: ArtifactType,
        model: ArtifactSchema,
        producer: str,
    ) -> Artifact:
        """Create an artifact from an already-validated Pydantic model."""
        return Artifact(
            artifact_id=uuid4(),
            run_id=run_id,
            artifact_type=artifact_type,
            schema_version=model.schema_version,
            payload=model.model_dump(mode="json"),
            producer=producer,
            created_at=datetime.now(timezone.utc),
        )
