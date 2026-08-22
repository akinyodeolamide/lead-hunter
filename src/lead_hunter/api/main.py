"""FastAPI application for Lead Hunter API."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from lead_hunter.api.auth import verify_api_key
from lead_hunter.api.dependencies import (
    get_approval_service,
    get_engine,
    get_persistence,
    get_scheduler,
)
from lead_hunter.approval.approval_service import ApprovalService
from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.models.domain import RunStatus
from lead_hunter.observability.health import HealthAggregator
from lead_hunter.observability.metrics import MetricsCollector
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.scheduler.campaign import CampaignSchedule, ScheduleType
from lead_hunter.scheduler.scheduler_service import SchedulerService
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow

logger = get_logger("api")


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    components: dict[str, Any]


class RunCreateRequest(BaseModel):
    configuration_id: str = "default"
    lead_name: str
    industry: str
    summary: str
    claims: list[str] = Field(default_factory=list)


class RunResponse(BaseModel):
    run_id: str
    status: str
    configuration_id: str
    created_at: str
    metadata: dict[str, Any]


class ApprovalActionRequest(BaseModel):
    decided_by: str
    rationale: str = ""


class CampaignCreateRequest(BaseModel):
    name: str
    description: str = ""
    schedule_type: str = "INTERVAL"
    schedule_config: dict[str, Any] = Field(default_factory=dict)
    configuration_id: str = "default"
    lead_name_template: str = ""
    industry: str = ""
    summary_template: str = ""
    initial_claims: list[str] = Field(default_factory=list)
    max_runs: int | None = None


class CampaignResponse(BaseModel):
    campaign_id: str
    name: str
    status: str
    schedule_type: str
    next_run_at: str | None
    run_count: int


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    import os
    from lead_hunter.persistence.factory import create_persistence
    from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
    from lead_hunter.approval.approval_service import ApprovalService
    from lead_hunter.delivery.telegram_delivery import TelegramDelivery
    from lead_hunter.telegram_bot.bot import LeadHunterTelegramBot

    pers = await create_persistence()

    # Read Telegram settings DIRECTLY from env vars (bypass config loader issues)
    bot_token = os.environ.get("LH_DELIVERY__TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("LH_DELIVERY__TELEGRAM_CHAT_ID", "")
    
    log_event(logger, "INFO", f"ENV CHECK: bot_token length={len(bot_token)}, chat_id={chat_id}")
    
    delivery = None
    if bot_token and chat_id:
        delivery = TelegramDelivery(bot_token=bot_token, chat_id=chat_id)
        log_event(logger, "INFO", "TelegramDelivery configured from env vars")
    else:
        log_event(logger, "WARNING", "Telegram env vars EMPTY - bot will not start")

    engine = OrchestrationEngine(pers, delivery=delivery)
    approval_svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)
    scheduler = SchedulerService(
        pers,
        engine,
        lambda: LeadHunterWorkflow(
            engine,
            approval_service=approval_svc,
            config={"screening_min_evidence": 1},
        ),
    )

    # Start Telegram bot with webhook
    telegram_bot = None
    if bot_token and chat_id:
        try:
            public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "lead-hunter-production-13b0.up.railway.app")
            webhook_url = f"https://{public_domain}/telegram/webhook"
            
            telegram_bot = LeadHunterTelegramBot(
                bot_token=bot_token,
                chat_id=chat_id,
                webhook_url=webhook_url,
                engine=engine,
                persistence=pers,
                approval_service=approval_svc,
            )
            await telegram_bot.start()
            log_event(logger, "INFO", f"Telegram bot webhook set to {webhook_url}")
        except Exception as exc:
            log_event(logger, "ERROR", f"Failed to start Telegram bot: {exc}")
    else:
        log_event(logger, "WARNING", "Telegram bot not started - missing token or chat_id")

    app.state.persistence = pers
    app.state.engine = engine
    app.state.approval_service = approval_svc
    app.state.scheduler = scheduler
    app.state.metrics = MetricsCollector()
    app.state.health = HealthAggregator()
    app.state.telegram_bot = telegram_bot

    await scheduler.start()
    log_event(logger, "INFO", "API server started, scheduler active")
    yield
    if telegram_bot:
        await telegram_bot.stop()
    await scheduler.shutdown()
    log_event(logger, "INFO", "API server stopped, scheduler shut down")


app = FastAPI(
    title="Lead Hunter API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check() -> dict[str, Any]:
    """Liveness and readiness health check."""
    return {
        "status": "healthy",
        "components": {"api": "ok", "scheduler": "ok"},
    }


@app.post("/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    req: RunCreateRequest,
    engine: OrchestrationEngine = Depends(get_engine),
    approval_service: ApprovalService = Depends(get_approval_service),
    api_key: str = Depends(verify_api_key),
) -> RunResponse:
    """Start a new lead hunter workflow run."""
    run = await engine.start_run(
        configuration_id=req.configuration_id,
        metadata={
            "lead_name": req.lead_name,
            "industry": req.industry,
            "summary": req.summary,
        },
    )
    workflow = LeadHunterWorkflow(
        engine,
        approval_service=approval_service,
        config={"screening_min_evidence": 1},
    )
    run = await workflow.execute_run(
        run=run,
        lead_name=req.lead_name,
        industry=req.industry,
        summary=req.summary,
        initial_claims=req.claims or None,
    )
    return RunResponse(
        run_id=str(run.run_id),
        status=run.status.name,
        configuration_id=run.configuration_id,
        created_at=run.created_at.isoformat(),
        metadata=run.metadata,
    )


@app.get("/runs")
async def list_runs(
    status: str | None = None,
    engine: OrchestrationEngine = Depends(get_engine),
    api_key: str = Depends(verify_api_key),
) -> list[RunResponse]:
    """List all runs, optionally filtered by status."""
    run_status = None
    if status:
        try:
            run_status = RunStatus[status.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    runs = await engine.persistence.list_runs(status=run_status, limit=1000)
    return [
        RunResponse(
            run_id=str(r.run_id),
            status=r.status.name,
            configuration_id=r.configuration_id,
            created_at=r.created_at.isoformat(),
            metadata=r.metadata,
        )
        for r in runs
    ]


@app.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    engine: OrchestrationEngine = Depends(get_engine),
    api_key: str = Depends(verify_api_key),
) -> RunResponse:
    """Get a single run by ID."""
    try:
        rid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format")
    run = await engine.persistence.get_run(rid)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse(
        run_id=str(run.run_id),
        status=run.status.name,
        configuration_id=run.configuration_id,
        created_at=run.created_at.isoformat(),
        metadata=run.metadata,
    )


@app.post("/runs/{run_id}/pause")
async def pause_run(
    run_id: str,
    engine: OrchestrationEngine = Depends(get_engine),
    approval_service: ApprovalService = Depends(get_approval_service),
    api_key: str = Depends(verify_api_key),
) -> RunResponse:
    """Pause a run."""
    try:
        rid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format")
    run = await engine.persistence.get_run(rid)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run = await approval_service.pause(rid)
    return RunResponse(
        run_id=str(run.run_id),
        status=run.status.name,
        configuration_id=run.configuration_id,
        created_at=run.created_at.isoformat(),
        metadata=run.metadata,
    )


@app.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    engine: OrchestrationEngine = Depends(get_engine),
    approval_service: ApprovalService = Depends(get_approval_service),
    api_key: str = Depends(verify_api_key),
) -> RunResponse:
    """Resume a paused run."""
    try:
        rid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format")
    run = await engine.persistence.get_run(rid)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run = await approval_service.resume(rid)
    return RunResponse(
        run_id=str(run.run_id),
        status=run.status.name,
        configuration_id=run.configuration_id,
        created_at=run.created_at.isoformat(),
        metadata=run.metadata,
    )


@app.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    engine: OrchestrationEngine = Depends(get_engine),
    api_key: str = Depends(verify_api_key),
) -> RunResponse:
    """Cancel a running or queued run."""
    try:
        rid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format")
    run = await engine.persistence.get_run(rid)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run = await engine.cancel_run(rid)
    return RunResponse(
        run_id=str(run.run_id),
        status=run.status.name,
        configuration_id=run.configuration_id,
        created_at=run.created_at.isoformat(),
        metadata=run.metadata,
    )


@app.get("/approvals")
async def list_approvals(
    approval_service: ApprovalService = Depends(get_approval_service),
    api_key: str = Depends(verify_api_key),
) -> list[dict[str, Any]]:
    """List all pending approvals."""
    approvals = await approval_service.get_waiting_approvals()
    return [
        {
            "approval_id": str(a.approval_id),
            "run_id": str(a.run_id),
            "stage_id": str(a.stage_id),
            "approval_type": a.approval_type.name,
            "decision": a.decision.name,
            "deadline": a.deadline.isoformat() if a.deadline else None,
            "request_details": a.request_details,
        }
        for a in approvals
    ]


@app.post("/approvals/{approval_id}/approve")
async def approve_approval(
    approval_id: str,
    req: ApprovalActionRequest,
    approval_service: ApprovalService = Depends(get_approval_service),
    api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Approve a pending approval request."""
    try:
        aid = UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid approval_id format")
    try:
        result = await approval_service.approve(aid, req.decided_by, req.rationale)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "approval_id": str(result.approval_id),
        "decision": result.decision.name,
        "decided_by": result.decided_by,
    }


@app.post("/approvals/{approval_id}/reject")
async def reject_approval(
    approval_id: str,
    req: ApprovalActionRequest,
    approval_service: ApprovalService = Depends(get_approval_service),
    api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Reject a pending approval request."""
    try:
        aid = UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid approval_id format")
    try:
        result = await approval_service.reject(aid, req.decided_by, req.rationale)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "approval_id": str(result.approval_id),
        "decision": result.decision.name,
        "decided_by": result.decided_by,
    }


@app.get("/campaigns")
async def list_campaigns(
    scheduler: SchedulerService = Depends(get_scheduler),
    api_key: str = Depends(verify_api_key),
) -> list[CampaignResponse]:
    """List all scheduled campaigns."""
    campaigns = await scheduler.list_campaigns()
    return [
        CampaignResponse(
            campaign_id=str(c.campaign_id),
            name=c.name,
            status=c.status.name,
            schedule_type=c.schedule_type.name,
            next_run_at=c.next_run_at.isoformat() if c.next_run_at else None,
            run_count=c.run_count,
        )
        for c in campaigns
    ]


@app.post("/campaigns", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    req: CampaignCreateRequest,
    scheduler: SchedulerService = Depends(get_scheduler),
    api_key: str = Depends(verify_api_key),
) -> CampaignResponse:
    """Create a new scheduled campaign."""
    try:
        st = ScheduleType[req.schedule_type.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid schedule_type: {req.schedule_type}")
    campaign = CampaignSchedule(
        name=req.name,
        description=req.description,
        schedule_type=st,
        schedule_config=req.schedule_config,
        configuration_id=req.configuration_id,
        lead_name_template=req.lead_name_template,
        industry=req.industry,
        summary_template=req.summary_template,
        initial_claims=req.initial_claims,
        max_runs=req.max_runs,
    )
    created = await scheduler.create_campaign(campaign)
    return CampaignResponse(
        campaign_id=str(created.campaign_id),
        name=created.name,
        status=created.status.name,
        schedule_type=created.schedule_type.name,
        next_run_at=created.next_run_at.isoformat() if created.next_run_at else None,
        run_count=created.run_count,
    )


@app.post("/stages/{stage_id}/retry")
async def retry_stage(
    stage_id: str,
    engine: OrchestrationEngine = Depends(get_engine),
    api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Retry a failed stage."""
    try:
        sid = UUID(stage_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid stage_id format")
    try:
        stage = await engine.retry_stage(sid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    return {
        "stage_id": str(stage.stage_id),
        "status": stage.status.name,
        "retry_count": stage.retry_count,
    }


@app.get("/metrics")
async def get_metrics(
    request: Request,
    api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return system metrics."""
    metrics: MetricsCollector = request.app.state.metrics
    summary = metrics.summary()
    return {
        "runs_total": summary.get("counters", {}),
        "stages_total": summary.get("counters", {}),
        "approvals_pending": len(metrics.get_gauges("approvals_pending")),
        "agent_requests_total": summary.get("counters", {}),
        "delivery_attempts_total": summary.get("counters", {}),
    }


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    update: dict[str, Any],
) -> dict[str, str]:
    """Receive Telegram updates via webhook."""
    bot: LeadHunterTelegramBot | None = getattr(request.app.state, "telegram_bot", None)
    if bot:
        await bot.handle_update(update)
    return {"status": "ok"}
