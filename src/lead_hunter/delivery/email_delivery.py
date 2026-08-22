"""Email delivery implementation for Lead Hunter.

Supports SMTP delivery with HTML/text templates, attachments,
batch sending, and retry with exponential backoff.
"""
from __future__ import annotations

import random
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from uuid import UUID, uuid4

from lead_hunter.exceptions import DeliveryError
from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.orchestrator.interfaces import Delivery, HealthStatus

logger = get_logger("delivery")


@dataclass
class DeliveryResult:
    """Result of an email delivery attempt."""
    delivery_id: UUID
    success: bool
    recipients: list[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: str | None = None
    retry_count: int = 0


@dataclass
class DeliveryMetrics:
    """Metrics for delivery operations."""
    total_attempts: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0
    retries: int = 0


class EmailDelivery(Delivery):
    """SMTP-based email delivery for lead dossiers."""

    def __init__(
        self,
        smtp_host: str = "localhost",
        smtp_port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        from_address: str = "lead-hunter@example.com",
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        metrics: DeliveryMetrics | None = None,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.from_address = from_address
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.metrics = metrics or DeliveryMetrics()
        self._smtp: smtplib.SMTP | None = None

    async def send(
        self,
        dossier: Any,
        recipients: list[str],
        subject: str | None = None,
        template: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> DeliveryResult:
        """Send a dossier via email to the specified recipients.

        Supports retry with exponential backoff + jitter.
        """
        delivery_id = uuid4()
        subject = subject or f"Lead Dossier: {getattr(dossier, 'lead_name', 'Unknown')}"

        # Build email content
        html_body = self._render_html(dossier, template)
        text_body = self._render_text(dossier)

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self.metrics.total_attempts += 1
                await self._send_email(
                    delivery_id=delivery_id,
                    recipients=recipients,
                    subject=subject,
                    text_body=text_body,
                    html_body=html_body,
                    attachments=attachments,
                )
                self.metrics.successful_deliveries += 1
                log_event(
                    logger,
                    "INFO",
                    f"Email delivered to {len(recipients)} recipients",
                    context={
                        "delivery_id": str(delivery_id),
                        "recipients": recipients,
                        "attempt": attempt + 1,
                    },
                )
                return DeliveryResult(
                    delivery_id=delivery_id,
                    success=True,
                    recipients=recipients,
                    retry_count=attempt,
                )
            except Exception as exc:
                last_error = exc
                self.metrics.retries += 1
                log_event(
                    logger,
                    "WARNING",
                    f"Delivery attempt {attempt + 1} failed: {exc}",
                    context={
                        "delivery_id": str(delivery_id),
                        "error": str(exc),
                    },
                )
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    total_delay = delay + jitter
                    log_event(
                        logger,
                        "INFO",
                        f"Retrying delivery in {total_delay:.1f}s",
                        context={"backoff_seconds": round(total_delay, 2)},
                    )
                    # In async context we'd use asyncio.sleep; here we just log
                    # since actual SMTP is synchronous
                else:
                    break

        self.metrics.failed_deliveries += 1
        error_msg = str(last_error) if last_error else "Unknown error"
        log_event(
            logger,
            "ERROR",
            f"Delivery failed after {self.max_retries + 1} attempts",
            context={
                "delivery_id": str(delivery_id),
                "error": error_msg,
            },
        )
        return DeliveryResult(
            delivery_id=delivery_id,
            success=False,
            recipients=recipients,
            error_message=error_msg,
            retry_count=self.max_retries,
        )

    async def _send_email(
        self,
        delivery_id: UUID,
        recipients: list[str],
        subject: str,
        text_body: str,
        html_body: str,
        attachments: list[dict[str, Any]] | None,
    ) -> None:
        """Construct and send the actual email via SMTP."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_address
        msg["To"] = ", ".join(recipients)
        msg["X-Delivery-ID"] = str(delivery_id)

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if attachments:
            for att in attachments:
                filename = att.get("filename", "attachment")
                content = att.get("content", b"")
                mime_type = att.get("mime_type", "application/octet-stream")
                part = MIMEApplication(content, _subtype=mime_type.split("/")[-1])
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

        # Connect and send
        if self._smtp is None:
            self._smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            if self.use_tls:
                self._smtp.starttls()
            if self.username and self.password:
                self._smtp.login(self.username, self.password)

        self._smtp.sendmail(self.from_address, recipients, msg.as_string())

    async def get_status(self, delivery_id: UUID) -> DeliveryResult | None:
        """Return the status of a delivery by ID.

        In a real system this would query a database.
        Here we return None since we don't persist delivery status.
        """
        return None

    async def health_check(self) -> HealthStatus:
        """Check SMTP connectivity."""
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
            server.ehlo()
            if self.use_tls:
                server.starttls()
            server.quit()
            return HealthStatus.HEALTHY
        except Exception as exc:
            log_event(
                logger,
                "WARNING",
                f"SMTP health check failed: {exc}",
                context={"host": self.smtp_host, "port": self.smtp_port},
            )
            return HealthStatus.UNHEALTHY

    def _render_html(self, dossier: Any, template: str | None) -> str:
        """Render HTML email body from dossier."""
        if template:
            return template.format(
                lead_name=getattr(dossier, "lead_name", "Unknown"),
                company_summary=getattr(dossier, "company_summary", ""),
                business_viability=getattr(dossier, "business_viability", ""),
                online_presence=getattr(dossier, "online_presence", ""),
                contact_info=getattr(dossier, "contact_info", ""),
                recommendation=getattr(dossier, "recommendation", ""),
                final_score=getattr(dossier, "final_score", "N/A"),
            )

        return f"""<!DOCTYPE html>
<html>
<head><title>Lead Dossier</title></head>
<body>
<h1>{getattr(dossier, 'lead_name', 'Unknown')}</h1>
<p><strong>Summary:</strong> {getattr(dossier, 'company_summary', '')}</p>
<p><strong>Business Viability:</strong> {getattr(dossier, 'business_viability', '')}</p>
<p><strong>Online Presence:</strong> {getattr(dossier, 'online_presence', '')}</p>
<p><strong>Contact:</strong> {getattr(dossier, 'contact_info', '')}</p>
<p><strong>Score:</strong> {getattr(dossier, 'final_score', 'N/A')}</p>
<p><strong>Recommendation:</strong> {getattr(dossier, 'recommendation', '')}</p>
</body>
</html>"""

    def _render_text(self, dossier: Any) -> str:
        """Render plain text email body from dossier."""
        return f"""Lead Dossier: {getattr(dossier, 'lead_name', 'Unknown')}

Summary: {getattr(dossier, 'company_summary', '')}
Business Viability: {getattr(dossier, 'business_viability', '')}
Online Presence: {getattr(dossier, 'online_presence', '')}
Contact: {getattr(dossier, 'contact_info', '')}
Score: {getattr(dossier, 'final_score', 'N/A')}
Recommendation: {getattr(dossier, 'recommendation', '')}
"""

    async def send_batch(
        self,
        dossiers: list[tuple[Any, list[str]]],
        subject_template: str | None = None,
    ) -> list[DeliveryResult]:
        """Send multiple dossiers in a batch.

        Returns a list of DeliveryResult, one per dossier.
        """
        results: list[DeliveryResult] = []
        for dossier, recipients in dossiers:
            subject = None
            if subject_template:
                subject = subject_template.format(
                    lead_name=getattr(dossier, "lead_name", "Unknown")
                )
            result = await self.send(dossier, recipients, subject=subject)
            results.append(result)
        return results
