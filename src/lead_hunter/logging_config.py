"""Structured logging configuration for Lead Hunter."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


class _JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Add correlation fields if present
        for attr in ["correlation_id", "run_id", "stage_id"]:
            if hasattr(record, attr):
                val = getattr(record, attr)
                if val is not None:
                    log_entry[attr] = str(val)
        # Add extra context
        if hasattr(record, "context"):
            log_entry["context"] = record.context
        # Add exception info
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


class _HumanFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    def format(self, record: logging.LogRecord) -> str:
        parts = [
            f"{datetime.now(timezone.utc).isoformat()}",
            f"[{record.levelname}]",
            f"{record.name}",
        ]
        for attr in ["correlation_id", "run_id", "stage_id"]:
            if hasattr(record, attr):
                val = getattr(record, attr)
                if val is not None:
                    parts.append(f"{attr}={val}")
        parts.append(record.getMessage())
        return " ".join(parts)


def setup_logging(level: str = "INFO", fmt: str = "json", outputs: list[str] | None = None) -> None:
    """Configure structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt: Format type ("json" or "human").
        outputs: List of output destinations ("stdout", "stderr", or file paths).
    """
    outputs = outputs or ["stdout"]
    handlers: list[logging.Handler] = []

    formatter: logging.Formatter
    if fmt == "json":
        formatter = _JSONFormatter()
    else:
        formatter = _HumanFormatter()

    for output in outputs:
        if output == "stdout":
            h = logging.StreamHandler(sys.stdout)
        elif output == "stderr":
            h = logging.StreamHandler(sys.stderr)
        else:
            h = logging.FileHandler(output)
        h.setFormatter(formatter)
        handlers.append(h)

    root = logging.getLogger("lead_hunter")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Remove only handlers previously added by this function (tagged),
    # preserving external handlers such as pytest's caplog fixture.
    for h in root.handlers[:]:
        if getattr(h, "_lead_hunter_handler", False):
            root.removeHandler(h)
    for h in handlers:
        h._lead_hunter_handler = True  # type: ignore[attr-defined]
        root.addHandler(h)

    # Also configure standard library loggers we care about
    for name in ["sqlalchemy", "alembic", "apscheduler"]:
        logger = logging.getLogger(name)
        logger.setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the lead_hunter prefix."""
    return logging.getLogger(f"lead_hunter.{name}")


def log_event(
    logger: logging.Logger,
    level: str,
    message: str,
    *,
    correlation_id: UUID | str | None = None,
    run_id: UUID | str | None = None,
    stage_id: UUID | str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Log an event with correlation fields."""
    extra: dict[str, Any] = {}
    if correlation_id is not None:
        extra["correlation_id"] = str(correlation_id)
    if run_id is not None:
        extra["run_id"] = str(run_id)
    if stage_id is not None:
        extra["stage_id"] = str(stage_id)
    if context is not None:
        extra["context"] = context

    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, extra=extra)
