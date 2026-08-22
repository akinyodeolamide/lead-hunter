"""Anthropic Claude adapter."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from lead_hunter.config.config import AgentConfig
from lead_hunter.exceptions import AgentResponseError
from lead_hunter.orchestrator.interfaces import AgentRequest, AgentResponse, HealthStatus
from lead_hunter.adapters.base import BaseAgentAdapter


class AnthropicAdapter(BaseAgentAdapter):
    """Adapter for Anthropic Claude."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        cfg = config or AgentConfig(
            api_endpoint="https://api.anthropic.com/v1/messages",
            model="claude-3-5-sonnet-20241022",
            timeout_connect=10.0,
            timeout_read=60.0,
            timeout_total=120.0,
            max_tokens=4096,
            temperature=0.0,
            max_retries=3,
        )
        super().__init__("claude", cfg)
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def _get_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _build_payload(self, request: AgentRequest) -> dict[str, Any]:
        return {
            "model": self.config.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [
                {"role": "user", "content": request.prompt},
            ],
        }

    def _parse_response(self, response_data: dict[str, Any], request: AgentRequest) -> AgentResponse:
        try:
            content_blocks = response_data.get("content", [])
            if not content_blocks:
                raise AgentResponseError("No content blocks in Claude response")
            content = content_blocks[0].get("text", "")
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
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                },
                latency_ms=0.0,
            )
        except (KeyError, IndexError) as exc:
            raise AgentResponseError(f"Invalid Claude response structure: {exc}")

    async def health_check(self) -> HealthStatus:
        if not self._api_key:
            return HealthStatus.UNHEALTHY
        return HealthStatus.UNKNOWN
