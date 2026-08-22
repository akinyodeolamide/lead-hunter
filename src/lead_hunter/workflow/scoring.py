"""Deterministic scoring engine for Lead Hunter.

The scoring engine produces deterministic scores based solely on the
FINAL_DOSSIER content using explicit, weighted, and configurable criteria.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from lead_hunter.artifacts.schemas import (
    AuditReport,
    EvidencePacket,
    FinalDossier,
    ScoreResult,
)
from lead_hunter.exceptions import ScoringError
from lead_hunter.logging_config import get_logger, log_event

logger = get_logger("scoring")


class ScoreConfidence(str, Enum):
    """Confidence level for a computed score."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ScoreThreshold(str, Enum):
    """Score threshold categories."""
    AUTO_APPROVE = "AUTO_APPROVE"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    AUTO_REJECT = "AUTO_REJECT"


@dataclass
class ScoreDecision:
    """Decision derived from a score result."""
    threshold: ScoreThreshold
    confidence: ScoreConfidence
    rationale: str


class ScoringEngine:
    """Deterministic scoring engine.

    Same inputs always produce the same score.
    Scoring is based solely on FINAL_DOSSIER content.
    """

    DEFAULT_WEIGHTS: dict[str, int] = {
        "evidence_quality": 25,
        "business_viability": 25,
        "online_presence": 20,
        "contact_accessibility": 15,
        "audit_confidence": 15,
    }

    def __init__(
        self,
        weights: dict[str, int] | None = None,
        auto_approve_threshold: int = 85,
        require_approval_threshold: int = 60,
        auto_reject_threshold: int = 60,
    ) -> None:
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.auto_approve_threshold = auto_approve_threshold
        self.require_approval_threshold = require_approval_threshold
        self.auto_reject_threshold = auto_reject_threshold
        self._validate_weights()

    def _validate_weights(self) -> None:
        """Validate that weights sum to 100."""
        total = sum(self.weights.values())
        if total != 100:
            raise ScoringError(f"Scoring weights must sum to 100, got {total}")
        for key in self.DEFAULT_WEIGHTS:
            if key not in self.weights:
                raise ScoringError(f"Missing required scoring weight: {key}")

    def score(
        self,
        dossier: FinalDossier,
        evidence: EvidencePacket | None = None,
        audit_report: AuditReport | None = None,
    ) -> ScoreResult:
        """Compute a deterministic score for a lead dossier."""
        category_scores: dict[str, int] = {}

        category_scores["evidence_quality"] = self._score_evidence_quality(
            evidence, dossier
        )
        category_scores["business_viability"] = self._score_business_viability(
            dossier
        )
        category_scores["online_presence"] = self._score_online_presence(dossier)
        category_scores["contact_accessibility"] = self._score_contact_accessibility(
            dossier
        )
        category_scores["audit_confidence"] = self._score_audit_confidence(
            audit_report
        )

        total_score = 0
        for category, weight in self.weights.items():
            total_score += category_scores[category] * (weight / 100)

        overall_score = int(round(total_score))
        overall_score = max(0, min(100, overall_score))

        confidence = self._determine_confidence(category_scores)

        result = ScoreResult(
            lead_name=dossier.lead_name,
            overall_score=overall_score,
            evidence_quality_score=category_scores["evidence_quality"],
            business_viability_score=category_scores["business_viability"],
            online_presence_score=category_scores["online_presence"],
            contact_accessibility_score=category_scores["contact_accessibility"],
            audit_confidence_score=category_scores["audit_confidence"],
            weights_used=self.weights.copy(),
        )

        log_event(
            logger,
            "INFO",
            f"Score computed for {dossier.lead_name}: {overall_score}",
            context={
                "overall_score": overall_score,
                "category_scores": category_scores,
                "confidence": confidence.value,
            },
        )
        return result

    def decide(self, score_result: ScoreResult) -> ScoreDecision:
        """Determine the decision based on score and confidence."""
        score = score_result.overall_score
        confidence = self._determine_confidence_from_result(score_result)

        if score >= self.auto_approve_threshold and confidence == ScoreConfidence.HIGH:
            threshold = ScoreThreshold.AUTO_APPROVE
            rationale = (
                f"Score {score} >= {self.auto_approve_threshold} "
                f"with HIGH confidence. Auto-approve eligible."
            )
        elif score < self.auto_reject_threshold:
            threshold = ScoreThreshold.AUTO_REJECT
            rationale = (
                f"Score {score} < {self.auto_reject_threshold}. "
                f"Auto-reject."
            )
        else:
            threshold = ScoreThreshold.REQUIRE_APPROVAL
            rationale = (
                f"Score {score} in approval range "
                f"({self.auto_reject_threshold}-{self.auto_approve_threshold}). "
                f"Human approval required."
            )

        return ScoreDecision(
            threshold=threshold,
            confidence=confidence,
            rationale=rationale,
        )

    def _score_evidence_quality(
        self, evidence: EvidencePacket | None, dossier: FinalDossier
    ) -> int:
        """Score evidence quality (0-100)."""
        if evidence is None:
            key_evidence = dossier.key_evidence
            if not key_evidence:
                return 0
            total = len(key_evidence)
            verified = sum(
                1 for e in key_evidence
                if e.confidence in ("HIGH", "MEDIUM")
            )
            return int((verified / total) * 100) if total > 0 else 0

        total = max(evidence.total_claims, len(evidence.evidence_items))
        if total == 0:
            return 0
        verified = evidence.verified_claims
        missing_penalty = len(evidence.missing_categories) * 10
        score = int((verified / total) * 100) - missing_penalty
        return max(0, min(100, score))

    def _score_business_viability(self, dossier: FinalDossier) -> int:
        """Score business viability (0-100)."""
        viability = dossier.business_viability.lower()
        if "excellent" in viability or "strong" in viability:
            return 90
        elif "good" in viability or "viable" in viability:
            return 75
        elif "moderate" in viability or "fair" in viability:
            return 55
        elif "poor" in viability or "weak" in viability:
            return 30
        elif "unknown" in viability:
            return 20
        return 50

    def _score_online_presence(self, dossier: FinalDossier) -> int:
        """Score online presence (0-100)."""
        presence = dossier.online_presence.lower()
        if "excellent" in presence or "strong" in presence:
            return 90
        elif "good" in presence or "active" in presence:
            return 75
        elif "moderate" in presence or "limited" in presence:
            return 55
        elif "poor" in presence or "minimal" in presence:
            return 30
        elif "unknown" in presence or "none" in presence:
            return 20
        return 50

    def _score_contact_accessibility(self, dossier: FinalDossier) -> int:
        """Score contact accessibility (0-100)."""
        contact = dossier.contact_info
        if not contact:
            return 0
        score = 50
        contact_lower = contact.lower()
        if "email" in contact_lower or "@" in contact_lower:
            score += 20
        if "phone" in contact_lower or "tel" in contact_lower:
            score += 15
        if "linkedin" in contact_lower:
            score += 10
        if "website" in contact_lower:
            score += 5
        return min(100, score)

    def _score_audit_confidence(self, audit_report: AuditReport | None) -> int:
        """Score audit confidence (0-100)."""
        if audit_report is None:
            return 50
        if audit_report.pass_fail == "PASS":
            return 90
        elif audit_report.pass_fail == "FAIL":
            return 20
        score = audit_report.score or 50
        return max(0, min(100, score))

    def _determine_confidence(self, category_scores: dict[str, int]) -> ScoreConfidence:
        """Determine overall confidence from category scores."""
        avg = sum(category_scores.values()) / len(category_scores)
        if avg >= 80:
            return ScoreConfidence.HIGH
        elif avg >= 50:
            return ScoreConfidence.MEDIUM
        return ScoreConfidence.LOW

    def _determine_confidence_from_result(
        self, score_result: ScoreResult
    ) -> ScoreConfidence:
        """Determine confidence from a ScoreResult."""
        scores = [
            score_result.evidence_quality_score,
            score_result.business_viability_score,
            score_result.online_presence_score,
            score_result.contact_accessibility_score,
            score_result.audit_confidence_score,
        ]
        avg = sum(scores) / len(scores)
        if avg >= 80:
            return ScoreConfidence.HIGH
        elif avg >= 50:
            return ScoreConfidence.MEDIUM
        return ScoreConfidence.LOW
