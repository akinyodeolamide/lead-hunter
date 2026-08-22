"""Unit tests for logging configuration."""
from __future__ import annotations

import json
import logging
from io import StringIO
from uuid import uuid4

import pytest

from lead_hunter.logging_config import setup_logging, get_logger, log_event


class TestSetupLogging:
    """Test logging setup."""

    def test_json_format(self, caplog: pytest.LogCaptureFixture) -> None:
        setup_logging(level="DEBUG", fmt="json")
        logger = get_logger("test")
        logger.info("test message")
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.message == "test message"
        assert record.levelname == "INFO"

    def test_human_format(self, caplog: pytest.LogCaptureFixture) -> None:
        setup_logging(level="DEBUG", fmt="human")
        logger = get_logger("test")
        logger.info("test message")
        assert len(caplog.records) == 1

    def test_log_level_filtering(self, caplog: pytest.LogCaptureFixture) -> None:
        setup_logging(level="WARNING", fmt="human")
        logger = get_logger("test")
        logger.info("should not appear")
        logger.warning("should appear")
        assert len(caplog.records) == 1
        assert caplog.records[0].message == "should appear"

    def test_multiple_outputs(self) -> None:
        # Just verify it doesn't crash with multiple outputs
        setup_logging(level="INFO", fmt="json", outputs=["stdout", "stderr"])
        logger = get_logger("test")
        logger.info("multi-output test")


class TestLogEvent:
    """Test structured event logging."""

    def test_log_event_with_correlation(self, caplog: pytest.LogCaptureFixture) -> None:
        setup_logging(level="DEBUG", fmt="json")
        logger = get_logger("test")
        cid = uuid4()
        log_event(logger, "INFO", "run started", correlation_id=cid, run_id=uuid4())
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.message == "run started"
        assert hasattr(record, "correlation_id")
        assert str(cid) == record.correlation_id

    def test_log_event_with_context(self, caplog: pytest.LogCaptureFixture) -> None:
        setup_logging(level="DEBUG", fmt="json")
        logger = get_logger("test")
        log_event(logger, "ERROR", "failure", context={"error_type": "timeout"})
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert hasattr(record, "context")
        assert record.context == {"error_type": "timeout"}

    def test_log_event_default_level(self, caplog: pytest.LogCaptureFixture) -> None:
        setup_logging(level="DEBUG", fmt="json")
        logger = get_logger("test")
        log_event(logger, "INVALID_LEVEL", "test")  # falls back to info
        assert len(caplog.records) == 1
