"""Moonshot Kimi adapter."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from lead_hunter.config.config import AgentConfig
from lead_hunter.exceptions import AgentResponseError
from lead_hunter.orchestrator.interfaces import AgentRequest, AgentResponse, HealthStatus
from lead_hunter.adapters.base import BaseAgentAdapter


class MoonshotAdapter(BaseAgentAdapter):
    """Adapter for Moonshot Kimi."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        cfg = config or AgentConfig(
            api_endpoint="https://api.moonshot.cn/v1/chat/completions",
            model="moonshot-v1-128k",
            timeout_connect=10.0,
            timeout_read=60.0,
            timeout_total=120.0,
            max_tokens=4096,
            temperature=0.0,
            max_retries=3,
        )
        super().__init__("kimi", cfg)
        self._api_key = os.environ.get("MOONSHOT_API_KEY", "")

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, request: AgentRequest) -> dict[str, Any]:
        return {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": request.prompt},
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "response_format": {"type": "json_object"},
        }

    def _parse_response(self, response_data: dict[str, Any], request: AgentRequest) -> AgentResponse:
        try:
            choice = response_data["choices"][0]
            content = choice["message"]["content"]
            usage = response_data.get("usage", {})
            return AgentResponse(
                response_id=uuid4(),
                request_id=request.request_id,
                run_id=request.run_id,
                correlation_id=request.correlation_id,
                agent_name=self._name,
                content=content,
                timestamp=datetime.now(timezone.utc),
                structured_payload=None,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                latency_ms=0.0,
            )
        except (KeyError, IndexError) as exc:
            raise AgentResponseError(f"Invalid Moonshot response structure: {exc}")

    async def health_check(self) -> HealthStatus:
        if not self._api_key:
            return HealthStatus.UNHEALTHY
        return HealthStatus.UNKNOWN
