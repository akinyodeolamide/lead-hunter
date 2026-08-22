"""Rate limiter for API call protection."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from lead_hunter.exceptions import RateLimitError
from lead_hunter.logging_config import get_logger, log_event

logger = get_logger("security.rate_limiter")


@dataclass
class RateLimitStatus:
    """Current status of a rate limiter."""
    tokens: float
    capacity: float
    last_refill: datetime


class TokenBucketRateLimiter:
    """Token-bucket rate limiter for API calls.

    Thread-safe via asyncio.Lock.
    """

    def __init__(self, capacity: float = 10.0, refill_rate: float = 1.0) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._tokens = capacity
        self._last_refill = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0, timeout: float | None = None) -> None:
        """Acquire tokens, waiting if necessary.

        Raises RateLimitError if tokens cannot be acquired within timeout.
        """
        async with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                log_event(
                    logger,
                    "DEBUG",
                    f"Acquired {tokens} tokens ({self._tokens:.2f} remaining)",
                )
                return

        # Need to wait for refill
        if timeout is None:
            timeout = (tokens / self.refill_rate) + 1.0

        start = datetime.now(timezone.utc)
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            if elapsed >= timeout:
                raise RateLimitError(
                    f"Rate limit exceeded: could not acquire {tokens} tokens within {timeout}s",
                    details={"tokens_requested": tokens, "timeout": timeout},
                )
            await asyncio.sleep(0.05)

    def current_tokens(self) -> float:
        """Return current token count (not thread-safe; approximate)."""
        self._refill()
        return self._tokens

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = datetime.now(timezone.utc)
        elapsed = (now - self._last_refill).total_seconds()
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
            self._last_refill = now

    def get_status(self) -> RateLimitStatus:
        """Return current rate limit status."""
        return RateLimitStatus(
            tokens=self.current_tokens(),
            capacity=self.capacity,
            last_refill=self._last_refill,
        )
