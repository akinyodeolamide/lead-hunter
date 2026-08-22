"""Graceful shutdown handling for Lead Hunter."""
from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any, Callable

from lead_hunter.logging_config import get_logger, log_event

logger = get_logger("shutdown")


class ShutdownHandler:
    """Handles graceful shutdown on SIGTERM/SIGINT signals."""

    def __init__(self) -> None:
        self._shutdown_event = asyncio.Event()
        self._cleanup_tasks: list[Callable[[], Any]] = []
        self._is_shutting_down = False

    def register_cleanup(self, task: Callable[[], Any]) -> None:
        """Register a cleanup task to run on shutdown."""
        self._cleanup_tasks.append(task)

    def install_signal_handlers(self) -> None:
        """Install SIGTERM and SIGINT handlers."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._signal_handler, sig)
        log_event(logger, "INFO", "Signal handlers installed")

    def _signal_handler(self, sig: int) -> None:
        """Handle shutdown signal."""
        sig_name = signal.Signals(sig).name
        log_event(logger, "INFO", f"Received {sig_name}, initiating graceful shutdown")
        self._is_shutting_down = True
        self._shutdown_event.set()

    async def wait_for_shutdown(self) -> None:
        """Block until shutdown signal is received."""
        await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        """Execute all cleanup tasks."""
        log_event(logger, "INFO", f"Running {len(self._cleanup_tasks)} cleanup tasks")
        for task in self._cleanup_tasks:
            try:
                if asyncio.iscoroutinefunction(task):
                    await task()
                else:
                    task()
            except Exception as exc:
                log_event(logger, "ERROR", f"Cleanup task failed: {exc}")
        log_event(logger, "INFO", "Graceful shutdown complete")

    @property
    def is_shutting_down(self) -> bool:
        return self._is_shutting_down
