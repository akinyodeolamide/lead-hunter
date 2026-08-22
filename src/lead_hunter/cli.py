"""Command-line interface for Lead Hunter."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import click
from dotenv import load_dotenv

from lead_hunter.config.config import AppConfig
from lead_hunter.logging_config import setup_logging
from lead_hunter.exceptions import ConfigurationError, SecretError


def _load_env() -> None:
    """Load environment variables from .env file if present."""
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)


def _validate_secrets() -> None:
    """Validate that required secrets are present."""
    required = [
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "MOONSHOT_API_KEY",
        "ANTHROPIC_API_KEY",
    ]
    missing = []
    for secret in required:
        value = os.environ.get(secret)
        if not value:
            missing.append(secret)
        elif value.startswith("placeholder") or value.startswith("YOUR_") or value.startswith("<"):
            click.echo(f"WARNING: Secret {secret} appears to be a placeholder value", err=True)

    if missing:
        raise SecretError(
            f"Missing required secrets: {', '.join(missing)}. "
            "Set them as environment variables or in a .env file."
        )


@click.group()
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to configuration file")
@click.option("--log-level", "-l", default="INFO", help="Log level")
@click.option("--log-format", "-f", default="json", type=click.Choice(["json", "human"]), help="Log format")
@click.pass_context
def cli(ctx: click.Context, config: str | None, log_level: str, log_format: str) -> None:
    """Lead Hunter — AI Agent Orchestrator for Lead Discovery."""
    _load_env()

    setup_logging(level=log_level, fmt=log_format)

    try:
        cfg = AppConfig.load(config_file=config)
        cfg.validate()
        ctx.ensure_object(dict)
        ctx.obj["config"] = cfg
    except ConfigurationError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def version(ctx: click.Context) -> None:
    """Show version information."""
    click.echo("Lead Hunter 1.0.0")


@cli.command()
@click.option("--validate-secrets", is_flag=True, help="Validate required secrets are present")
@click.pass_context
def check(ctx: click.Context, validate_secrets: bool) -> None:
    """Check system health and configuration."""
    click.echo("Configuration loaded successfully.")
    if validate_secrets:
        try:
            _validate_secrets()
            click.echo("All required secrets are present.")
        except SecretError as e:
            click.echo(f"Secret validation failed: {e}", err=True)
            sys.exit(1)


@cli.command()
@click.option("--approval-id", type=str, required=True, help="Approval ID to approve")
@click.option("--by", "decided_by", type=str, required=True, help="Who is making the decision")
@click.option("--rationale", type=str, default="", help="Approval rationale")
@click.pass_context
def approve(ctx: click.Context, approval_id: str, decided_by: str, rationale: str) -> None:
    """Approve a pending approval request."""
    from uuid import UUID
    from lead_hunter.approval.approval_service import ApprovalService
    from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
    from lead_hunter.persistence.factory import create_persistence

    async def _do_approve() -> None:
        pers = await create_persistence()
        engine = OrchestrationEngine(pers)
        svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)
        result = await svc.approve(UUID(approval_id), decided_by, rationale)
        click.echo(f"Approval {result.approval_id} approved by {decided_by}.")

    asyncio.run(_do_approve())


@cli.command()
@click.option("--approval-id", type=str, required=True, help="Approval ID to reject")
@click.option("--by", "decided_by", type=str, required=True, help="Who is making the decision")
@click.option("--rationale", type=str, default="", help="Rejection rationale")
@click.pass_context
def reject(ctx: click.Context, approval_id: str, decided_by: str, rationale: str) -> None:
    """Reject a pending approval request."""
    from uuid import UUID
    from lead_hunter.approval.approval_service import ApprovalService
    from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
    from lead_hunter.persistence.factory import create_persistence

    async def _do_reject() -> None:
        pers = await create_persistence()
        engine = OrchestrationEngine(pers)
        svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)
        result = await svc.reject(UUID(approval_id), decided_by, rationale)
        click.echo(f"Approval {result.approval_id} rejected by {decided_by}.")

    asyncio.run(_do_reject())


@cli.command()
@click.option("--run-id", type=str, required=True, help="Run ID to pause")
@click.pass_context
def pause(ctx: click.Context, run_id: str) -> None:
    """Pause a run waiting for approval."""
    from uuid import UUID
    from lead_hunter.approval.approval_service import ApprovalService
    from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
    from lead_hunter.persistence.factory import create_persistence

    async def _do_pause() -> None:
        pers = await create_persistence()
        engine = OrchestrationEngine(pers)
        svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)
        run = await svc.pause(UUID(run_id))
        click.echo(f"Run {run.run_id} paused.")

    asyncio.run(_do_pause())


@cli.command()
@click.option("--run-id", type=str, required=True, help="Run ID to resume")
@click.pass_context
def resume(ctx: click.Context, run_id: str) -> None:
    """Resume a paused run."""
    from uuid import UUID
    from lead_hunter.approval.approval_service import ApprovalService
    from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
    from lead_hunter.persistence.factory import create_persistence

    async def _do_resume() -> None:
        pers = await create_persistence()
        engine = OrchestrationEngine(pers)
        svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)
        run = await svc.resume(UUID(run_id))
        click.echo(f"Run {run.run_id} resumed.")

    asyncio.run(_do_resume())


@cli.command()
@click.option("--run-id", type=str, required=True, help="Run ID to cancel")
@click.pass_context
def cancel(ctx: click.Context, run_id: str) -> None:
    """Cancel a running or queued run."""
    from uuid import UUID
    from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
    from lead_hunter.persistence.factory import create_persistence

    async def _do_cancel() -> None:
        pers = await create_persistence()
        engine = OrchestrationEngine(pers)
        run = await engine.cancel_run(UUID(run_id))
        if run:
            click.echo(f"Run {run.run_id} cancelled.")
        else:
            click.echo(f"Run {run_id} not found.", err=True)
            sys.exit(1)

    asyncio.run(_do_cancel())


@cli.command()
@click.option("--stage-id", type=str, required=True, help="Stage ID to retry")
@click.pass_context
def retry_stage(ctx: click.Context, stage_id: str) -> None:
    """Retry a failed stage."""
    from uuid import UUID
    from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
    from lead_hunter.persistence.factory import create_persistence

    async def _do_retry() -> None:
        pers = await create_persistence()
        engine = OrchestrationEngine(pers)
        try:
            stage = await engine.retry_stage(UUID(stage_id))
            if stage:
                click.echo(f"Stage {stage.stage_id} scheduled for retry (attempt {stage.retry_count}).")
            else:
                click.echo(f"Stage {stage_id} not found.", err=True)
                sys.exit(1)
        except ValueError as e:
            click.echo(str(e), err=True)
            sys.exit(1)

    asyncio.run(_do_retry())


@cli.command(name="list-waiting")
@click.pass_context
def list_waiting(ctx: click.Context) -> None:
    """List all approvals waiting for human decision."""
    from lead_hunter.approval.approval_service import ApprovalService
    from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
    from lead_hunter.persistence.factory import create_persistence

    async def _do_list() -> None:
        pers = await create_persistence()
        engine = OrchestrationEngine(pers)
        svc = ApprovalService(pers, engine.stage_manager, engine.run_manager)
        waiting = await svc.get_waiting_approvals()
        if not waiting:
            click.echo("No waiting approvals.")
            return
        click.echo(f"{'Approval ID':<40} {'Run ID':<40} {'Stage ID':<40} {'Deadline'}")
        for a in waiting:
            deadline = a.deadline.isoformat() if a.deadline else "N/A"
            click.echo(f"{str(a.approval_id):<40} {str(a.run_id):<40} {str(a.stage_id):<40} {deadline}")

    asyncio.run(_do_list())


@cli.command()
@click.option("--config-id", type=str, required=True, help="Configuration ID")
@click.option("--lead-name", type=str, required=True, help="Lead name")
@click.option("--industry", type=str, required=True, help="Industry")
@click.option("--summary", type=str, required=True, help="Lead summary")
@click.option("--claim", "claims", multiple=True, help="Initial claims")
@click.pass_context
def start(
    ctx: click.Context,
    config_id: str,
    lead_name: str,
    industry: str,
    summary: str,
    claims: tuple[str, ...],
) -> None:
    """Start a new lead hunter workflow run."""
    from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
    from lead_hunter.persistence.factory import create_persistence
    from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow

    async def _do_start() -> None:
        pers = await create_persistence()
        engine = OrchestrationEngine(pers)
        workflow = LeadHunterWorkflow(engine, config={"screening_min_evidence": 1})

        run = await engine.start_run(configuration_id=config_id)
        run = await workflow.execute_run(
            run=run,
            lead_name=lead_name,
            industry=industry,
            summary=summary,
            initial_claims=list(claims) if claims else None,
        )
        click.echo(f"Run {run.run_id} finished with status: {run.status.name}")
        if run.status.name == "COMPLETED":
            click.echo("Lead dossier generated successfully.")
        elif run.status.name == "REJECTED":
            click.echo("Lead was rejected during processing.")
        elif run.status.name == "RUNNING":
            click.echo("Run is waiting for approval or further action.")

    asyncio.run(_do_start())


@cli.command()
@click.pass_context
def serve(ctx: click.Context) -> None:
    """Run the Lead Hunter service (long-running process)."""
    import asyncio
    from lead_hunter.service_runner import ServiceRunner

    async def _do_serve() -> None:
        runner = ServiceRunner()
        click.echo("Lead Hunter service started. Press Ctrl+C to stop.")
        await runner.run_forever()
        click.echo("Lead Hunter service stopped.")

    asyncio.run(_do_serve())


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
