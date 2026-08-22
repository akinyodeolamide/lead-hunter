"""FastAPI dependencies for Lead Hunter API."""
from __future__ import annotations

from typing import Any

from fastapi import Request

from lead_hunter.approval.approval_service import ApprovalService
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.scheduler.scheduler_service import SchedulerService


def get_persistence(request: Request) -> Any:
    """Get persistence from app state."""
    return request.app.state.persistence


def get_engine(request: Request) -> OrchestrationEngine:
    """Get orchestration engine from app state."""
    return request.app.state.engine


def get_approval_service(request: Request) -> ApprovalService:
    """Get approval service from app state."""
    return request.app.state.approval_service


def get_scheduler(request: Request) -> SchedulerService:
    """Get scheduler service from app state."""
    return request.app.state.scheduler
