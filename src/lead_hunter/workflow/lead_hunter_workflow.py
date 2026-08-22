"""Lead Hunter Workflow implementation.

Implements the full 9-stage workflow:
INIT → RESEARCH → SCREENING → DEEP_RESEARCH → AUDIT → SCORING → APPROVAL → DELIVERY → FINALIZATION
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from lead_hunter.approval.approval_service import ApprovalService
from lead_hunter.artifacts.factory import ArtifactFactory
from lead_hunter.artifacts.schemas import (
    AuditPacket,
    AuditReport,
    DeepResearchBrief,
    EvidencePacket,
    FinalDossier,
    ResearchBrief,
    ResearchUpdate,
    ScoreResult,
)
from lead_hunter.artifacts.validation import ArtifactValidationService
from lead_hunter.exceptions import AgentError, ArtifactValidationError, ScoringError
from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.models.domain import (
    ApprovalType,
    Artifact,
    ArtifactType,
    Event,
    EventType,
    RejectionCategory,
    RejectionReason,
    Run,
    RunStatus,
    Stage,
    StageStatus,
    StageType,
)
from lead_hunter.orchestrator.interfaces import AgentRequest, Delivery, HealthStatus
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.orchestrator.state_machine import StateMachine
from lead_hunter.workflow.scoring import ScoreDecision, ScoreThreshold, ScoringEngine

logger = get_logger("lead_hunter_workflow")


class LeadHunterWorkflow:
    """End-to-end lead hunter workflow executor.

    Orchestrates the complete pipeline from research brief generation
    through final dossier delivery.
    """

    def __init__(
        self,
        orchestration_engine: OrchestrationEngine,
        scoring_engine: ScoringEngine | None = None,
        approval_service: ApprovalService | None = None,
        delivery: Delivery | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.engine = orchestration_engine
        self.scoring_engine = scoring_engine or ScoringEngine()
        self.approval_service = approval_service
        self.delivery = delivery
        self.config = config or {}
        self._screening_min_evidence = self.config.get("screening_min_evidence", 3)
        self._screening_min_confidence = self.config.get("screening_min_confidence", "MEDIUM")
        self._deep_research_threshold = self.config.get("deep_research_threshold", 50)

    async def execute_run(
        self,
        run: Run,
        lead_name: str,
        industry: str,
        summary: str,
        initial_claims: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> Run:
        """Execute the complete lead hunter workflow for a run."""
        # Persist lead context in run metadata for continuation/resumption
        run.metadata["lead_name"] = lead_name
        run.metadata["industry"] = industry
        run.metadata["summary"] = summary
        await self.engine.persistence.update_run(run)

        log_event(
            logger,
            "INFO",
            f"Starting LeadHunterWorkflow for {lead_name}",
            run_id=run.run_id,
        )

        try:
            # Stage 1: RESEARCH (Gemini)
            run = await self._execute_research_stage(
                run, lead_name, industry, summary, initial_claims, sources
            )
            if StateMachine.is_run_terminal(run.status):
                return run

            # Stage 2: SCREENING
            run = await self._execute_screening_stage(run, lead_name)
            if StateMachine.is_run_terminal(run.status):
                return run

            # Stage 3: DEEP_RESEARCH (Kimi) — conditional
            run = await self._execute_deep_research_stage(run, lead_name)
            if StateMachine.is_run_terminal(run.status):
                return run

            # Stage 4: AUDIT (Claude)
            run = await self._execute_audit_stage(run, lead_name)
            if StateMachine.is_run_terminal(run.status):
                return run

            # Stage 5: SCORING
            run = await self._execute_scoring_stage(run, lead_name)
            if StateMachine.is_run_terminal(run.status):
                return run

            # Stage 6: APPROVAL
            run = await self._execute_approval_stage(run, lead_name)
            if StateMachine.is_run_terminal(run.status):
                return run
            # If run is paused or waiting for approval, stop here
            if run.status == RunStatus.PAUSED:
                return run
            stages = await self.engine.persistence.get_stages_for_run(run.run_id)
            approval_stages = [s for s in stages if s.stage_type == StageType.APPROVAL]
            if approval_stages and approval_stages[-1].status == StageStatus.WAITING_FOR_APPROVAL:
                return run

            # Stage 7: DELIVERY
            run = await self._execute_delivery_stage(run, lead_name)
            if StateMachine.is_run_terminal(run.status):
                return run
            if run.status == RunStatus.PAUSED:
                return run

            # Stage 8: FINALIZATION
            run = await self._execute_finalization_stage(run)
            return run

        except Exception as exc:
            log_event(
                logger,
                "ERROR",
                f"Workflow execution failed: {exc}",
                run_id=run.run_id,
                context={"error": str(exc)},
            )
            await self.engine.run_manager.fail_run(run, str(exc))
            return run

    async def continue_run(self, run: Run, lead_name: str, industry: str, summary: str) -> Run:
        """Continue a run from the DELIVERY stage (used after approval resume)."""
        if StateMachine.is_run_terminal(run.status):
            return run
        try:
            run = await self._execute_delivery_stage(run, lead_name)
            if StateMachine.is_run_terminal(run.status):
                return run
            if run.status == RunStatus.PAUSED:
                return run
            run = await self._execute_finalization_stage(run)
            return run
        except Exception as exc:
            log_event(
                logger,
                "ERROR",
                f"Workflow continuation failed: {exc}",
                run_id=run.run_id,
                context={"error": str(exc)},
            )
            await self.engine.run_manager.fail_run(run, str(exc))
            return run

    # ------------------------------------------------------------------
    # Stage: RESEARCH
    # ------------------------------------------------------------------
    async def _execute_research_stage(
        self,
        run: Run,
        lead_name: str,
        industry: str,
        summary: str,
        initial_claims: list[str] | None,
        sources: list[str] | None,
    ) -> Run:
        """Execute the RESEARCH stage with Gemini."""
        stage = await self.engine.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=StageType.RESEARCH,
        )
        stage = await self.engine.stage_manager.start_stage(stage)

        # Create and persist RESEARCH_BRIEF artifact
        brief_payload = {
            "lead_name": lead_name,
            "industry": industry,
            "summary": summary,
            "initial_claims": initial_claims or [],
            "sources": sources or [],
        }
        try:
            brief_artifact = ArtifactFactory.create(
                run_id=run.run_id,
                artifact_type=ArtifactType.RESEARCH_BRIEF,
                payload=brief_payload,
                producer="orchestrator",
            )
            await self.engine.persistence.create_artifact(brief_artifact)
        except ArtifactValidationError as exc:
            log_event(logger, "ERROR", f"Research brief validation failed: {exc}", run_id=run.run_id)
            await self.engine.stage_manager.fail_stage(stage, str(exc))
            await self._reject_run(run, RejectionCategory.QUALITY_FAILURE, str(exc), stage)
            return run

        # Call Gemini adapter if available
        gemini = self.engine.adapters.get("gemini")
        if gemini:
            try:
                request = self._build_agent_request(
                    run, stage, "gemini", self._build_research_prompt(brief_payload)
                )
                response = await gemini.send_request(request)
                evidence_data = self._safe_parse_json(response.content)
                evidence_data["lead_name"] = lead_name

                evidence_artifact = ArtifactFactory.create(
                    run_id=run.run_id,
                    artifact_type=ArtifactType.EVIDENCE_PACKET,
                    payload=evidence_data,
                    producer="gemini",
                )
                await self.engine.persistence.create_artifact(evidence_artifact)
                log_event(
                    logger,
                    "INFO",
                    "Evidence packet received from Gemini",
                    run_id=run.run_id,
                    stage_id=stage.stage_id,
                )
            except (AgentError, ArtifactValidationError) as exc:
                log_event(logger, "ERROR", f"Gemini research failed: {exc}", run_id=run.run_id)
                await self.engine.stage_manager.fail_stage(stage, str(exc))
                if stage.retry_count < stage.max_retries:
                    await self.engine.stage_manager.retry_stage(stage)
                    # In a real system we'd re-queue; here we fail the run for simplicity
                await self._reject_run(run, RejectionCategory.SYSTEM_ERROR, str(exc), stage)
                return run
        else:
            # No adapter — create synthetic evidence for testing
            evidence_artifact = ArtifactFactory.create(
                run_id=run.run_id,
                artifact_type=ArtifactType.EVIDENCE_PACKET,
                payload={
                    "lead_name": lead_name,
                    "evidence_items": [
                        {
                            "claim": f"{lead_name} operates in {industry}",
                            "confidence": "HIGH",
                            "category": "BUSINESS_INFO",
                        }
                    ],
                    "missing_categories": [],
                    "total_claims": 1,
                    "verified_claims": 1,
                },
                producer="orchestrator_mock",
            )
            await self.engine.persistence.create_artifact(evidence_artifact)

        stage = await self.engine.stage_manager.complete_stage(stage)
        return run

    # ------------------------------------------------------------------
    # Stage: SCREENING
    # ------------------------------------------------------------------
    async def _execute_screening_stage(self, run: Run, lead_name: str) -> Run:
        """Execute the SCREENING stage — sufficiency check."""
        stage = await self.engine.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=StageType.SCREENING,
        )
        stage = await self.engine.stage_manager.start_stage(stage)

        artifacts = await self.engine.persistence.get_artifacts_for_run(run.run_id)
        evidence_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.EVIDENCE_PACKET]

        if not evidence_artifacts:
            reason = "No evidence packet found for screening"
            await self.engine.stage_manager.fail_stage(stage, reason)
            await self._reject_run(run, RejectionCategory.INSUFFICIENT_EVIDENCE, reason, stage)
            return run

        evidence_payload = evidence_artifacts[-1].payload
        evidence_packet = EvidencePacket(**evidence_payload)

        # OpenAI screening enrichment (non-authoritative)
        openai_result = None
        chatgpt = self.engine.adapters.get("chatgpt")
        if chatgpt:
            try:
                health = await chatgpt.health_check()
                if health == HealthStatus.HEALTHY:
                    request = self._build_agent_request(
                        run, stage, "chatgpt", self._build_screening_prompt(evidence_packet)
                    )
                    response = await chatgpt.send_request(request)
                    openai_result = self._parse_screening_response(response.content)
                    log_event(
                        logger,
                        "INFO",
                        f"OpenAI screening: {openai_result.get('recommendation', 'UNKNOWN')}",
                        run_id=run.run_id,
                        stage_id=stage.stage_id,
                    )
                    if openai_result.get("concerns"):
                        log_event(
                            logger,
                            "WARNING",
                            f"OpenAI concerns: {openai_result['concerns']}",
                            run_id=run.run_id,
                            stage_id=stage.stage_id,
                        )
            except Exception as exc:
                log_event(logger, "WARNING", f"OpenAI screening failed, using deterministic fallback: {exc}")

        # Screening criteria — deterministic remains authoritative
        sufficient = self._screen_evidence(evidence_packet)

        if not sufficient:
            reason = (
                f"Insufficient evidence for {lead_name}: "
                f"{len(evidence_packet.evidence_items)} items, "
                f"{evidence_packet.verified_claims} verified"
            )
            await self.engine.stage_manager.reject_stage(stage, reason)
            await self._reject_run(run, RejectionCategory.INSUFFICIENT_EVIDENCE, reason, stage)
            return run

        stage = await self.engine.stage_manager.complete_stage(stage)
        log_event(
            logger,
            "INFO",
            f"Screening passed for {lead_name}",
            run_id=run.run_id,
            stage_id=stage.stage_id,
        )
        return run

    def _screen_evidence(self, evidence: EvidencePacket) -> bool:
        """Check if evidence meets minimum screening criteria."""
        if len(evidence.evidence_items) < self._screening_min_evidence:
            return False
        high_medium_count = sum(
            1 for e in evidence.evidence_items
            if e.confidence in ("HIGH", "MEDIUM")
        )
        if high_medium_count < 1:
            return False
        return True

    def _build_screening_prompt(self, evidence: EvidencePacket) -> str:
        """Build screening prompt for OpenAI."""
        items = evidence.evidence_items
        return (
            "You are a lead screening analyst. Review the evidence and return JSON:\n"
            '{\n  "recommendation": "PASS" or "FAIL",\n'
            '  "confidence": "HIGH", "MEDIUM", or "LOW",\n'
            '  "rationale": "explanation",\n  "concerns": ["list"]\n}\n\n'
            f"Evidence items: {len(items)}\n"
            f"Details: {[getattr(i, 'claim', str(i)) for i in items]}"
        )

    def _parse_screening_response(self, content: str) -> dict[str, Any]:
        """Safely parse OpenAI screening response."""
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            return json.loads(content)
        except Exception:
            return {"recommendation": "PASS", "rationale": "Parse failed, defaulting to PASS", "concerns": []}

    # ------------------------------------------------------------------
    # Stage: DEEP_RESEARCH
    # ------------------------------------------------------------------
    async def _execute_deep_research_stage(self, run: Run, lead_name: str) -> Run:
        """Execute the DEEP_RESEARCH stage with Kimi — conditional."""
        stage = await self.engine.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=StageType.DEEP_RESEARCH,
        )
        stage = await self.engine.stage_manager.start_stage(stage)

        # Decision: proceed to deep research based on evidence quality
        artifacts = await self.engine.persistence.get_artifacts_for_run(run.run_id)
        evidence_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.EVIDENCE_PACKET]
        if evidence_artifacts:
            evidence = EvidencePacket(**evidence_artifacts[-1].payload)
            evidence_score = self._quick_evidence_score(evidence)
            if evidence_score < self._deep_research_threshold:
                log_event(
                    logger,
                    "INFO",
                    f"Skipping deep research for {lead_name} (score {evidence_score})",
                    run_id=run.run_id,
                )
                stage = await self.engine.stage_manager.skip_stage(stage)
                return run

        # Create DEEP_RESEARCH_BRIEF
        deep_brief_payload = {
            "lead_name": lead_name,
            "deep_claims": ["Verify financial stability", "Check leadership team"],
            "evidence_quality": "GOOD",
        }
        try:
            deep_brief_artifact = ArtifactFactory.create(
                run_id=run.run_id,
                artifact_type=ArtifactType.DEEP_RESEARCH_BRIEF,
                payload=deep_brief_payload,
                producer="orchestrator",
            )
            await self.engine.persistence.create_artifact(deep_brief_artifact)
        except ArtifactValidationError as exc:
            await self.engine.stage_manager.fail_stage(stage, str(exc))
            await self._reject_run(run, RejectionCategory.QUALITY_FAILURE, str(exc), stage)
            return run

        # Call Kimi adapter if available
        kimi = self.engine.adapters.get("kimi")
        if kimi:
            try:
                request = self._build_agent_request(
                    run, stage, "kimi", self._build_deep_research_prompt(deep_brief_payload)
                )
                response = await kimi.send_request(request)
                update_data = self._safe_parse_json(response.content)
                update_data["lead_name"] = lead_name

                update_artifact = ArtifactFactory.create(
                    run_id=run.run_id,
                    artifact_type=ArtifactType.RESEARCH_UPDATE,
                    payload=update_data,
                    producer="kimi",
                )
                await self.engine.persistence.create_artifact(update_artifact)
            except (AgentError, ArtifactValidationError) as exc:
                log_event(logger, "ERROR", f"Kimi deep research failed: {exc}", run_id=run.run_id)
                await self.engine.stage_manager.fail_stage(stage, str(exc))
                if stage.retry_count < stage.max_retries:
                    await self.engine.stage_manager.retry_stage(stage)
                await self._reject_run(run, RejectionCategory.SYSTEM_ERROR, str(exc), stage)
                return run
        else:
            update_artifact = ArtifactFactory.create(
                run_id=run.run_id,
                artifact_type=ArtifactType.RESEARCH_UPDATE,
                payload={
                    "lead_name": lead_name,
                    "update_type": "REFINEMENT",
                    "updated_claims": ["Deep research completed via mock"],
                },
                producer="orchestrator_mock",
            )
            await self.engine.persistence.create_artifact(update_artifact)

        stage = await self.engine.stage_manager.complete_stage(stage)
        return run

    # ------------------------------------------------------------------
    # Stage: AUDIT
    # ------------------------------------------------------------------
    async def _execute_audit_stage(self, run: Run, lead_name: str) -> Run:
        """Execute the AUDIT stage with Claude."""
        stage = await self.engine.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=StageType.AUDIT,
        )
        stage = await self.engine.stage_manager.start_stage(stage)

        artifacts = await self.engine.persistence.get_artifacts_for_run(run.run_id)
        evidence_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.EVIDENCE_PACKET]
        if not evidence_artifacts:
            reason = "No evidence for audit"
            await self.engine.stage_manager.fail_stage(stage, reason)
            await self._reject_run(run, RejectionCategory.INSUFFICIENT_EVIDENCE, reason, stage)
            return run

        evidence = EvidencePacket(**evidence_artifacts[-1].payload)

        # Build audit packet
        audit_packet_payload = {
            "lead_name": lead_name,
            "audit_items": [
                {
                    "claim": item.claim,
                    "evidence_found": item.confidence in ("HIGH", "MEDIUM"),
                    "evidence_source": item.source_url or "unknown",
                    "auditor_notes": "",
                    "confidence": item.confidence,
                }
                for item in evidence.evidence_items
            ],
            "overall_confidence": "MEDIUM",
            "discrepancies_found": 0,
        }
        try:
            audit_packet_artifact = ArtifactFactory.create(
                run_id=run.run_id,
                artifact_type=ArtifactType.AUDIT_PACKET,
                payload=audit_packet_payload,
                producer="orchestrator",
            )
            await self.engine.persistence.create_artifact(audit_packet_artifact)
        except ArtifactValidationError as exc:
            await self.engine.stage_manager.fail_stage(stage, str(exc))
            await self._reject_run(run, RejectionCategory.QUALITY_FAILURE, str(exc), stage)
            return run

        # Call Claude adapter if available
        claude = self.engine.adapters.get("claude")
        if claude:
            try:
                request = self._build_agent_request(
                    run, stage, "claude", self._build_audit_prompt(audit_packet_payload)
                )
                response = await claude.send_request(request)
                report_data = self._safe_parse_json(response.content)
                report_data["lead_name"] = lead_name

                report_artifact = ArtifactFactory.create(
                    run_id=run.run_id,
                    artifact_type=ArtifactType.AUDIT_REPORT,
                    payload=report_data,
                    producer="claude",
                )
                await self.engine.persistence.create_artifact(report_artifact)
            except (AgentError, ArtifactValidationError) as exc:
                log_event(logger, "ERROR", f"Claude audit failed: {exc}", run_id=run.run_id)
                await self.engine.stage_manager.fail_stage(stage, str(exc))
                if stage.retry_count < stage.max_retries:
                    await self.engine.stage_manager.retry_stage(stage)
                await self._reject_run(run, RejectionCategory.SYSTEM_ERROR, str(exc), stage)
                return run
        else:
            report_artifact = ArtifactFactory.create(
                run_id=run.run_id,
                artifact_type=ArtifactType.AUDIT_REPORT,
                payload={
                    "lead_name": lead_name,
                    "summary": "Mock audit passed",
                    "recommendations": [],
                    "pass_fail": "PASS",
                    "score": 85,
                },
                producer="orchestrator_mock",
            )
            await self.engine.persistence.create_artifact(report_artifact)

        stage = await self.engine.stage_manager.complete_stage(stage)
        return run

    # ------------------------------------------------------------------
    # Stage: SCORING
    # ------------------------------------------------------------------
    async def _execute_scoring_stage(self, run: Run, lead_name: str) -> Run:
        """Execute the SCORING stage."""
        stage = await self.engine.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=StageType.SCORING,
        )
        stage = await self.engine.stage_manager.start_stage(stage)

        artifacts = await self.engine.persistence.get_artifacts_for_run(run.run_id)

        # Gather inputs for scoring
        evidence = self._find_artifact_payload(artifacts, ArtifactType.EVIDENCE_PACKET, EvidencePacket)
        audit_report = self._find_artifact_payload(artifacts, ArtifactType.AUDIT_REPORT, AuditReport)

        # Build final dossier
        dossier_payload = self._build_dossier_payload(lead_name, artifacts)
        try:
            dossier_artifact = ArtifactFactory.create(
                run_id=run.run_id,
                artifact_type=ArtifactType.FINAL_DOSSIER,
                payload=dossier_payload,
                producer="orchestrator",
            )
            await self.engine.persistence.create_artifact(dossier_artifact)
        except ArtifactValidationError as exc:
            await self.engine.stage_manager.fail_stage(stage, str(exc))
            await self._reject_run(run, RejectionCategory.QUALITY_FAILURE, str(exc), stage)
            return run

        dossier = FinalDossier(**dossier_artifact.payload)

        # Score
        try:
            score_result = self.scoring_engine.score(dossier, evidence, audit_report)
            score_artifact = ArtifactFactory.create(
                run_id=run.run_id,
                artifact_type=ArtifactType.SCORE_RESULT,
                payload=score_result.model_dump(mode="json"),
                producer="scoring_engine",
            )
            await self.engine.persistence.create_artifact(score_artifact)
        except ScoringError as exc:
            await self.engine.stage_manager.fail_stage(stage, str(exc))
            await self._reject_run(run, RejectionCategory.SYSTEM_ERROR, str(exc), stage)
            return run

        # Check auto-reject
        decision = self.scoring_engine.decide(score_result)
        if decision.threshold == ScoreThreshold.AUTO_REJECT:
            reason = f"Auto-rejected: score {score_result.overall_score} below threshold"
            await self.engine.stage_manager.reject_stage(stage, reason)
            await self._reject_run(run, RejectionCategory.AUDIT_FAILURE, reason, stage)
            return run

        stage = await self.engine.stage_manager.complete_stage(stage)
        log_event(
            logger,
            "INFO",
            f"Scoring complete for {lead_name}: {score_result.overall_score}",
            run_id=run.run_id,
            stage_id=stage.stage_id,
        )
        return run

    # ------------------------------------------------------------------
    # Stage: APPROVAL
    # ------------------------------------------------------------------
    async def _execute_approval_stage(self, run: Run, lead_name: str) -> Run:
        """Execute the APPROVAL stage."""
        stage = await self.engine.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=StageType.APPROVAL,
        )
        stage = await self.engine.stage_manager.start_stage(stage)

        artifacts = await self.engine.persistence.get_artifacts_for_run(run.run_id)
        score_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.SCORE_RESULT]
        if not score_artifacts:
            reason = "No score result for approval"
            await self.engine.stage_manager.fail_stage(stage, reason)
            await self._reject_run(run, RejectionCategory.SYSTEM_ERROR, reason, stage)
            return run

        score_result = ScoreResult(**score_artifacts[-1].payload)
        decision = self.scoring_engine.decide(score_result)

        if decision.threshold == ScoreThreshold.AUTO_APPROVE:
            # Auto-approve
            stage = await self.engine.stage_manager.complete_stage(stage)
            await self.engine.persistence.create_event(
                Event(
                    run_id=run.run_id,
                    stage_id=stage.stage_id,
                    event_type=EventType.APPROVAL_DECIDED,
                    payload={"decision": "AUTO_APPROVED", "rationale": decision.rationale},
                )
            )
            log_event(
                logger,
                "INFO",
                f"Auto-approved {lead_name}",
                run_id=run.run_id,
                stage_id=stage.stage_id,
            )
            return run

        # Require manual approval
        if self.approval_service:
            await self.approval_service.create_approval_request(
                run_id=run.run_id,
                stage_id=stage.stage_id,
                approval_type=ApprovalType.MANUAL_REVIEW,
                request_details={
                    "lead_name": lead_name,
                    "overall_score": score_result.overall_score,
                    "rationale": decision.rationale,
                },
                timeout_seconds=self.config.get("approval_timeout_seconds", 86400),
            )
            # Stage is already set to WAITING_FOR_APPROVAL by ApprovalService
            log_event(
                logger,
                "INFO",
                f"Approval requested for {lead_name}",
                run_id=run.run_id,
                stage_id=stage.stage_id,
            )
        else:
            # No approval service — simulate approval for testing
            stage = await self.engine.stage_manager.request_approval(stage)
            stage = await self.engine.approve_stage(stage, "workflow_auto", "Simulated approval")
        return run

    # ------------------------------------------------------------------
    # Stage: DELIVERY
    # ------------------------------------------------------------------
    async def _execute_delivery_stage(self, run: Run, lead_name: str) -> Run:
        """Execute the DELIVERY stage."""
        stage = await self.engine.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=StageType.DELIVERY,
        )
        stage = await self.engine.stage_manager.start_stage(stage)

        if self.delivery:
            artifacts = await self.engine.persistence.get_artifacts_for_run(run.run_id)
            dossier_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.FINAL_DOSSIER]
            if dossier_artifacts:
                dossier = FinalDossier(**dossier_artifacts[-1].payload)
                try:
                    recipients = self.config.get("delivery_recipients", ["admin@example.com"])
                    await self.delivery.send(dossier, recipients)
                    await self.engine.persistence.create_event(
                        Event(
                            run_id=run.run_id,
                            stage_id=stage.stage_id,
                            event_type=EventType.DELIVERY_SUCCEEDED,
                            payload={"recipients": recipients},
                        )
                    )
                except Exception as exc:
                    log_event(logger, "ERROR", f"Delivery failed: {exc}", run_id=run.run_id)
                    await self.engine.persistence.create_event(
                        Event(
                            run_id=run.run_id,
                            stage_id=stage.stage_id,
                            event_type=EventType.DELIVERY_FAILED,
                            payload={"error": str(exc)},
                        )
                    )
                    # Delivery failure doesn't fail the run

        stage = await self.engine.stage_manager.complete_stage(stage)
        return run

    # ------------------------------------------------------------------
    # Stage: FINALIZATION
    # ------------------------------------------------------------------
    async def _execute_finalization_stage(self, run: Run) -> Run:
        """Execute the FINALIZATION stage."""
        stage = await self.engine.stage_manager.create_stage(
            run_id=run.run_id,
            stage_type=StageType.FINALIZATION,
        )
        stage = await self.engine.stage_manager.start_stage(stage)
        stage = await self.engine.stage_manager.complete_stage(stage)
        run = await self.engine.run_manager.complete_run(run)
        return run

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _reject_run(
        self,
        run: Run,
        category: RejectionCategory,
        reason: str,
        stage: Stage,
    ) -> None:
        """Execute deterministic rejection path."""
        rejection = RejectionReason(
            category=category,
            reason=reason,
            stage=stage.stage_type,
        )
        await self.engine.persistence.create_event(
            Event(
                run_id=run.run_id,
                stage_id=stage.stage_id,
                event_type=EventType.STAGE_REJECTED,
                payload={
                    "category": category.name,
                    "reason": reason,
                    "stage": stage.stage_type.name,
                },
            )
        )
        await self.engine.run_manager.reject_run(run, reason)

    def _build_agent_request(
        self,
        run: Run,
        stage: Stage,
        agent_name: str,
        prompt: str,
    ) -> AgentRequest:
        """Build an AgentRequest for the given stage."""
        return AgentRequest(
            request_id=uuid4(),
            run_id=run.run_id,
            correlation_id=run.correlation_id,
            stage_id=stage.stage_id,
            agent_name=agent_name,
            prompt=prompt,
            context={"lead_name": run.metadata.get("lead_name", "unknown")},
            max_tokens=4096,
            temperature=0.0,
            timeout_seconds=60.0,
            attempt_number=stage.retry_count + 1,
        )

    def _build_research_prompt(self, brief: dict[str, Any]) -> str:
        """Build research prompt for Gemini."""
        return (
            f"Research the company: {brief['lead_name']}\n"
            f"Industry: {brief['industry']}\n"
            f"Summary: {brief['summary']}\n"
            "Return a JSON object with fields: "
            "lead_name, evidence_items (list of {claim, source_url, source_title, confidence, category, excerpt}), "
            "missing_categories (list), total_claims (int), verified_claims (int)"
        )

    def _build_deep_research_prompt(self, brief: dict[str, Any]) -> str:
        """Build deep research prompt for Kimi."""
        return (
            f"Perform deep research on: {brief['lead_name']}\n"
            "Return a JSON object with fields: "
            "lead_name, update_type (NEW_EVIDENCE/CORRECTION/REFINEMENT), "
            "updated_claims (list), previous_version_id (optional)"
        )

    def _build_audit_prompt(self, audit_packet: dict[str, Any]) -> str:
        """Build audit prompt for Claude."""
        return (
            f"Audit the evidence for: {audit_packet['lead_name']}\n"
            f"Audit items: {json.dumps(audit_packet['audit_items'])}\n"
            "Return a JSON object with fields: "
            "lead_name, summary, recommendations (list), pass_fail (PASS/FAIL), score (0-100)"
        )

    def _safe_parse_json(self, content: str) -> dict[str, Any]:
        """Safely parse JSON from agent response."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in content:
                json_part = content.split("```json")[1].split("```")[0].strip()
                return json.loads(json_part)
            elif "```" in content:
                json_part = content.split("```")[1].split("```")[0].strip()
                return json.loads(json_part)
            raise

    def _quick_evidence_score(self, evidence: EvidencePacket) -> int:
        """Quick heuristic score for deep research decision."""
        total = max(evidence.total_claims, len(evidence.evidence_items))
        if total == 0:
            return 0
        return int((evidence.verified_claims / total) * 100)

    def _find_artifact_payload(
        self,
        artifacts: list[Artifact],
        artifact_type: ArtifactType,
        model_class: type,
    ) -> Any | None:
        """Find and parse the most recent artifact of a given type."""
        matching = [a for a in artifacts if a.artifact_type == artifact_type]
        if not matching:
            return None
        return model_class(**matching[-1].payload)

    def _build_dossier_payload(self, lead_name: str, artifacts: list[Artifact]) -> dict[str, Any]:
        """Build final dossier payload from accumulated artifacts."""
        evidence = self._find_artifact_payload(artifacts, ArtifactType.EVIDENCE_PACKET, EvidencePacket)
        audit_report = self._find_artifact_payload(artifacts, ArtifactType.AUDIT_REPORT, AuditReport)

        key_evidence = evidence.evidence_items if evidence else []
        business_viability = "Good business viability"
        online_presence = "Moderate online presence"
        contact_info = None

        if evidence and evidence.evidence_items:
            for item in evidence.evidence_items:
                if item.category == "CONTACT" and item.excerpt:
                    contact_info = item.excerpt
                if item.category == "BUSINESS_INFO" and item.excerpt:
                    business_viability = item.excerpt
                if item.category == "ONLINE_PRESENCE" and item.excerpt:
                    online_presence = item.excerpt

        recommendation = "PENDING"
        if audit_report:
            recommendation = "APPROVE" if audit_report.pass_fail == "PASS" else "REJECT"

        return {
            "lead_name": lead_name,
            "company_summary": f"Lead dossier for {lead_name}",
            "key_evidence": [item.model_dump(mode="json") for item in key_evidence],
            "business_viability": business_viability,
            "online_presence": online_presence,
            "contact_info": contact_info or "Email: contact@example.com",
            "final_score": audit_report.score if audit_report else None,
            "recommendation": recommendation,
        }
