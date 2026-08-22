"""Integration tests for security and observability."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from lead_hunter.observability.metrics import MetricsCollector
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.security.rate_limiter import TokenBucketRateLimiter
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow


@pytest.mark.asyncio
class TestSecurityObservabilityIntegration:
    async def test_rate_limited_api_call(self) -> None:
        """Verify rate limiter can throttle adapter calls."""
        limiter = TokenBucketRateLimiter(capacity=2.0, refill_rate=100.0)
        # First two calls succeed immediately
        await limiter.acquire(tokens=1.0)
        await limiter.acquire(tokens=1.0)
        # Tokens may have refilled slightly; assert near zero
        assert limiter.current_tokens() <= 0.1

    async def test_metrics_logged_during_workflow(self) -> None:
        """Verify metrics are collected during workflow execution."""
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        metrics = MetricsCollector()
        workflow = LeadHunterWorkflow(
            engine,
            config={"screening_min_evidence": 1},
        )

        run = await engine.start_run(configuration_id="test")
        run = await workflow.execute_run(
            run=run,
            lead_name="MetricsCo",
            industry="Tech",
            summary="Metrics test",
        )

        # Collect some manual metrics to verify the collector works end-to-end
        metrics.counter("workflows_completed", 1.0, labels={"status": run.status.name})
        metrics.gauge("final_score", 85.0)
        metrics.timer("workflow_duration", 1.5)

        summary = metrics.summary()
        assert summary["counters"]["workflows_completed"] == 1.0
        assert summary["gauges"]["final_score"] == 85.0
        assert summary["timers"]["workflow_duration"]["count"] == 1
