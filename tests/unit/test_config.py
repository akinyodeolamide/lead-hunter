"""Unit tests for configuration system."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from lead_hunter.config.config import AppConfig, DEFAULT_CONFIG
from lead_hunter.exceptions import ConfigurationError


class TestAppConfigDefaults:
    """Test default configuration loading."""

    def test_load_defaults(self) -> None:
        cfg = AppConfig.load()
        assert cfg.orchestrator.max_concurrent_runs == 10
        assert cfg.orchestrator.default_retry_count == 3
        assert cfg.orchestrator.retry_backoff_base_seconds == 2.0
        assert cfg.orchestrator.retry_backoff_max_seconds == 60.0
        assert cfg.orchestrator.auto_approve_threshold == 85
        assert cfg.orchestrator.require_approval_threshold == 60
        assert cfg.orchestrator.auto_reject_threshold == 60

    def test_default_scoring_weights_sum_to_100(self) -> None:
        cfg = AppConfig.load()
        total = sum(cfg.orchestrator.scoring_weights.values())
        assert total == 100

    def test_default_agents_present(self) -> None:
        cfg = AppConfig.load()
        assert "chatgpt" in cfg.agents
        assert "gemini" in cfg.agents
        assert "kimi" in cfg.agents
        assert "claude" in cfg.agents

    def test_default_persistence(self) -> None:
        cfg = AppConfig.load()
        assert cfg.persistence.database_url == "sqlite:///lead_hunter.db"
        assert cfg.persistence.echo_sql is False

    def test_default_logging(self) -> None:
        cfg = AppConfig.load()
        assert cfg.logging.level == "INFO"
        assert cfg.logging.format == "json"
        assert cfg.logging.mask_secrets is True


class TestAppConfigFileLoading:
    """Test configuration file loading."""

    def test_load_from_yaml_file(self) -> None:
        config_data = {
            "orchestrator": {
                "max_concurrent_runs": 20,
                "default_retry_count": 5,
            },
            "agents": {
                "chatgpt": {
                    "model": "gpt-4o-mini",
                    "max_tokens": 8192,
                }
            },
            "persistence": {
                "database_url": "postgresql://user:pass@localhost/db",
            },
            "delivery": {"smtp_host": "smtp.example.com"},
            "scheduler": {"timezone": "America/New_York"},
            "logging": {"level": "DEBUG"},
            "security": {"max_payload_size_bytes": 5_000_000},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            path = f.name
        try:
            cfg = AppConfig.load(config_file=path)
            assert cfg.orchestrator.max_concurrent_runs == 20
            assert cfg.orchestrator.default_retry_count == 5
            assert cfg.agents["chatgpt"].model == "gpt-4o-mini"
            assert cfg.agents["chatgpt"].max_tokens == 8192
            assert cfg.persistence.database_url == "postgresql://user:pass@localhost/db"
            assert cfg.delivery.smtp_host == "smtp.example.com"
            assert cfg.scheduler.timezone == "America/New_York"
            assert cfg.logging.level == "DEBUG"
            assert cfg.security.max_payload_size_bytes == 5_000_000
        finally:
            os.unlink(path)

    def test_missing_sections_filled_from_defaults(self) -> None:
        """Missing sections are filled from default config, not rejected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"orchestrator": {}}, f)
            path = f.name
        try:
            cfg = AppConfig.load(config_file=path)
            # All missing sections are filled from defaults
            assert cfg.persistence.database_url == "sqlite:///lead_hunter.db"
            assert cfg.delivery.smtp_host == ""
            assert cfg.scheduler.timezone == "UTC"
            assert cfg.logging.level == "INFO"
        finally:
            os.unlink(path)


class TestAppConfigEnvOverrides:
    """Test environment variable overrides."""

    def test_env_override_simple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LH_ORCHESTRATOR__MAX_CONCURRENT_RUNS", "42")
        cfg = AppConfig.load()
        assert cfg.orchestrator.max_concurrent_runs == 42

    def test_env_override_nested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LH_PERSISTENCE__DATABASE_URL", "sqlite:///test.db")
        cfg = AppConfig.load()
        assert cfg.persistence.database_url == "sqlite:///test.db"

    def test_env_override_boolean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LH_PERSISTENCE__ECHO_SQL", "true")
        cfg = AppConfig.load()
        assert cfg.persistence.echo_sql is True

    def test_env_override_float(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LH_ORCHESTRATOR__RETRY_BACKOFF_BASE_SECONDS", "5.5")
        cfg = AppConfig.load()
        assert cfg.orchestrator.retry_backoff_base_seconds == 5.5

    def test_env_override_list_stored_as_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Environment variables for list fields are stored as raw strings
        # (a known limitation; lists should be configured via file)
        monkeypatch.setenv("LH_SECURITY__ALLOWED_DOMAINS", "example.com,test.com")
        cfg = AppConfig.load()
        assert cfg.security.allowed_domains == "example.com,test.com"


class TestAppConfigRunOverrides:
    """Test run-specific overrides."""

    def test_run_override(self) -> None:
        overrides = {"orchestrator": {"max_concurrent_runs": 99}}
        cfg = AppConfig.load(overrides=overrides)
        assert cfg.orchestrator.max_concurrent_runs == 99

    def test_run_override_preserves_defaults(self) -> None:
        overrides = {"orchestrator": {"max_concurrent_runs": 99}}
        cfg = AppConfig.load(overrides=overrides)
        assert cfg.orchestrator.default_retry_count == 3  # unchanged


class TestAppConfigValidation:
    """Test configuration validation."""

    def test_valid_config_passes(self) -> None:
        cfg = AppConfig.load()
        cfg.validate()  # should not raise

    def test_invalid_max_concurrent_runs(self) -> None:
        cfg = AppConfig.load()
        cfg.orchestrator.max_concurrent_runs = 0
        with pytest.raises(ConfigurationError, match="max_concurrent_runs must be > 0"):
            cfg.validate()

    def test_invalid_approval_timeout(self) -> None:
        cfg = AppConfig.load()
        cfg.orchestrator.approval_timeout_seconds = -1
        with pytest.raises(ConfigurationError, match="approval_timeout_seconds must be > 0"):
            cfg.validate()

    def test_invalid_retry_count(self) -> None:
        cfg = AppConfig.load()
        cfg.orchestrator.default_retry_count = -1
        with pytest.raises(ConfigurationError, match="default_retry_count must be >= 0"):
            cfg.validate()

    def test_invalid_backoff_base(self) -> None:
        cfg = AppConfig.load()
        cfg.orchestrator.retry_backoff_base_seconds = 0
        with pytest.raises(ConfigurationError, match="retry_backoff_base_seconds must be > 0"):
            cfg.validate()

    def test_invalid_backoff_max(self) -> None:
        cfg = AppConfig.load()
        cfg.orchestrator.retry_backoff_max_seconds = 0
        with pytest.raises(ConfigurationError, match="retry_backoff_max_seconds must be > 0"):
            cfg.validate()

    def test_scoring_weights_must_sum_to_100(self) -> None:
        cfg = AppConfig.load()
        cfg.orchestrator.scoring_weights = {"evidence_quality": 50, "business_viability": 40}
        with pytest.raises(ConfigurationError, match="scoring_weights must sum to 100"):
            cfg.validate()

    def test_invalid_threshold_ordering_auto_approve(self) -> None:
        cfg = AppConfig.load()
        cfg.orchestrator.auto_approve_threshold = 50
        cfg.orchestrator.require_approval_threshold = 60
        with pytest.raises(ConfigurationError, match="auto_approve_threshold must be >= require_approval_threshold"):
            cfg.validate()

    def test_invalid_threshold_ordering_require(self) -> None:
        cfg = AppConfig.load()
        cfg.orchestrator.require_approval_threshold = 50
        cfg.orchestrator.auto_reject_threshold = 60
        with pytest.raises(ConfigurationError, match="require_approval_threshold must be >= auto_reject_threshold"):
            cfg.validate()

    def test_missing_database_url(self) -> None:
        cfg = AppConfig.load()
        cfg.persistence.database_url = ""
        with pytest.raises(ConfigurationError, match="database_url is required"):
            cfg.validate()

    def test_invalid_payload_size(self) -> None:
        cfg = AppConfig.load()
        cfg.security.max_payload_size_bytes = 0
        with pytest.raises(ConfigurationError, match="max_payload_size_bytes must be > 0"):
            cfg.validate()

    def test_invalid_control_chars_ratio_low(self) -> None:
        cfg = AppConfig.load()
        cfg.security.max_control_chars_ratio = -0.1
        with pytest.raises(ConfigurationError, match="max_control_chars_ratio must be between 0 and 1"):
            cfg.validate()

    def test_invalid_control_chars_ratio_high(self) -> None:
        cfg = AppConfig.load()
        cfg.security.max_control_chars_ratio = 1.1
        with pytest.raises(ConfigurationError, match="max_control_chars_ratio must be between 0 and 1"):
            cfg.validate()
