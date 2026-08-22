"""Unit tests for EmailDelivery."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lead_hunter.artifacts.schemas import FinalDossier
from lead_hunter.delivery.email_delivery import DeliveryMetrics, EmailDelivery
from lead_hunter.orchestrator.interfaces import HealthStatus


class TestEmailDelivery:
    def _make_dossier(self) -> FinalDossier:
        return FinalDossier(
            lead_name="TestCo",
            company_summary="A test company",
            business_viability="Good",
            online_presence="Strong",
            contact_info="test@example.com",
            recommendation="APPROVE",
            final_score=85,
        )

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        delivery = EmailDelivery(smtp_host="localhost", smtp_port=587)
        dossier = self._make_dossier()

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp_class.return_value = mock_smtp

            result = await delivery.send(dossier, ["recipient@example.com"])

            assert result.success is True
            assert result.recipients == ["recipient@example.com"]
            assert result.error_message is None
            mock_smtp.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_with_custom_subject(self) -> None:
        delivery = EmailDelivery()
        dossier = self._make_dossier()

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp_class.return_value = mock_smtp

            result = await delivery.send(
                dossier, ["r@example.com"], subject="Custom Subject"
            )
            assert result.success is True
            call_args = mock_smtp.sendmail.call_args
            msg_str = call_args[0][2]
            assert "Custom Subject" in msg_str

    @pytest.mark.asyncio
    async def test_send_with_template(self) -> None:
        import base64, re
        delivery = EmailDelivery()
        dossier = self._make_dossier()
        template = "<html><body><h1>{lead_name}</h1></body></html>"

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp_class.return_value = mock_smtp

            result = await delivery.send(
                dossier, ["r@example.com"], template=template
            )
            assert result.success is True
            call_args = mock_smtp.sendmail.call_args
            msg_str = call_args[0][2]
            # Extract base64-encoded HTML part
            match = re.search(r"Content-Type: text/html.*?\n\n([A-Za-z0-9+/=\s]+)", msg_str, re.DOTALL)
            assert match is not None
            b64 = match.group(1).replace("\n", "").replace(" ", "")
            decoded = base64.b64decode(b64).decode("utf-8")
            assert "<h1>TestCo</h1>" in decoded

    @pytest.mark.asyncio
    async def test_send_with_attachment(self) -> None:
        delivery = EmailDelivery()
        dossier = self._make_dossier()
        attachments = [
            {"filename": "report.pdf", "content": b"PDFDATA", "mime_type": "application/pdf"}
        ]

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp_class.return_value = mock_smtp

            result = await delivery.send(
                dossier, ["r@example.com"], attachments=attachments
            )
            assert result.success is True
            call_args = mock_smtp.sendmail.call_args
            msg_str = call_args[0][2]
            assert "report.pdf" in msg_str

    @pytest.mark.asyncio
    async def test_send_retry_then_success(self) -> None:
        delivery = EmailDelivery(max_retries=2, base_delay=0.01)
        dossier = self._make_dossier()

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            # First call fails, second succeeds
            mock_smtp.sendmail.side_effect = [Exception("SMTP error"), None]
            mock_smtp_class.return_value = mock_smtp

            result = await delivery.send(dossier, ["r@example.com"])
            assert result.success is True
            assert result.retry_count == 1
            assert mock_smtp.sendmail.call_count == 2

    @pytest.mark.asyncio
    async def test_send_all_retries_fail(self) -> None:
        delivery = EmailDelivery(max_retries=2, base_delay=0.01)
        dossier = self._make_dossier()

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp.sendmail.side_effect = Exception("SMTP error")
            mock_smtp_class.return_value = mock_smtp

            result = await delivery.send(dossier, ["r@example.com"])
            assert result.success is False
            assert result.error_message is not None
            assert result.retry_count == 2
            assert mock_smtp.sendmail.call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_health_check_healthy(self) -> None:
        delivery = EmailDelivery()

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp_class.return_value = mock_smtp

            status = await delivery.health_check()
            assert status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self) -> None:
        delivery = EmailDelivery()

        with patch("smtplib.SMTP", side_effect=Exception("Connection refused")):
            status = await delivery.health_check()
            assert status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_send_batch(self) -> None:
        delivery = EmailDelivery()
        dossier1 = self._make_dossier()
        dossier2 = FinalDossier(
            lead_name="Co2",
            company_summary="Another company",
            business_viability="Moderate",
            online_presence="Limited",
        )

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp = MagicMock()
            mock_smtp_class.return_value = mock_smtp

            results = await delivery.send_batch([
                (dossier1, ["a@example.com"]),
                (dossier2, ["b@example.com"]),
            ])

            assert len(results) == 2
            assert all(r.success for r in results)
            assert mock_smtp.sendmail.call_count == 2

    def test_metrics_tracking(self) -> None:
        metrics = DeliveryMetrics()
        assert metrics.total_attempts == 0
        assert metrics.successful_deliveries == 0
        assert metrics.failed_deliveries == 0
        metrics.total_attempts = 5
        metrics.successful_deliveries = 4
        metrics.failed_deliveries = 1
        assert metrics.retries == 0
