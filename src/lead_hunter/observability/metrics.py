"""Metrics collection for Lead Hunter."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from lead_hunter.logging_config import get_logger, log_event

logger = get_logger("observability.metrics")


class MetricType(str, Enum):
    """Type of metric."""
    COUNTER = "counter"
    TIMER = "timer"
    GAUGE = "gauge"


@dataclass
class Metric:
    """A single metric data point."""
    name: str
    value: float
    type: MetricType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """In-memory metrics collector.

    Collects counters, timers, and gauges.
    Not intended for production-scale metrics — use Prometheus/etc for that.
    """

    def __init__(self) -> None:
        self._metrics: list[Metric] = []

    def counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        metric = Metric(
            name=name,
            value=value,
            type=MetricType.COUNTER,
            labels=labels or {},
        )
        self._metrics.append(metric)
        log_event(logger, "DEBUG", f"Counter {name} += {value}")

    def timer(self, name: str, duration: float, labels: dict[str, str] | None = None) -> None:
        """Record a timer metric (duration in seconds)."""
        metric = Metric(
            name=name,
            value=duration,
            type=MetricType.TIMER,
            labels=labels or {},
        )
        self._metrics.append(metric)
        log_event(logger, "DEBUG", f"Timer {name} = {duration:.4f}s")

    def gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric."""
        metric = Metric(
            name=name,
            value=value,
            type=MetricType.GAUGE,
            labels=labels or {},
        )
        self._metrics.append(metric)
        log_event(logger, "DEBUG", f"Gauge {name} = {value}")

    def get_metrics(self, name: str | None = None, metric_type: MetricType | None = None) -> list[Metric]:
        """Return collected metrics, optionally filtered."""
        result = self._metrics[:]
        if name:
            result = [m for m in result if m.name == name]
        if metric_type:
            result = [m for m in result if m.type == metric_type]
        return result

    def get_counters(self, name: str | None = None) -> list[Metric]:
        """Return counter metrics."""
        return self.get_metrics(name=name, metric_type=MetricType.COUNTER)

    def get_timers(self, name: str | None = None) -> list[Metric]:
        """Return timer metrics."""
        return self.get_metrics(name=name, metric_type=MetricType.TIMER)

    def get_gauges(self, name: str | None = None) -> list[Metric]:
        """Return gauge metrics."""
        return self.get_metrics(name=name, metric_type=MetricType.GAUGE)

    def clear(self) -> None:
        """Clear all collected metrics."""
        self._metrics.clear()

    def summary(self) -> dict[str, Any]:
        """Return a summary of all metrics."""
        counters: dict[str, float] = {}
        timers: dict[str, list[float]] = {}
        gauges: dict[str, float] = {}

        for m in self._metrics:
            if m.type == MetricType.COUNTER:
                counters[m.name] = counters.get(m.name, 0.0) + m.value
            elif m.type == MetricType.TIMER:
                timers.setdefault(m.name, []).append(m.value)
            elif m.type == MetricType.GAUGE:
                gauges[m.name] = m.value

        return {
            "counters": counters,
            "timers": {k: {"count": len(v), "avg": sum(v) / len(v), "min": min(v), "max": max(v)} for k, v in timers.items()},
            "gauges": gauges,
        }
