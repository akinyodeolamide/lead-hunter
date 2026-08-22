"""Tests for artifact protocol (schemas, validation, factory, serialization)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

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
from lead_hunter.artifacts.validation import ArtifactValidationService, ARTIFACT_SCHEMA_MAP
from lead_hunter.artifacts.factory import ArtifactFactory
from lead_hunter.artifacts.serialization import ArtifactSerializer
from lead_hunter.exceptions import ArtifactValidationError
from lead_hunter.models.domain import Artifact, ArtifactType


class TestArtifactSchemaBase:
    def test_default_schema_version(self) -> None:
        schema = ArtifactSchema()
        assert schema.schema_version == "1.0.0"

    def test_produced_at_is_aware(self) -> None:
        schema = ArtifactSchema()
        assert schema.produced_at.tzinfo is not None

    def test_producer_default(self) -> None:
        schema = ArtifactSchema()
        assert schema.producer == ""


class TestResearchBrief:
    def test_valid_creation(self) -> None:
        brief = ResearchBrief(
            lead_name="Acme Corp",
            industry="Software",
            summary="A software company",
            initial_claims=["Has 50 employees"],
            sources=["https://example.com"],
        )
        assert brief.lead_name == "Acme Corp"
        assert brief.industry == "Software"
        assert brief.initial_claims == ["Has 50 employees"]

    def test_missing_required_raises(self) -> None:
        with pytest.raises(Exception):
            ResearchBrief()  # lead_name and industry are required


class TestEvidencePacket:
    def test_valid_creation(self) -> None:
        item = EvidenceItemModel(
            claim="Has 50 employees",
            source_url="https://example.com",
            confidence="HIGH",
            category="BUSINESS_INFO",
        )
        packet = EvidencePacket(
            lead_name="Acme Corp",
            evidence_items=[item],
            total_claims=1,
            verified_claims=1,
        )
        assert len(packet.evidence_items) == 1
        assert packet.evidence_items[0].confidence == "HIGH"

    def test_defaults(self) -> None:
        packet = EvidencePacket(lead_name="Acme Corp")
        assert packet.evidence_items == []
        assert packet.missing_categories == []
        assert packet.total_claims == 0


class TestDeepResearchBrief:
    def test_score_ranges(self) -> None:
        brief = DeepResearchBrief(
            lead_name="Acme Corp",
            business_viability_score=85,
            online_presence_score=70,
            contact_accessibility_score=60,
        )
        assert brief.business_viability_score == 85

    def test_score_out_of_range(self) -> None:
        with pytest.raises(Exception):
            DeepResearchBrief(lead_name="Acme Corp", business_viability_score=101)


class TestResearchUpdate:
    def test_valid_creation(self) -> None:
        update = ResearchUpdate(
            lead_name="Acme Corp",
            update_type="NEW_EVIDENCE",
            updated_claims=["New claim"],
        )
        assert update.update_type == "NEW_EVIDENCE"
        assert update.previous_version_id is None


class TestAuditPacket:
    def test_valid_creation(self) -> None:
        item = AuditItemModel(
            claim="Has 50 employees",
            evidence_found=True,
            evidence_source="https://example.com",
            confidence="HIGH",
        )
        packet = AuditPacket(
            lead_name="Acme Corp",
            audit_items=[item],
            overall_confidence="HIGH",
        )
        assert packet.audit_items[0].evidence_found is True


class TestAuditReport:
    def test_pass_fail(self) -> None:
        report = AuditReport(
            lead_name="Acme Corp",
            summary="All claims verified",
            pass_fail="PASS",
            score=95,
        )
        assert report.pass_fail == "PASS"
        assert report.score == 95

    def test_score_range(self) -> None:
        with pytest.raises(Exception):
            AuditReport(lead_name="Acme Corp", summary="test", score=-1)


class TestFinalDossier:
    def test_valid_creation(self) -> None:
        item = EvidenceItemModel(claim="Has 50 employees", confidence="HIGH")
        dossier = FinalDossier(
            lead_name="Acme Corp",
            company_summary="Software company",
            key_evidence=[item],
            business_viability="Strong",
            online_presence="Active",
            final_score=88,
            recommendation="APPROVE",
        )
        assert dossier.final_score == 88
        assert dossier.recommendation == "APPROVE"


class TestScoreResult:
    def test_valid_creation(self) -> None:
        result = ScoreResult(
            lead_name="Acme Corp",
            overall_score=85,
            evidence_quality_score=90,
            business_viability_score=80,
            online_presence_score=85,
            contact_accessibility_score=70,
            audit_confidence_score=95,
            weights_used={"evidence_quality": 25, "business_viability": 25},
        )
        assert result.overall_score == 85
        assert result.weights_used == {"evidence_quality": 25, "business_viability": 25}

    def test_score_out_of_range(self) -> None:
        with pytest.raises(Exception):
            ScoreResult(lead_name="Acme Corp", overall_score=101, evidence_quality_score=0,
                        business_viability_score=0, online_presence_score=0,
                        contact_accessibility_score=0, audit_confidence_score=0)


class TestArtifactValidationService:
    def test_validate_research_brief(self) -> None:
        payload = {
            "lead_name": "Acme Corp",
            "industry": "Software",
            "summary": "A software company",
        }
        result = ArtifactValidationService.validate(ArtifactType.RESEARCH_BRIEF, payload)
        assert isinstance(result, ResearchBrief)
        assert result.lead_name == "Acme Corp"

    def test_validate_invalid_payload(self) -> None:
        with pytest.raises(ArtifactValidationError):
            ArtifactValidationService.validate(ArtifactType.RESEARCH_BRIEF, {"invalid": "data"})

    def test_validate_unknown_type(self) -> None:
        with pytest.raises(ArtifactValidationError, match="Unknown artifact type"):
            from lead_hunter.models.domain import EventType
            ArtifactValidationService.validate(EventType.RUN_CREATED, {})  # type: ignore[arg-type]

    def test_get_json_schema(self) -> None:
        schema = ArtifactValidationService.get_json_schema(ArtifactType.SCORE_RESULT)
        assert "properties" in schema
        assert "overall_score" in schema["properties"]

    def test_list_artifact_types(self) -> None:
        types = ArtifactValidationService.list_artifact_types()
        assert "RESEARCH_BRIEF" in types
        assert "SCORE_RESULT" in types
        assert len(types) == 8

    def test_validate_all_types(self) -> None:
        """Verify all 8 artifact types can be validated with minimal valid payloads."""
        test_payloads = {
            ArtifactType.RESEARCH_BRIEF: {"lead_name": "X", "industry": "Y", "summary": "Z"},
            ArtifactType.EVIDENCE_PACKET: {"lead_name": "X"},
            ArtifactType.DEEP_RESEARCH_BRIEF: {"lead_name": "X"},
            ArtifactType.RESEARCH_UPDATE: {"lead_name": "X", "update_type": "NEW_EVIDENCE"},
            ArtifactType.AUDIT_PACKET: {"lead_name": "X"},
            ArtifactType.AUDIT_REPORT: {"lead_name": "X", "summary": "Z"},
            ArtifactType.FINAL_DOSSIER: {"lead_name": "X", "company_summary": "Z", "business_viability": "Strong", "online_presence": "Active"},
            ArtifactType.SCORE_RESULT: {"lead_name": "X", "overall_score": 50, "evidence_quality_score": 50,
                                         "business_viability_score": 50, "online_presence_score": 50,
                                         "contact_accessibility_score": 50, "audit_confidence_score": 50},
        }
        for atype, payload in test_payloads.items():
            result = ArtifactValidationService.validate(atype, payload)
            assert result is not None


class TestArtifactFactory:
    def test_create_valid_artifact(self) -> None:
        run_id = uuid4()
        payload = {"lead_name": "Acme Corp", "industry": "Software", "summary": "A company"}
        artifact = ArtifactFactory.create(
            run_id=run_id,
            artifact_type=ArtifactType.RESEARCH_BRIEF,
            payload=payload,
            producer="gemini",
        )
        assert artifact.run_id == run_id
        assert artifact.artifact_type == ArtifactType.RESEARCH_BRIEF
        assert artifact.producer == "gemini"
        assert artifact.payload["lead_name"] == "Acme Corp"

    def test_create_invalid_payload_raises(self) -> None:
        with pytest.raises(ArtifactValidationError):
            ArtifactFactory.create(
                run_id=uuid4(),
                artifact_type=ArtifactType.RESEARCH_BRIEF,
                payload={"invalid": "data"},
                producer="gemini",
            )

    def test_create_from_model(self) -> None:
        run_id = uuid4()
        model = ResearchBrief(lead_name="Acme", industry="Software", summary="test")
        artifact = ArtifactFactory.create_from_model(
            run_id=run_id,
            artifact_type=ArtifactType.RESEARCH_BRIEF,
            model=model,
            producer="claude",
        )
        assert artifact.producer == "claude"
        assert artifact.payload["lead_name"] == "Acme"


class TestArtifactSerializer:
    def test_to_json(self) -> None:
        artifact = Artifact(
            run_id=uuid4(),
            artifact_type=ArtifactType.RESEARCH_BRIEF,
            payload={"key": "value"},
            producer="gemini",
        )
        json_str = ArtifactSerializer.to_json(artifact)
        data = json.loads(json_str)
        assert data["artifact_type"] == "RESEARCH_BRIEF"
        assert data["producer"] == "gemini"
        assert data["payload"]["key"] == "value"

    def test_from_json(self) -> None:
        json_str = '{"key": "value", "number": 42}'
        data = ArtifactSerializer.from_json(json_str)
        assert data["key"] == "value"
        assert data["number"] == 42
