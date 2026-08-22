"""Abstract interfaces for Lead Hunter components.

All provider implementations and adapters must conform to these interfaces.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Protocol
from uuid import UUID


class HealthStatus(Enum):
    """Health status of a component."""
    HEALTHY = auto()
    DEGRADED = auto()
    UNHEALTHY = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class AgentRequest:
    """Structured request sent to an agent adapter."""
    request_id: UUID
    run_id: UUID
    correlation_id: UUID
    stage_id: UUID
    agent_name: str
    prompt: str
    context: dict[str, Any]
    max_tokens: int = 2048
    temperature: float = 0.0
    timeout_seconds: float = 60.0
    attempt_number: int = 1


@dataclass(frozen=True)
class AgentResponse:
    """Structured response from an agent adapter."""
    response_id: UUID
    request_id: UUID
    run_id: UUID
    correlation_id: UUID
    agent_name: str
    content: str
    timestamp: datetime
    structured_payload: dict[str, Any] | None = None
    usage: dict[str, int] | None = None
    latency_ms: float = 0.0


class AgentAdapter(ABC):
    """Abstract adapter for AI provider integrations.

    All provider implementations (OpenAI, Google, Moonshot, Anthropic)
    must inherit from this class.
    """

    @abstractmethod
    async def send_request(self, request: AgentRequest) -> AgentResponse:
        """Send a request to the agent and return the response."""
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Return the current health status of the adapter."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return the human-readable name of this agent."""
        ...

    @abstractmethod
    def get_capabilities(self) -> list[str]:
        """Return a list of capabilities this agent supports."""
        ...


class Persistence(ABC):
    """Abstract persistence interface.

    All persistence implementations (in-memory, SQLite, PostgreSQL)
    must inherit from this class.
    """

    @abstractmethod
    async def create_run(self, run: Any) -> Any:
        ...

    @abstractmethod
    async def get_run(self, run_id: UUID) -> Any | None:
        ...

    @abstractmethod
    async def update_run(self, run: Any) -> Any:
        ...

    @abstractmethod
    async def list_runs(self, status: Any | None = None, limit: int = 1000) -> list[Any]:
        ...

    @abstractmethod
    async def create_stage(self, stage: Any) -> Any:
        ...

    @abstractmethod
    async def get_stage(self, stage_id: UUID) -> Any | None:
        ...

    @abstractmethod
    async def update_stage(self, stage: Any) -> Any:
        ...

    @abstractmethod
    async def get_stages_for_run(self, run_id: UUID) -> list[Any]:
        ...

    @abstractmethod
    async def create_approval(self, approval: Any) -> Any:
        ...

    @abstractmethod
    async def get_approval(self, approval_id: UUID) -> Any | None:
        ...

    @abstractmethod
    async def update_approval(self, approval: Any) -> Any:
        ...

    @abstractmethod
    async def get_approvals_for_run(self, run_id: UUID) -> list[Any]:
        ...

    @abstractmethod
    async def create_event(self, event: Any) -> Any:
        ...

    @abstractmethod
    async def get_events_for_run(self, run_id: UUID) -> list[Any]:
        ...

    @abstractmethod
    async def create_artifact(self, artifact: Any) -> Any:
        ...

    @abstractmethod
    async def get_artifact(self, artifact_id: UUID) -> Any | None:
        ...

    @abstractmethod
    async def get_artifacts_for_run(self, run_id: UUID) -> list[Any]:
        ...

    @abstractmethod
    async def create_error(self, error: Any) -> Any:
        ...

    @abstractmethod
    async def get_errors_for_run(self, run_id: UUID) -> list[Any]:
        ...

    @abstractmethod
    async def get_runs_to_recover(self) -> list[Any]:
        """Return runs that need recovery after restart."""
        ...

    @abstractmethod
    async def get_configuration(self, config_id: str) -> Any | None:
        ...

    @abstractmethod
    async def save_configuration(self, config: Any) -> Any:
        ...

    @abstractmethod
    async def save_campaign(self, campaign: Any) -> Any:
        ...

    @abstractmethod
    async def get_campaign(self, campaign_id: UUID) -> Any | None:
        ...

    @abstractmethod
    async def list_campaigns(self) -> list[Any]:
        ...

    @abstractmethod
    async def delete_campaign(self, campaign_id: UUID) -> bool:
        ...


class Scheduler(ABC):
    """Abstract scheduler interface."""

    @abstractmethod
    async def start(self) -> None:
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        ...

    @abstractmethod
    async def add_job(self, trigger_request: Any) -> Any:
        ...

    @abstractmethod
    async def remove_job(self, job_id: str) -> None:
        ...

    @abstractmethod
    async def list_jobs(self) -> list[Any]:
        ...


class Delivery(ABC):
    """Abstract delivery interface for email and notifications."""

    @abstractmethod
    async def send(self, dossier: Any, recipients: list[str]) -> Any:
        ...

    @abstractmethod
    async def get_status(self, delivery_id: UUID) -> Any | None:
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        ...


class VoiceTriggerAdapter(ABC):
    """Future voice-trigger adapter interface.

    Designed so that voice triggers can be added later without
    restructuring the core orchestrator.
    """

    @abstractmethod
    async def listen(self) -> Any:
        """Listen for and capture a voice command."""
        ...

    @abstractmethod
    async def parse(self, command: Any) -> Any:
        """Parse a voice command into a trigger request."""
        ...

    @abstractmethod
    async def validate(self, request: Any) -> bool:
        """Validate a parsed trigger request."""
        ...
