"""Telegram delivery implementation for Lead Hunter.

Sends lead dossiers as formatted messages via Telegram Bot API.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import httpx

from lead_hunter.exceptions import DeliveryError
from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.orchestrator.interfaces import Delivery, HealthStatus

logger = get_logger("delivery.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


@dataclass
class DeliveryResult:
    """Result of a Telegram delivery attempt."""
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


class TelegramDelivery(Delivery):
    """Telegram Bot API delivery for lead dossiers."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        metrics: DeliveryMetrics | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.metrics = metrics or DeliveryMetrics()
        self._client: httpx.AsyncClient | None = None

    def _client_sync(self) -> httpx.Client:
        """Return a synchronous httpx client for use in async context."""
        return httpx.Client(timeout=30.0)

    async def send(
        self,
        dossier: Any,
        recipients: list[str],
        subject: str | None = None,
        template: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> DeliveryResult:
        """Send a dossier via Telegram to the configured chat."""
        delivery_id = uuid4()
        subject = subject or f"Lead Dossier: {getattr(dossier, 'lead_name', 'Unknown')}"

        message_text = self._render_message(dossier, subject)

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self.metrics.total_attempts += 1
                await self._send_telegram_message(
                    delivery_id=delivery_id,
                    text=message_text,
                )
                self.metrics.successful_deliveries += 1
                log_event(
                    logger,
                    "INFO",
                    f"Telegram message delivered to chat {self.chat_id}",
                    context={
                        "delivery_id": str(delivery_id),
                        "chat_id": self.chat_id,
                        "attempt": attempt + 1,
                    },
                )
                return DeliveryResult(
                    delivery_id=delivery_id,
                    success=True,
                    recipients=[self.chat_id],
                    retry_count=attempt,
                )
            except Exception as exc:
                last_error = exc
                self.metrics.retries += 1
                log_event(
                    logger,
                    "WARNING",
                    f"Telegram delivery attempt {attempt + 1} failed: {exc}",
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
                        f"Retrying Telegram delivery in {total_delay:.1f}s",
                        context={"backoff_seconds": round(total_delay, 2)},
                    )
                else:
                    break

        self.metrics.failed_deliveries += 1
        error_msg = str(last_error) if last_error else "Unknown error"
        log_event(
            logger,
            "ERROR",
            f"Telegram delivery failed after {self.max_retries + 1} attempts",
            context={
                "delivery_id": str(delivery_id),
                "error": error_msg,
            },
        )
        return DeliveryResult(
            delivery_id=delivery_id,
            success=False,
            recipients=[self.chat_id],
            error_message=error_msg,
            retry_count=self.max_retries,
        )

    async def _send_telegram_message(self, delivery_id: UUID, text: str) -> None:
        """Send a message via Telegram Bot API."""
        url = f"{TELEGRAM_API_BASE}{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        # Use sync client inside async method (same pattern as email_delivery)
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise DeliveryError(f"Telegram API error: {data.get('description', 'Unknown error')}")

    async def get_status(self, delivery_id: UUID) -> DeliveryResult | None:
        """Return the status of a delivery by ID."""
        return None

    async def health_check(self) -> HealthStatus:
        """Check Telegram Bot API connectivity."""
        try:
            url = f"{TELEGRAM_API_BASE}{self.bot_token}/getMe"
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
                if data.get("ok"):
                    bot_info = data.get("result", {})
                    log_event(
                        logger,
                        "INFO",
                        f"Telegram bot connected: @{bot_info.get('username', 'unknown')}",
                    )
                    return HealthStatus.HEALTHY
                return HealthStatus.UNHEALTHY
        except Exception as exc:
            log_event(
                logger,
                "WARNING",
                f"Telegram health check failed: {exc}",
            )
            return HealthStatus.UNHEALTHY

    def _render_message(self, dossier: Any, subject: str) -> str:
        """Render a Telegram HTML message from dossier."""
        lead_name = getattr(dossier, "lead_name", "Unknown")
        company_summary = getattr(dossier, "company_summary", "N/A")
        business_viability = getattr(dossier, "business_viability", "N/A")
        online_presence = getattr(dossier, "online_presence", "N/A")
        contact_info = getattr(dossier, "contact_info", "N/A")
        recommendation = getattr(dossier, "recommendation", "N/A")
        final_score = getattr(dossier, "final_score", "N/A")

        return f"""<b>🔍 {subject}</b>

<b>📋 Company Summary</b>
{company_summary}

<b>💼 Business Viability</b>
{business_viability}

<b>🌐 Online Presence</b>
{online_presence}

<b>📞 Contact Info</b>
{contact_info}

<b>⭐ Final Score:</b> {final_score}/100

<b>✅ Recommendation</b>
{recommendation}

<i>Delivered by Lead Hunter via Telegram</i>"""

    async def send_batch(
        self,
        dossiers: list[tuple[Any, list[str]]],
        subject_template: str | None = None,
    ) -> list[DeliveryResult]:
        """Send multiple dossiers in a batch."""
        results: list[DeliveryResult] = []
        for dossier, _recipients in dossiers:
            subject = None
            if subject_template:
                subject = subject_template.format(
                    lead_name=getattr(dossier, "lead_name", "Unknown")
                )
            result = await self.send(dossier, [self.chat_id], subject=subject)
            results.append(result)
        return results
