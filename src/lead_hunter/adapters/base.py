"""Base agent adapter with retry, timeout, and error handling."""
from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import Any

import httpx

from lead_hunter.config.config import AgentConfig
from lead_hunter.exceptions import AgentError, AgentResponseError, AgentTimeoutError, RetryExhaustedError
from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.orchestrator.interfaces import AgentAdapter, AgentRequest, AgentResponse, HealthStatus

logger = get_logger("adapters")


class BaseAgentAdapter(AgentAdapter):
    """Base class for all agent adapters with shared retry/timeout logic."""

    def __init__(self, name: str, config: AgentConfig) -> None:
        self._name = name
        self.config = config
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                config.timeout_total,
                connect=config.timeout_connect,
                read=config.timeout_read,
                write=10.0,
            ),
            follow_redirects=True,
        )

    def get_name(self) -> str:
        return self._name

    def get_capabilities(self) -> list[str]:
        return ["text_generation", "structured_output"]

    async def health_check(self) -> HealthStatus:
        """Default health check - subclasses should override."""
        return HealthStatus.UNKNOWN

    async def _do_request(self, request: AgentRequest, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute HTTP request with retry logic."""
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = await self._client.post(
                    self.config.api_endpoint,
                    json=payload,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                last_error = AgentTimeoutError(f"Timeout on attempt {attempt}: {exc}")
                log_event(
                    logger,
                    "WARNING",
                    f"{self._name} request timed out (attempt {attempt})",
                    run_id=request.run_id,
                    context={"attempt": attempt, "max_retries": self.config.max_retries},
                )
                if attempt < self.config.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 60))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_error = AgentError(f"Rate limited on attempt {attempt}: {exc}")
                    if attempt < self.config.max_retries:
                        await asyncio.sleep(min(2 ** attempt + 1, 60))
                    continue
                if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                    raise AgentResponseError(f"Client error {exc.response.status_code}: {exc}")
                last_error = AgentError(f"Server error {exc.response.status_code}: {exc}")
                if attempt < self.config.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 60))
            except Exception as exc:
                last_error = AgentError(f"Request failed on attempt {attempt}: {exc}")
                if attempt < self.config.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 60))

        raise RetryExhaustedError(
            f"Max retries ({self.config.max_retries}) exceeded for {self._name}",
            details={"last_error": str(last_error)},
        )

    @abstractmethod
    def _get_headers(self) -> dict[str, str]:
        """Return HTTP headers for this provider."""
        ...

    @abstractmethod
    def _build_payload(self, request: AgentRequest) -> dict[str, Any]:
        """Build the provider-specific request payload."""
        ...

    @abstractmethod
    def _parse_response(self, response_data: dict[str, Any], request: AgentRequest) -> AgentResponse:
        """Parse provider-specific response into AgentResponse."""
        ...

    async def send_request(self, request: AgentRequest) -> AgentResponse:
        """Send a request to the agent and return the response."""
        payload = self._build_payload(request)
        response_data = await self._do_request(request, payload)
        return self._parse_response(response_data, request)
