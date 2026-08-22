"""Health check aggregation for Lead Hunter."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.orchestrator.interfaces import HealthStatus

logger = get_logger("observability.health")


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    component: str
    status: HealthStatus
    message: str | None = None


class HealthAggregator:
    """Aggregates health checks from multiple components."""

    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], Coroutine[Any, Any, HealthCheckResult] | HealthCheckResult]] = {}

    def register_component(
        self,
        name: str,
        check_fn: Callable[[], Coroutine[Any, Any, HealthCheckResult] | HealthCheckResult],
    ) -> None:
        """Register a health check function for a component."""
        self._checks[name] = check_fn
        log_event(logger, "INFO", f"Registered health check for {name}")

    async def check_all(self) -> dict[str, HealthCheckResult]:
        """Run all registered health checks.

        Returns a dict mapping component name to HealthCheckResult.
        """
        results: dict[str, HealthCheckResult] = {}
        for name, check_fn in self._checks.items():
            try:
                if inspect.iscoroutinefunction(check_fn):
                    result = await check_fn()
                else:
                    result = check_fn()
                results[name] = result
            except Exception as exc:
                results[name] = HealthCheckResult(
                    component=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check threw exception: {exc}",
                )
                log_event(logger, "ERROR", f"Health check failed for {name}: {exc}")
        return results

    async def overall_status(self) -> HealthStatus:
        """Return the overall health status.

        HEALTHY if all components are healthy.
        DEGRADED if some are degraded.
        UNHEALTHY if any are unhealthy.
        """
        results = await self.check_all()
        statuses = [r.status for r in results.values()]
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY
