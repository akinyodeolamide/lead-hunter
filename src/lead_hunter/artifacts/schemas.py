"""Pydantic models for all artifact types in the artifact protocol."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ArtifactSchema(BaseModel):
    """Base class for all artifact schemas."""
    schema_version: str = Field(default="1.0.0", description="Version of the artifact schema")
    produced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the artifact was produced")
    producer: str = Field(default="", description="Name of the agent that produced this artifact")

    class Config:
        json_schema_extra = {"additionalProperties": False}


class ResearchBrief(ArtifactSchema):
    """Initial research brief artifact."""
    lead_name: str = Field(description="Name of the lead/company")
    industry: str = Field(description="Industry sector")
    summary: str = Field(description="Brief summary of the lead")
    initial_claims: list[str] = Field(default_factory=list, description="Initial claims to verify")
    sources: list[str] = Field(default_factory=list, description="Initial source URLs")


class EvidenceItemModel(BaseModel):
    """A single piece of evidence in an evidence packet."""
    claim: str = Field(description="The claim being supported")
    source_url: str | None = Field(default=None, description="URL of the source")
    source_title: str | None = Field(default=None, description="Title of the source")
    confidence: str = Field(default="UNVERIFIED", description="Confidence level: HIGH, MEDIUM, LOW, UNVERIFIED")
    category: str = Field(default="OTHER", description="Evidence category")
    excerpt: str | None = Field(default=None, description="Relevant excerpt from the source")


class EvidencePacket(ArtifactSchema):
    """Evidence packet artifact containing collected evidence."""
    lead_name: str = Field(description="Name of the lead")
    evidence_items: list[EvidenceItemModel] = Field(default_factory=list, description="List of evidence items")
    missing_categories: list[str] = Field(default_factory=list, description="Categories with insufficient evidence")
    total_claims: int = Field(default=0, description="Total number of claims")
    verified_claims: int = Field(default=0, description="Number of verified claims")


class DeepResearchBrief(ArtifactSchema):
    """Deep research brief artifact."""
    lead_name: str = Field(description="Name of the lead")
    deep_claims: list[str] = Field(default_factory=list, description="Deep-dive claims")
    evidence_quality: str = Field(default="UNKNOWN", description="Overall evidence quality")
    business_viability_score: int | None = Field(default=None, ge=0, le=100, description="Business viability score 0-100")
    online_presence_score: int | None = Field(default=None, ge=0, le=100, description="Online presence score 0-100")
    contact_accessibility_score: int | None = Field(default=None, ge=0, le=100, description="Contact accessibility score 0-100")


class ResearchUpdate(ArtifactSchema):
    """Research update artifact."""
    lead_name: str = Field(description="Name of the lead")
    update_type: str = Field(description="Type of update: NEW_EVIDENCE, CORRECTION, REFINEMENT")
    updated_claims: list[str] = Field(default_factory=list, description="Updated or new claims")
    previous_version_id: str | None = Field(default=None, description="ID of the previous version")


class AuditItemModel(BaseModel):
    """A single audit item."""
    claim: str = Field(description="The claim being audited")
    evidence_found: bool = Field(description="Whether evidence was found")
    evidence_source: str | None = Field(default=None, description="Source of the evidence")
    auditor_notes: str | None = Field(default=None, description="Notes from the auditor")
    confidence: str = Field(default="UNVERIFIED", description="Audit confidence")


class AuditPacket(ArtifactSchema):
    """Audit packet artifact."""
    lead_name: str = Field(description="Name of the lead")
    audit_items: list[AuditItemModel] = Field(default_factory=list, description="List of audited items")
    overall_confidence: str = Field(default="UNKNOWN", description="Overall audit confidence")
    discrepancies_found: int = Field(default=0, description="Number of discrepancies found")


class AuditReport(ArtifactSchema):
    """Audit report artifact."""
    lead_name: str = Field(description="Name of the lead")
    summary: str = Field(description="Summary of audit findings")
    recommendations: list[str] = Field(default_factory=list, description="Audit recommendations")
    pass_fail: str = Field(default="PENDING", description="PASS or FAIL")
    score: int | None = Field(default=None, ge=0, le=100, description="Audit score 0-100")


class FinalDossier(ArtifactSchema):
    """Final dossier artifact."""
    lead_name: str = Field(description="Name of the lead")
    company_summary: str = Field(description="Company summary")
    key_evidence: list[EvidenceItemModel] = Field(default_factory=list, description="Key evidence items")
    business_viability: str = Field(description="Business viability assessment")
    online_presence: str = Field(description="Online presence assessment")
    contact_info: str | None = Field(default=None, description="Contact information")
    final_score: int | None = Field(default=None, ge=0, le=100, description="Final score 0-100")
    recommendation: str = Field(default="PENDING", description="Final recommendation")


class ScoreResult(ArtifactSchema):
    """Score result artifact."""
    lead_name: str = Field(description="Name of the lead")
    overall_score: int = Field(ge=0, le=100, description="Overall score 0-100")
    evidence_quality_score: int = Field(ge=0, le=100, description="Evidence quality score")
    business_viability_score: int = Field(ge=0, le=100, description="Business viability score")
    online_presence_score: int = Field(ge=0, le=100, description="Online presence score")
    contact_accessibility_score: int = Field(ge=0, le=100, description="Contact accessibility score")
    audit_confidence_score: int = Field(ge=0, le=100, description="Audit confidence score")
    weights_used: dict[str, int] = Field(default_factory=dict, description="Scoring weights used")
