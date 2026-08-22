"""Artifact serialization utilities."""
from __future__ import annotations

import json
from typing import Any

from lead_hunter.models.domain import Artifact


class ArtifactSerializer:
    """Serializes and deserializes artifacts."""

    @staticmethod
    def to_json(artifact: Artifact) -> str:
        """Serialize an artifact to JSON string."""
        return json.dumps({
            "artifact_id": str(artifact.artifact_id),
            "run_id": str(artifact.run_id),
            "artifact_type": artifact.artifact_type.name,
            "schema_version": artifact.schema_version,
            "payload": artifact.payload,
            "producer": artifact.producer,
            "created_at": artifact.created_at.isoformat(),
        }, indent=2)

    @staticmethod
    def from_json(data: str) -> dict[str, Any]:
        """Deserialize JSON string to artifact dict."""
        return json.loads(data)
