"""Integration tests for delivery within the workflow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lead_hunter.delivery.email_delivery import EmailDelivery
from lead_hunter.models.domain import ArtifactType, RunStatus
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow


@pytest.mark.asyncio
class TestDeliveryIntegration:
    async def test_workflow_with_email_delivery(self) -> None:
        """Full workflow with email delivery at the end."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)

        mock_delivery = AsyncMock()
        mock_delivery.send = AsyncMock(return_value=None)

        workflow = LeadHunterWorkflow(
            engine,
            delivery=mock_delivery,
            config={"screening_min_evidence": 1, "delivery_recipients": ["admin@example.com"]},
        )

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="DeliverCo",
            industry="Tech",
            summary="A deliverable lead",
        )

        assert run.status == RunStatus.COMPLETED
        mock_delivery.send.assert_called_once()
        call_args = mock_delivery.send.call_args
        dossier_arg = call_args[0][0]
        recipients_arg = call_args[0][1]
        assert dossier_arg.lead_name == "DeliverCo"
        assert recipients_arg == ["admin@example.com"]

    async def test_delivery_failure_does_not_fail_run(self) -> None:
        """Delivery failure should not cause the run to fail."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)

        mock_delivery = AsyncMock()
        mock_delivery.send = AsyncMock(side_effect=Exception("SMTP down"))

        workflow = LeadHunterWorkflow(
            engine,
            delivery=mock_delivery,
            config={"screening_min_evidence": 1, "delivery_recipients": ["admin@example.com"]},
        )

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="FailDeliverCo",
            industry="Tech",
            summary="A lead whose delivery fails",
        )

        assert run.status == RunStatus.COMPLETED
        mock_delivery.send.assert_called_once()

    async def test_email_delivery_rendering(self) -> None:
        """Verify email content is properly rendered from dossier."""
        import base64, re
        from lead_hunter.artifacts.schemas import FinalDossier
        delivery = EmailDelivery()
        dossier = FinalDossier(
            lead_name="RenderCo",
            company_summary="A rendering company",
            business_viability="Excellent",
            online_presence="Strong",
            contact_info="render@example.com",
            recommendation="APPROVE",
            final_score=92,
        )

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp_class.return_value = mock_smtp

            result = await delivery.send(
                dossier,
                ["recipient@example.com"],
                subject="Lead: {lead_name}".format(lead_name=dossier.lead_name),
            )
            assert result.success is True
            call_args = mock_smtp.sendmail.call_args
            msg_str = call_args[0][2]
            # Decode base64 text/plain part
            match = re.search(r"Content-Type: text/plain.*?\n\n([A-Za-z0-9+/=\s]+)", msg_str, re.DOTALL)
            assert match is not None
            b64 = match.group(1).replace("\n", "").replace(" ", "")
            decoded = base64.b64decode(b64).decode("utf-8")
            assert "RenderCo" in decoded
            assert "92" in decoded
            assert "render@example.com" in decoded

    async def test_delivery_metrics_accumulate(self) -> None:
        """Verify delivery metrics track successes and failures."""
        from lead_hunter.artifacts.schemas import FinalDossier
        delivery = EmailDelivery(max_retries=1, base_delay=0.01)
        dossier = FinalDossier(
            lead_name="MetricsCo",
            company_summary="Metrics test",
            business_viability="Good",
            online_presence="Good",
        )

        # First send succeeds
        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp_class.return_value = mock_smtp
            await delivery.send(dossier, ["a@example.com"])

        # Reset cached SMTP so second patch is used
        delivery._smtp = None

        # Second send fails
        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp.sendmail.side_effect = Exception("fail")
            mock_smtp_class.return_value = mock_smtp
            await delivery.send(dossier, ["b@example.com"])

        assert delivery.metrics.total_attempts == 3  # 1 success + 2 failed attempts (initial + 1 retry)
        assert delivery.metrics.successful_deliveries == 1
        assert delivery.metrics.failed_deliveries == 1
