"""Telegram bot for Lead Hunter — Webhook-based.

Telegram POSTs updates to our FastAPI endpoint instead of us polling.
This avoids 409 Conflict errors on Railway where old containers stay alive.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import httpx

from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.models.domain import RunStatus
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.approval.approval_service import ApprovalService
from lead_hunter.orchestrator.interfaces import Persistence
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow

logger = get_logger("telegram_bot")

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

STAGE_EMOJIS = {
    "INIT": "🚀",
    "RESEARCH": "🔍",
    "SCREENING": "🧪",
    "DEEP_RESEARCH": "🔬",
    "AUDIT": "📋",
    "SCORING": "📊",
    "APPROVAL": "⏳",
    "DELIVERY": "📬",
    "FINALIZATION": "✅",
}

STATUS_EMOJIS = {
    RunStatus.PENDING: "⏳",
    RunStatus.RUNNING: "🔄",
    RunStatus.PAUSED: "⏸️",
    RunStatus.COMPLETED: "✅",
    RunStatus.FAILED: "❌",
    RunStatus.CANCELLED: "🚫",
    RunStatus.REJECTED: "🚫",
}


class LeadHunterTelegramBot:
    """Telegram bot using webhooks (no polling)."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        webhook_url: str,
        engine: OrchestrationEngine,
        persistence: Persistence,
        approval_service: ApprovalService,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.webhook_url = webhook_url
        self.engine = engine
        self.persistence = persistence
        self.approval_service = approval_service
        self._status_tasks: dict[str, asyncio.Task[Any]] = {}
        self._message_ids: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Delete old webhook, set new one, drop pending updates."""
        await self._delete_webhook()
        await self._set_webhook()
        log_event(logger, "INFO", f"Telegram webhook set to {self.webhook_url}")

    async def stop(self) -> None:
        """Remove webhook on shutdown."""
        await self._delete_webhook()
        for t in self._status_tasks.values():
            t.cancel()
        log_event(logger, "INFO", "Telegram webhook removed")

    async def _delete_webhook(self) -> None:
        """Clear any existing webhook and drop pending updates."""
        url = f"{TELEGRAM_API_BASE}{self.bot_token}/deleteWebhook"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(url, json={"drop_pending_updates": True})
        except Exception as exc:
            log_event(logger, "WARNING", f"deleteWebhook failed: {exc}")

    async def _set_webhook(self) -> None:
        """Register our webhook URL with Telegram."""
        url = f"{TELEGRAM_API_BASE}{self.bot_token}/setWebhook"
        payload = {
            "url": self.webhook_url,
            "allowed_updates": ["message", "callback_query"],
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload)
                data = response.json()
                if data.get("ok"):
                    log_event(logger, "INFO", "Webhook registered successfully")
                else:
                    log_event(logger, "ERROR", f"Webhook registration failed: {data}")
        except Exception as exc:
            log_event(logger, "ERROR", f"setWebhook failed: {exc}")

    # ------------------------------------------------------------------
    # Webhook handler (called by FastAPI endpoint)
    # ------------------------------------------------------------------

    async def handle_update(self, update: dict[str, Any]) -> None:
        """Process an update received via webhook."""
        if "message" in update:
            await self._handle_message(update["message"])
        elif "callback_query" in update:
            await self._handle_callback(update["callback_query"])

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming text messages."""
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        if not text:
            return
        if str(chat_id) != self.chat_id:
            return

        if text.startswith("/"):
            await self._handle_command(text, chat_id)
        else:
            await self._start_hunt_from_text(text, chat_id)

    async def _handle_command(self, text: str, chat_id: int) -> None:
        """Parse and execute bot commands."""
        parts = text.split()
        cmd = parts[0].lower()
        args = parts[1:]

        handlers = {
            "/start": self._cmd_start,
            "/hunt": self._cmd_hunt,
            "/status": self._cmd_status,
            "/history": self._cmd_history,
            "/help": self._cmd_help,
        }

        handler = handlers.get(cmd, self._cmd_unknown)
        await handler(args, chat_id)

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        """Handle inline button callbacks (approve/reject)."""
        data = callback.get("data", "")
        message_id = callback.get("message", {}).get("message_id")
        chat_id = callback.get("message", {}).get("chat", {}).get("id")

        await self._answer_callback(callback.get("id"), "Processing...")

        if data.startswith("approve:"):
            approval_id = data.split(":", 1)[1]
            try:
                await self.approval_service.approve(
                    UUID(approval_id), decided_by="telegram_user", rationale="Approved via Telegram"
                )
                await self._edit_message(
                    chat_id, message_id,
                    f"✅ <b>Approved!</b>\nApproval ID: <code>{approval_id[:8]}</code>"
                )
            except Exception as exc:
                await self._edit_message(
                    chat_id, message_id,
                    f"❌ <b>Approval failed:</b> {exc}"
                )

        elif data.startswith("reject:"):
            approval_id = data.split(":", 1)[1]
            try:
                await self.approval_service.reject(
                    UUID(approval_id), decided_by="telegram_user", rationale="Rejected via Telegram"
                )
                await self._edit_message(
                    chat_id, message_id,
                    f"🚫 <b>Rejected!</b>\nApproval ID: <code>{approval_id[:8]}</code>"
                )
            except Exception as exc:
                await self._edit_message(
                    chat_id, message_id,
                    f"❌ <b>Rejection failed:</b> {exc}"
                )

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def _cmd_start(self, _args: list[str], chat_id: int) -> None:
        await self._send_message(
            chat_id,
            "<b>🔍 Welcome to Lead Hunter!</b>\n\n"
            "I find and research business leads for you.\n\n"
            "<b>Commands:</b>\n"
            "• <code>/hunt &lt;industry&gt; in &lt;location&gt;</code> — Start a new hunt\n"
            "• <code>/status</code> — Check active hunts\n"
            "• <code>/history</code> — View past hunts\n"
            "• <code>/help</code> — Show help\n\n"
            "Or just type what you want to find, like:\n"
            "<i>\"Find me fashion designers in Abeokuta without websites\"</i>"
        )

    async def _cmd_hunt(self, args: list[str], chat_id: int) -> None:
        text = " ".join(args)
        if not text:
            await self._send_message(
                chat_id,
                "❌ Please specify what to hunt.\n"
                "Example: <code>/hunt fashion designers in Abeokuta</code>"
            )
            return
        await self._start_hunt_from_text(text, chat_id)

    async def _cmd_status(self, _args: list[str], chat_id: int) -> None:
        runs = await self.persistence.list_runs(status=RunStatus.RUNNING, limit=10)
        if not runs:
            await self._send_message(chat_id, "✅ No active hunts right now.")
            return

        lines = ["<b>🔄 Active Hunts</b>"]
        for run in runs:
            emoji = STATUS_EMOJIS.get(run.status, "❓")
            current_stage = run.metadata.get("current_stage", "Unknown")
            stage_emoji = STAGE_EMOJIS.get(current_stage, "🔹")
            lines.append(
                f"{emoji} <code>{str(run.run_id)[:8]}</code> — {stage_emoji} {current_stage}"
            )
        await self._send_message(chat_id, "\n".join(lines))

    async def _cmd_history(self, _args: list[str], chat_id: int) -> None:
        runs = await self.persistence.list_runs(limit=10)
        if not runs:
            await self._send_message(chat_id, "📭 No hunts yet. Start one with <code>/hunt</code>!")
            return

        lines = ["<b>📜 Recent Hunts</b>"]
        for run in runs:
            emoji = STATUS_EMOJIS.get(run.status, "❓")
            lead_name = run.metadata.get("lead_name", "Unknown")
            lines.append(
                f"{emoji} <code>{str(run.run_id)[:8]}</code> — {lead_name}"
            )
        await self._send_message(chat_id, "\n".join(lines))

    async def _cmd_help(self, _args: list[str], chat_id: int) -> None:
        await self._send_message(
            chat_id,
            "<b>📖 Lead Hunter Help</b>\n\n"
            "<b>Starting a Hunt:</b>\n"
            "• <code>/hunt &lt;industry&gt; in &lt;location&gt;</code>\n"
            "• Or just type naturally: <i>\"Find plumbers in Lagos\"</i>\n\n"
            "<b>Monitoring:</b>\n"
            "• Hunts update their message automatically as stages progress\n"
            "• <code>/status</code> — See all active hunts\n"
            "• <code>/history</code> — See completed hunts\n\n"
            "<b>Approvals:</b>\n"
            "• When a lead needs approval, I'll send you buttons\n"
            "• Tap ✅ Approve or 🚫 Reject\n\n"
            "<b>Results:</b>\n"
            "• Completed dossiers are sent as formatted messages\n"
            "• Each includes summary, viability, score, and recommendation"
        )

    async def _cmd_unknown(self, args: list[str], chat_id: int) -> None:
        await self._send_message(
            chat_id,
            "❓ Unknown command. Use <code>/help</code> to see available commands."
        )

    # ------------------------------------------------------------------
    # Hunt execution
    # ------------------------------------------------------------------

    async def _start_hunt_from_text(self, text: str, chat_id: int) -> None:
        industry = text
        location = ""
        if " in " in text.lower():
            parts = text.lower().split(" in ", 1)
            industry = parts[0].strip()
            location = parts[1].strip()

        status_text = (
            f"<b>🔍 Starting Hunt</b>\n\n"
            f"<b>Industry:</b> {industry.title()}\n"
            f"<b>Location:</b> {location.title() or 'Any'}\n\n"
            f"🚀 Initializing..."
        )
        message = await self._send_message(chat_id, status_text)
        message_id = message.get("result", {}).get("message_id") if message else None

        try:
            run = await self.engine.start_run(
                configuration_id="default",
                metadata={
                    "lead_name": f"{industry.title()} in {location.title() or 'Any'}",
                    "industry": industry,
                    "summary": f"Find {industry} businesses",
                },
            )
            run_id = str(run.run_id)

            if message_id:
                self._message_ids[run_id] = message_id

            workflow = LeadHunterWorkflow(
                self.engine,
                approval_service=self.approval_service,
                config={"screening_min_evidence": 1},
            )

            asyncio.create_task(self._execute_workflow(
                workflow, run, industry, location, chat_id, message_id
            ))

            if message_id:
                status_task = asyncio.create_task(
                    self._poll_run_status(run_id, chat_id, message_id)
                )
                self._status_tasks[run_id] = status_task

        except Exception as exc:
            log_event(logger, "ERROR", f"Failed to start hunt: {exc}")
            if message_id:
                await self._edit_message(
                    chat_id, message_id,
                    f"❌ <b>Hunt failed to start</b>\n{exc}"
                )

    async def _execute_workflow(
        self,
        workflow: LeadHunterWorkflow,
        run: Any,
        industry: str,
        location: str,
        chat_id: int,
        message_id: int | None,
    ) -> None:
        try:
            await workflow.execute_run(
                run=run,
                lead_name=f"{industry.title()} in {location.title() or 'Any'}",
                industry=industry,
                summary=f"Find {industry} businesses",
                initial_claims=None,
            )
        except Exception as exc:
            log_event(logger, "ERROR", f"Workflow execution failed: {exc}")

    async def _poll_run_status(
        self,
        run_id: str,
        chat_id: int,
        message_id: int,
    ) -> None:
        last_status = ""
        last_stage = ""
        run_uuid = UUID(run_id)

        while True:
            try:
                run = await self.persistence.get_run(run_uuid)
                if not run:
                    break

                current_stage = run.metadata.get("current_stage", "Unknown")
                status = run.status.name

                if status != last_status or current_stage != last_stage:
                    last_status = status
                    last_stage = current_stage

                    status_emoji = STATUS_EMOJIS.get(run.status, "❓")
                    stage_emoji = STAGE_EMOJIS.get(current_stage, "🔹")

                    if run.status == RunStatus.COMPLETED:
                        text = (
                            f"<b>{status_emoji} Hunt Complete!</b>\n\n"
                            f"<b>Run:</b> <code>{run_id[:8]}</code>\n"
                            f"<b>Result:</b> {current_stage}\n\n"
                            f"Check your messages for the dossier."
                        )
                        await self._edit_message(chat_id, message_id, text)
                        break

                    elif run.status in (RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.REJECTED):
                        text = (
                            f"<b>{status_emoji} Hunt Ended</b>\n\n"
                            f"<b>Run:</b> <code>{run_id[:8]}</code>\n"
                            f"<b>Status:</b> {status}\n\n"
                            f"The hunt did not complete successfully."
                        )
                        await self._edit_message(chat_id, message_id, text)
                        break

                    elif run.status == RunStatus.PAUSED:
                        text = (
                            f"<b>{status_emoji} Hunt Paused</b>\n\n"
                            f"<b>Run:</b> <code>{run_id[:8]}</code>\n"
                            f"<b>Stage:</b> {stage_emoji} {current_stage}\n\n"
                            f"Waiting for approval..."
                        )
                        await self._edit_message(chat_id, message_id, text)

                    else:
                        text = (
                            f"<b>{status_emoji} Hunt in Progress</b>\n\n"
                            f"<b>Run:</b> <code>{run_id[:8]}</code>\n"
                            f"<b>Stage:</b> {stage_emoji} {current_stage}\n"
                            f"<b>Status:</b> {status}"
                        )
                        await self._edit_message(chat_id, message_id, text)

                await self._check_and_notify_approvals(run_uuid, chat_id)

                if run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
                    break

                await asyncio.sleep(3)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log_event(logger, "WARNING", f"Status poll error: {exc}")
                await asyncio.sleep(5)

        self._status_tasks.pop(run_id, None)

    async def _check_and_notify_approvals(self, run_id: UUID, chat_id: int) -> None:
        try:
            approvals = await self.approval_service.get_waiting_approvals()
            for approval in approvals:
                if str(approval.run_id) != str(run_id):
                    continue
                details = approval.request_details or {}
                lead_name = details.get("lead_name", "Unknown Lead")
                score = details.get("score", "N/A")

                text = (
                    f"<b>⏳ Approval Required</b>\n\n"
                    f"<b>Lead:</b> {lead_name}\n"
                    f"<b>Score:</b> {score}/100\n"
                    f"<b>Run:</b> <code>{str(run_id)[:8]}</code>\n\n"
                    f"Please review and decide:"
                )

                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Approve", "callback_data": f"approve:{approval.approval_id}"},
                            {"text": "🚫 Reject", "callback_data": f"reject:{approval.approval_id}"},
                        ]
                    ]
                }

                await self._send_message(chat_id, text, reply_markup=keyboard)
        except Exception as exc:
            log_event(logger, "WARNING", f"Approval check error: {exc}")

    # ------------------------------------------------------------------
    # Telegram API helpers
    # ------------------------------------------------------------------

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        url = f"{TELEGRAM_API_BASE}{self.bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            log_event(logger, "ERROR", f"sendMessage failed: {exc}")
            return None

    async def _edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
    ) -> dict[str, Any] | None:
        url = f"{TELEGRAM_API_BASE}{self.bot_token}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            log_event(logger, "WARNING", f"editMessageText failed: {exc}")
            return None

    async def _answer_callback(self, callback_query_id: str, text: str) -> None:
        url = f"{TELEGRAM_API_BASE}{self.bot_token}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id,
            "text": text,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=payload)
        except Exception:
            pass
