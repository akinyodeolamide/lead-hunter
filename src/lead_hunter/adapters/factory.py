"""Factory for creating agent adapters."""
from __future__ import annotations

from lead_hunter.config.config import AgentConfig
from lead_hunter.exceptions import ConfigurationError
from lead_hunter.orchestrator.interfaces import AgentAdapter
from lead_hunter.adapters.openai_adapter import OpenAIAdapter
from lead_hunter.adapters.google_adapter import GoogleAdapter
from lead_hunter.adapters.moonshot_adapter import MoonshotAdapter
from lead_hunter.adapters.anthropic_adapter import AnthropicAdapter


class AgentAdapterFactory:
    """Factory for creating agent adapters by name."""

    _adapters: dict[str, type[AgentAdapter]] = {
        "chatgpt": OpenAIAdapter,
        "gemini": GoogleAdapter,
        "kimi": MoonshotAdapter,
        "claude": AnthropicAdapter,
    }

    @classmethod
    def create(cls, name: str, config: AgentConfig | None = None) -> AgentAdapter:
        """Create an agent adapter by name."""
        adapter_class = cls._adapters.get(name.lower())
        if not adapter_class:
            raise ConfigurationError(f"Unknown agent adapter: {name}")
        return adapter_class(config)

    @classmethod
    def list_adapters(cls) -> list[str]:
        """List all available adapter names."""
        return list(cls._adapters.keys())

    @classmethod
    def register(cls, name: str, adapter_class: type[AgentAdapter]) -> None:
        """Register a new adapter type."""
        cls._adapters[name.lower()] = adapter_class
