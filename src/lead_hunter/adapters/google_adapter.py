"""Google Gemini adapter."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from lead_hunter.config.config import AgentConfig
from lead_hunter.exceptions import AgentResponseError
from lead_hunter.orchestrator.interfaces import AgentRequest, AgentResponse, HealthStatus
from lead_hunter.adapters.base import BaseAgentAdapter


class GoogleAdapter(BaseAgentAdapter):
    """Adapter for Google Gemini."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        cfg = config or AgentConfig(
            api_endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent",
            model="gemini-1.5-pro",
            timeout_connect=10.0,
            timeout_read=60.0,
            timeout_total=120.0,
            max_tokens=4096,
            temperature=0.0,
            max_retries=3,
        )
        super().__init__("gemini", cfg)
        self._api_key = os.environ.get("GOOGLE_API_KEY", "")

    def _get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

    def _build_payload(self, request: AgentRequest) -> dict[str, Any]:
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": request.prompt}],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature,
                "responseMimeType": "application/json",
            },
        }

    def _parse_response(self, response_data: dict[str, Any], request: AgentRequest) -> AgentResponse:
        try:
            candidates = response_data.get("candidates", [])
            if not candidates:
                raise AgentResponseError("No candidates in Gemini response")
            content = candidates[0]["content"]["parts"][0]["text"]
            usage = response_data.get("usageMetadata", {})
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
                    "prompt_tokens": usage.get("promptTokenCount", 0),
                    "completion_tokens": usage.get("candidatesTokenCount", 0),
                    "total_tokens": usage.get("totalTokenCount", 0),
                },
                latency_ms=0.0,
            )
        except (KeyError, IndexError) as exc:
            raise AgentResponseError(f"Invalid Gemini response structure: {exc}")

    async def health_check(self) -> HealthStatus:
        if not self._api_key:
            return HealthStatus.UNHEALTHY
        return HealthStatus.UNKNOWN  # Google does not have a simple health endpoint
