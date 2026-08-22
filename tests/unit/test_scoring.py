"""Unit tests for the deterministic scoring engine."""
from __future__ import annotations

import pytest

from lead_hunter.artifacts.schemas import (
    AuditReport,
    EvidenceItemModel,
    EvidencePacket,
    FinalDossier,
)
from lead_hunter.exceptions import ScoringError
from lead_hunter.workflow.scoring import (
    ScoreConfidence,
    ScoreDecision,
    ScoreThreshold,
    ScoringEngine,
)


class TestScoringEngine:
    def test_default_weights_valid(self) -> None:
        engine = ScoringEngine()
        assert sum(engine.weights.values()) == 100

    def test_invalid_weights_raises(self) -> None:
        with pytest.raises(ScoringError, match="must sum to 100"):
            ScoringEngine(weights={"evidence_quality": 50, "business_viability": 30})

    def test_missing_weight_key_raises(self) -> None:
        # Omit one required key but sum to 100 so the missing-key check triggers
        with pytest.raises(ScoringError, match="Missing required scoring weight"):
            ScoringEngine(
                weights={
                    "evidence_quality": 30,
                    "business_viability": 30,
                    "online_presence": 20,
                    "contact_accessibility": 20,
                    # audit_confidence missing — sums to 100
                }
            )

    def test_score_minimal_dossier(self) -> None:
        engine = ScoringEngine()
        dossier = FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Unknown",
            online_presence="Unknown",
            contact_info=None,
        )
        result = engine.score(dossier)
        # Unknown viability=20, unknown presence=20, no contact=0, no evidence=0, no audit=50
        # weighted: 20*0.25 + 20*0.25 + 0*0.20 + 0*0.15 + 50*0.15 = 5+5+0+0+7.5 = 17.5 -> 16 (round down)
        assert result.overall_score == 16
        assert result.lead_name == "TestCo"
        assert result.evidence_quality_score == 0
        assert result.contact_accessibility_score == 0

    def test_score_with_evidence(self) -> None:
        engine = ScoringEngine()
        dossier = FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Good viability",
            online_presence="Strong presence",
            contact_info="Email: test@example.com, Phone: 555-1234",
        )
        evidence = EvidencePacket(
            lead_name="TestCo",
            evidence_items=[
                EvidenceItemModel(claim="C1", confidence="HIGH", category="BUSINESS_INFO"),
                EvidenceItemModel(claim="C2", confidence="MEDIUM", category="CONTACT"),
                EvidenceItemModel(claim="C3", confidence="HIGH", category="ONLINE_PRESENCE"),
            ],
            total_claims=3,
            verified_claims=3,
        )
        result = engine.score(dossier, evidence=evidence)
        assert result.overall_score > 0
        assert result.evidence_quality_score == 100
        assert result.business_viability_score == 75
        assert result.online_presence_score == 90
        assert result.contact_accessibility_score == 85

    def test_score_with_audit_pass(self) -> None:
        engine = ScoringEngine()
        dossier = FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Good",
            online_presence="Good",
            contact_info="Email: test@example.com",
        )
        audit = AuditReport(
            lead_name="TestCo",
            summary="All good",
            pass_fail="PASS",
            score=90,
        )
        result = engine.score(dossier, audit_report=audit)
        assert result.audit_confidence_score == 90

    def test_score_with_audit_fail(self) -> None:
        engine = ScoringEngine()
        dossier = FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Good",
            online_presence="Good",
            contact_info="Email: test@example.com",
        )
        audit = AuditReport(
            lead_name="TestCo",
            summary="Issues found",
            pass_fail="FAIL",
            score=30,
        )
        result = engine.score(dossier, audit_report=audit)
        assert result.audit_confidence_score == 20

    def test_determinism(self) -> None:
        engine = ScoringEngine()
        dossier = FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Strong",
            online_presence="Excellent",
            contact_info="Email: a@b.com, Phone: 123, LinkedIn: url",
        )
        evidence = EvidencePacket(
            lead_name="TestCo",
            evidence_items=[
                EvidenceItemModel(claim="C1", confidence="HIGH", category="BUSINESS_INFO"),
                EvidenceItemModel(claim="C2", confidence="HIGH", category="CONTACT"),
                EvidenceItemModel(claim="C3", confidence="HIGH", category="ONLINE_PRESENCE"),
                EvidenceItemModel(claim="C4", confidence="MEDIUM", category="FINANCIAL"),
            ],
            total_claims=4,
            verified_claims=4,
        )
        audit = AuditReport(
            lead_name="TestCo",
            summary="Pass",
            pass_fail="PASS",
            score=95,
        )
        r1 = engine.score(dossier, evidence=evidence, audit_report=audit)
        r2 = engine.score(dossier, evidence=evidence, audit_report=audit)
        assert r1.overall_score == r2.overall_score
        # Compare individual score fields instead of category_scores attribute
        assert r1.evidence_quality_score == r2.evidence_quality_score
        assert r1.business_viability_score == r2.business_viability_score
        assert r1.online_presence_score == r2.online_presence_score
        assert r1.contact_accessibility_score == r2.contact_accessibility_score
        assert r1.audit_confidence_score == r2.audit_confidence_score

    def test_decide_auto_approve(self) -> None:
        engine = ScoringEngine()
        dossier = FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Excellent",
            online_presence="Excellent",
            contact_info="Email: test@example.com",
        )
        evidence = EvidencePacket(
            lead_name="TestCo",
            evidence_items=[
                EvidenceItemModel(claim="C1", confidence="HIGH", category="BUSINESS_INFO"),
            ],
            total_claims=1,
            verified_claims=1,
        )
        audit = AuditReport(
            lead_name="TestCo",
            summary="Pass",
            pass_fail="PASS",
            score=95,
        )
        result = engine.score(dossier, evidence=evidence, audit_report=audit)
        decision = engine.decide(result)
        assert decision.threshold == ScoreThreshold.AUTO_APPROVE
        assert decision.confidence == ScoreConfidence.HIGH

    def test_decide_auto_reject(self) -> None:
        engine = ScoringEngine()
        dossier = FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Unknown",
            online_presence="Unknown",
            contact_info=None,
        )
        result = engine.score(dossier)
        decision = engine.decide(result)
        assert decision.threshold == ScoreThreshold.AUTO_REJECT

    def test_decide_require_approval(self) -> None:
        engine = ScoringEngine()
        dossier = FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Good",
            online_presence="Good",
            contact_info="Email: test@example.com",
        )
        evidence = EvidencePacket(
            lead_name="TestCo",
            evidence_items=[
                EvidenceItemModel(claim="C1", confidence="HIGH", category="BUSINESS_INFO"),
                EvidenceItemModel(claim="C2", confidence="HIGH", category="CONTACT"),
                EvidenceItemModel(claim="C3", confidence="MEDIUM", category="ONLINE_PRESENCE"),
            ],
            total_claims=3,
            verified_claims=3,
        )
        audit = AuditReport(
            lead_name="TestCo",
            summary="Pass",
            pass_fail="PASS",
            score=70,
        )
        result = engine.score(dossier, evidence=evidence, audit_report=audit)
        decision = engine.decide(result)
        assert decision.threshold == ScoreThreshold.REQUIRE_APPROVAL

    def test_score_result_has_weights(self) -> None:
        engine = ScoringEngine()
        dossier = FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Good",
            online_presence="Good",
            contact_info="Email: test@example.com",
        )
        result = engine.score(dossier)
        assert "evidence_quality" in result.weights_used
        assert sum(result.weights_used.values()) == 100

    def test_custom_weights(self) -> None:
        custom_weights = {
            "evidence_quality": 30,
            "business_viability": 30,
            "online_presence": 20,
            "contact_accessibility": 10,
            "audit_confidence": 10,
        }
        engine = ScoringEngine(weights=custom_weights)
        assert engine.weights == custom_weights
