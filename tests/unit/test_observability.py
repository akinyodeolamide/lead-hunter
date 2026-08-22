"""Unit tests for observability components."""
from __future__ import annotations

import pytest

from lead_hunter.observability.health import HealthAggregator, HealthCheckResult
from lead_hunter.observability.metrics import MetricType, MetricsCollector
from lead_hunter.orchestrator.interfaces import HealthStatus


class TestMetricsCollector:
    def test_metrics_collector_counter(self) -> None:
        collector = MetricsCollector()
        collector.counter("runs_started", 1.0)
        collector.counter("runs_started", 1.0)
        metrics = collector.get_counters("runs_started")
        assert len(metrics) == 2
        assert all(m.type == MetricType.COUNTER for m in metrics)
        assert metrics[0].value == 1.0

    def test_metrics_collector_timer(self) -> None:
        collector = MetricsCollector()
        collector.timer("stage_duration", 2.5)
        metrics = collector.get_timers("stage_duration")
        assert len(metrics) == 1
        assert metrics[0].type == MetricType.TIMER
        assert metrics[0].value == 2.5

    def test_metrics_collector_gauge(self) -> None:
        collector = MetricsCollector()
        collector.gauge("active_runs", 5.0)
        metrics = collector.get_gauges("active_runs")
        assert len(metrics) == 1
        assert metrics[0].type == MetricType.GAUGE
        assert metrics[0].value == 5.0

    def test_metrics_collector_summary(self) -> None:
        collector = MetricsCollector()
        collector.counter("events", 1.0)
        collector.counter("events", 2.0)
        collector.timer("latency", 0.1)
        collector.timer("latency", 0.3)
        collector.gauge("memory_mb", 128.0)

        summary = collector.summary()
        assert summary["counters"]["events"] == 3.0
        assert summary["timers"]["latency"]["count"] == 2
        assert summary["timers"]["latency"]["avg"] == 0.2
        assert summary["gauges"]["memory_mb"] == 128.0

    def test_metrics_collector_clear(self) -> None:
        collector = MetricsCollector()
        collector.counter("x", 1.0)
        assert len(collector.get_metrics()) == 1
        collector.clear()
        assert len(collector.get_metrics()) == 0

    def test_metrics_collector_labels(self) -> None:
        collector = MetricsCollector()
        collector.counter("requests", 1.0, labels={"agent": "gemini"})
        metrics = collector.get_metrics()
        assert metrics[0].labels == {"agent": "gemini"}


class TestHealthAggregator:
    @pytest.mark.asyncio
    async def test_health_aggregator_all_healthy(self) -> None:
        aggregator = HealthAggregator()
        aggregator.register_component(
            "db",
            lambda: HealthCheckResult("db", HealthStatus.HEALTHY),
        )
        aggregator.register_component(
            "smtp",
            lambda: HealthCheckResult("smtp", HealthStatus.HEALTHY),
        )
        results = await aggregator.check_all()
        assert len(results) == 2
        assert all(r.status == HealthStatus.HEALTHY for r in results.values())
        assert await aggregator.overall_status() == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_aggregator_one_unhealthy(self) -> None:
        aggregator = HealthAggregator()
        aggregator.register_component(
            "db",
            lambda: HealthCheckResult("db", HealthStatus.HEALTHY),
        )
        aggregator.register_component(
            "smtp",
            lambda: HealthCheckResult("smtp", HealthStatus.UNHEALTHY, "Connection refused"),
        )
        results = await aggregator.check_all()
        assert results["smtp"].status == HealthStatus.UNHEALTHY
        assert await aggregator.overall_status() == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_health_aggregator_degraded(self) -> None:
        aggregator = HealthAggregator()
        aggregator.register_component(
            "db",
            lambda: HealthCheckResult("db", HealthStatus.HEALTHY),
        )
        aggregator.register_component(
            "cache",
            lambda: HealthCheckResult("cache", HealthStatus.DEGRADED, "Slow response"),
        )
        assert await aggregator.overall_status() == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_health_aggregator_exception_in_check(self) -> None:
        aggregator = HealthAggregator()

        async def failing_check() -> HealthCheckResult:
            raise RuntimeError("Boom")

        aggregator.register_component("bad", failing_check)
        results = await aggregator.check_all()
        assert results["bad"].status == HealthStatus.UNHEALTHY
        assert "Boom" in results["bad"].message
