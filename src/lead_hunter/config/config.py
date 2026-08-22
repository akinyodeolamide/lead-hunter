"""Layered configuration system for Lead Hunter.

Configuration is loaded in order (later overrides earlier):
1. Default configuration (code)
2. Configuration file (YAML or JSON)
3. Environment variables
4. Run-specific overrides
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lead_hunter.exceptions import ConfigurationError


DEFAULT_CONFIG: dict[str, Any] = {
    "orchestrator": {
        "max_concurrent_runs": 10,
        "approval_timeout_seconds": 86400,
        "default_retry_count": 3,
        "retry_backoff_base_seconds": 2,
        "retry_backoff_max_seconds": 60,
        "scoring_weights": {
            "evidence_quality": 25,
            "business_viability": 25,
            "online_presence": 20,
            "contact_accessibility": 15,
            "audit_confidence": 15,
        },
        "auto_approve_threshold": 85,
        "require_approval_threshold": 60,
        "auto_reject_threshold": 60,
    },
    "agents": {
        "chatgpt": {
            "api_endpoint": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "timeout_connect": 10,
            "timeout_read": 60,
            "timeout_total": 120,
            "max_tokens": 4096,
            "temperature": 0.0,
            "max_retries": 3,
        },
        "gemini": {
            "api_endpoint": "https://generativelanguage.googleapis.com/v1beta",
            "model": "gemini-1.5-pro",
            "timeout_connect": 10,
            "timeout_read": 60,
            "timeout_total": 120,
            "max_tokens": 4096,
            "temperature": 0.0,
            "max_retries": 3,
        },
        "kimi": {
            "api_endpoint": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-128k",
            "timeout_connect": 10,
            "timeout_read": 60,
            "timeout_total": 120,
            "max_tokens": 4096,
            "temperature": 0.0,
            "max_retries": 3,
        },
        "claude": {
            "api_endpoint": "https://api.anthropic.com/v1",
            "model": "claude-3-5-sonnet-20241022",
            "timeout_connect": 10,
            "timeout_read": 60,
            "timeout_total": 120,
            "max_tokens": 4096,
            "temperature": 0.0,
            "max_retries": 3,
        },
    },
    "persistence": {
        "database_url": "sqlite:///lead_hunter.db",
        "echo_sql": False,
        "migration_directory": "migrations",
        "pool_size": 5,
        "max_overflow": 10,
    },
    "delivery": {
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_use_tls": True,
        "smtp_username": "",
        "smtp_password": "",
        "sender_address": "",
        "default_recipients": [],
        "subject_template": "Lead Hunter Dossier: {{ lead_name }}",
        "html_template": "default",
        "text_template": "default",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
    },
    "scheduler": {
        "timezone": "UTC",
        "job_store": "memory",
        "max_instances": 1,
        "misfire_grace_time": 3600,
    },
    "logging": {
        "level": "INFO",
        "format": "json",
        "outputs": ["stdout"],
        "mask_secrets": True,
    },
    "security": {
        "max_payload_size_bytes": 10_485_760,
        "allowed_domains": [],
        "prompt_injection_patterns": [
            "ignore previous instructions",
            "ignore all previous instructions",
            "system prompt",
            "you are now",
            "you are a",
            "you have been",
            "new instructions",
            "override instructions",
            "disregard",
            "forget everything",
        ],
        "max_control_chars_ratio": 0.05,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_config_file(path: Path) -> dict[str, Any]:
    """Load configuration from a YAML or JSON file."""
    if not path.exists():
        return {}
    content = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(content) or {}
    elif path.suffix == ".json":
        import json
        return json.loads(content)
    else:
        raise ConfigurationError(f"Unsupported config file format: {path.suffix}")


def _load_env_overrides(prefix: str = "LH_") -> dict[str, Any]:
    """Load configuration overrides from environment variables.

    Variables like LH_ORCHESTRATOR__MAX_CONCURRENT_RUNS=20
    are mapped to nested dict keys.
    """
    overrides: dict[str, Any] = {}
    pattern = re.compile(rf"^{prefix}(.+)$")
    for key, value in os.environ.items():
        match = pattern.match(key)
        if not match:
            continue
        path = match.group(1).lower().split("__")
        # Convert value to appropriate type
        converted: Any = value
        if value.lower() in ("true", "false"):
            converted = value.lower() == "true"
        else:
            try:
                converted = int(value)
            except ValueError:
                try:
                    converted = float(value)
                except ValueError:
                    pass
        # Build nested dict
        current = overrides
        for part in path[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[path[-1]] = converted
    return overrides


@dataclass
class OrchestratorConfig:
    """Orchestrator-specific configuration."""
    max_concurrent_runs: int = 10
    approval_timeout_seconds: int = 86400
    default_retry_count: int = 3
    retry_backoff_base_seconds: float = 2.0
    retry_backoff_max_seconds: float = 60.0
    scoring_weights: dict[str, int] = field(default_factory=lambda: {
        "evidence_quality": 25,
        "business_viability": 25,
        "online_presence": 20,
        "contact_accessibility": 15,
        "audit_confidence": 15,
    })
    auto_approve_threshold: int = 85
    require_approval_threshold: int = 60
    auto_reject_threshold: int = 60


@dataclass
class AgentConfig:
    """Per-agent configuration."""
    api_endpoint: str = ""
    model: str = ""
    timeout_connect: float = 10.0
    timeout_read: float = 60.0
    timeout_total: float = 120.0
    max_tokens: int = 4096
    temperature: float = 0.0
    max_retries: int = 3


@dataclass
class PersistenceConfig:
    """Persistence-specific configuration."""
    database_url: str = "sqlite:///lead_hunter.db"
    echo_sql: bool = False
    migration_directory: str = "migrations"
    pool_size: int = 5
    max_overflow: int = 10


@dataclass
class DeliveryConfig:
    """Delivery-specific configuration."""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""
    sender_address: str = ""
    default_recipients: list[str] = field(default_factory=list)
    subject_template: str = "Lead Hunter Dossier: {{ lead_name }}"
    html_template: str = "default"
    text_template: str = "default"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


@dataclass
class SchedulerConfig:
    """Scheduler-specific configuration."""
    timezone: str = "UTC"
    job_store: str = "memory"
    max_instances: int = 1
    misfire_grace_time: int = 3600


@dataclass
class LoggingConfig:
    """Logging-specific configuration."""
    level: str = "INFO"
    format: str = "json"
    outputs: list[str] = field(default_factory=lambda: ["stdout"])
    mask_secrets: bool = True


@dataclass
class SecurityConfig:
    """Security-specific configuration."""
    max_payload_size_bytes: int = 10_485_760
    allowed_domains: list[str] = field(default_factory=list)
    prompt_injection_patterns: list[str] = field(default_factory=list)
    max_control_chars_ratio: float = 0.05


@dataclass
class AppConfig:
    """Top-level application configuration."""
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    @classmethod
    def load(cls, config_file: Path | str | None = None, overrides: dict[str, Any] | None = None) -> "AppConfig":
        """Load configuration from defaults, file, environment, and overrides."""
        raw = DEFAULT_CONFIG.copy()

        # Layer 2: configuration file
        if config_file:
            file_config = _load_config_file(Path(config_file))
            raw = _deep_merge(raw, file_config)

        # Layer 3: environment variables
        env_config = _load_env_overrides()
        raw = _deep_merge(raw, env_config)

        # Layer 4: run-specific overrides
        if overrides:
            raw = _deep_merge(raw, overrides)

        # Validate required sections
        required_sections = ["orchestrator", "agents", "persistence", "delivery", "scheduler", "logging", "security"]
        for section in required_sections:
            if section not in raw:
                raise ConfigurationError(f"Missing required configuration section: {section}")

        # Build typed config
        orch = raw["orchestrator"]
        orchestrator_cfg = OrchestratorConfig(
            max_concurrent_runs=orch.get("max_concurrent_runs", 10),
            approval_timeout_seconds=orch.get("approval_timeout_seconds", 86400),
            default_retry_count=orch.get("default_retry_count", 3),
            retry_backoff_base_seconds=orch.get("retry_backoff_base_seconds", 2.0),
            retry_backoff_max_seconds=orch.get("retry_backoff_max_seconds", 60.0),
            scoring_weights=orch.get("scoring_weights", DEFAULT_CONFIG["orchestrator"]["scoring_weights"]),
            auto_approve_threshold=orch.get("auto_approve_threshold", 85),
            require_approval_threshold=orch.get("require_approval_threshold", 60),
            auto_reject_threshold=orch.get("auto_reject_threshold", 60),
        )

        agents_cfg: dict[str, AgentConfig] = {}
        for name, cfg in raw.get("agents", {}).items():
            agents_cfg[name] = AgentConfig(
                api_endpoint=cfg.get("api_endpoint", ""),
                model=cfg.get("model", ""),
                timeout_connect=cfg.get("timeout_connect", 10.0),
                timeout_read=cfg.get("timeout_read", 60.0),
                timeout_total=cfg.get("timeout_total", 120.0),
                max_tokens=cfg.get("max_tokens", 4096),
                temperature=cfg.get("temperature", 0.0),
                max_retries=cfg.get("max_retries", 3),
            )

        pers = raw["persistence"]
        persistence_cfg = PersistenceConfig(
            database_url=pers.get("database_url", "sqlite:///lead_hunter.db"),
            echo_sql=pers.get("echo_sql", False),
            migration_directory=pers.get("migration_directory", "migrations"),
            pool_size=pers.get("pool_size", 5),
            max_overflow=pers.get("max_overflow", 10),
        )

        deliv = raw["delivery"]
        delivery_cfg = DeliveryConfig(
            smtp_host=deliv.get("smtp_host", ""),
            smtp_port=deliv.get("smtp_port", 587),
            smtp_use_tls=deliv.get("smtp_use_tls", True),
            smtp_username=deliv.get("smtp_username", ""),
            smtp_password=deliv.get("smtp_password", ""),
            sender_address=deliv.get("sender_address", ""),
            default_recipients=deliv.get("default_recipients", []),
            subject_template=deliv.get("subject_template", "Lead Hunter Dossier: {{ lead_name }}"),
            html_template=deliv.get("html_template", "default"),
            text_template=deliv.get("text_template", "default"),
            telegram_bot_token=deliv.get("telegram_bot_token", ""),
            telegram_chat_id=deliv.get("telegram_chat_id", ""),
        )

        sched = raw["scheduler"]
        scheduler_cfg = SchedulerConfig(
            timezone=sched.get("timezone", "UTC"),
            job_store=sched.get("job_store", "memory"),
            max_instances=sched.get("max_instances", 1),
            misfire_grace_time=sched.get("misfire_grace_time", 3600),
        )

        log = raw["logging"]
        logging_cfg = LoggingConfig(
            level=log.get("level", "INFO"),
            format=log.get("format", "json"),
            outputs=log.get("outputs", ["stdout"]),
            mask_secrets=log.get("mask_secrets", True),
        )

        sec = raw["security"]
        security_cfg = SecurityConfig(
            max_payload_size_bytes=sec.get("max_payload_size_bytes", 10_485_760),
            allowed_domains=sec.get("allowed_domains", []),
            prompt_injection_patterns=sec.get("prompt_injection_patterns", DEFAULT_CONFIG["security"]["prompt_injection_patterns"]),
            max_control_chars_ratio=sec.get("max_control_chars_ratio", 0.05),
        )

        return cls(
            orchestrator=orchestrator_cfg,
            agents=agents_cfg,
            persistence=persistence_cfg,
            delivery=delivery_cfg,
            scheduler=scheduler_cfg,
            logging=logging_cfg,
            security=security_cfg,
        )

    def validate(self) -> None:
        """Validate configuration values."""
        if self.orchestrator.max_concurrent_runs <= 0:
            raise ConfigurationError("max_concurrent_runs must be > 0")
        if self.orchestrator.approval_timeout_seconds <= 0:
            raise ConfigurationError("approval_timeout_seconds must be > 0")
        if self.orchestrator.default_retry_count < 0:
            raise ConfigurationError("default_retry_count must be >= 0")
        if self.orchestrator.retry_backoff_base_seconds <= 0:
            raise ConfigurationError("retry_backoff_base_seconds must be > 0")
        if self.orchestrator.retry_backoff_max_seconds <= 0:
            raise ConfigurationError("retry_backoff_max_seconds must be > 0")
        if self.orchestrator.auto_approve_threshold < self.orchestrator.require_approval_threshold:
            raise ConfigurationError("auto_approve_threshold must be >= require_approval_threshold")
        if self.orchestrator.require_approval_threshold < self.orchestrator.auto_reject_threshold:
            raise ConfigurationError("require_approval_threshold must be >= auto_reject_threshold")

        total_weight = sum(self.orchestrator.scoring_weights.values())
        if total_weight != 100:
            raise ConfigurationError(f"scoring_weights must sum to 100, got {total_weight}")

        if not self.persistence.database_url:
            raise ConfigurationError("database_url is required")

        if self.security.max_payload_size_bytes <= 0:
            raise ConfigurationError("max_payload_size_bytes must be > 0")
        if self.security.max_control_chars_ratio < 0 or self.security.max_control_chars_ratio > 1:
            raise ConfigurationError("max_control_chars_ratio must be between 0 and 1")
