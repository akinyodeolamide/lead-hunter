# Lead Hunter

AI Agent Orchestrator for automated lead discovery, research, and evaluation.

## Overview

Lead Hunter orchestrates multiple AI agents (OpenAI, Gemini, Kimi, Claude) to
research, evaluate, and score potential business leads. It implements a
deterministic, reproducible workflow with human-in-the-loop approval gates,
comprehensive audit trailing, and email delivery of finalized dossiers.

## Architecture

The system follows a 9-stage pipeline:

```
INIT → RESEARCH → SCREENING → DEEP_RESEARCH → AUDIT → SCORING → APPROVAL → DELIVERY → FINALIZATION
```

- **INIT**: Run initialization and configuration loading
- **RESEARCH** (Gemini): Initial evidence gathering and claim verification
- **SCREENING** (OpenAI + deterministic): OpenAI enrichment with deterministic safety fallback
- **DEEP_RESEARCH** (Kimi): Conditional deep-dive based on evidence quality
- **AUDIT** (Claude): Evidence cross-verification and discrepancy detection
- **SCORING**: Deterministic weighted scoring (0-100) across 5 categories
- **APPROVAL**: Human-in-the-loop gate with auto-approve / require-approval / auto-reject
- **DELIVERY**: Email delivery of finalized dossiers via SMTP
- **FINALIZATION**: Run completion and cleanup

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd lead_hunter

# Install with development dependencies
pip install -e ".[dev]"

# Or install for production only
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `GOOGLE_API_KEY` | Google/Gemini API key |
| `MOONSHOT_API_KEY` | Moonshot/Kimi API key |
| `ANTHROPIC_API_KEY` | Anthropic/Claude API key |
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP server port |
| `SMTP_USERNAME` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `SMTP_FROM` | From address for emails |
| `DATABASE_URL` | Database URL (default: in-memory; use `sqlite+aiosqlite:///...` or `postgresql+asyncpg://...` for persistence) |
| `LEAD_HUNTER_API_KEY` | API authentication key |

## Usage

### CLI Commands

```bash
# Check system health
python -m lead_hunter.cli check

# Check with secret validation
python -m lead_hunter.cli check --validate-secrets

# Start a new lead hunter run
python -m lead_hunter.cli start \
  --config-id test \
  --lead-name "Acme Corp" \
  --industry "Technology" \
  --summary "A leading SaaS company"

# List waiting approvals
python -m lead_hunter.cli list-waiting

# Approve a pending lead
python -m lead_hunter.cli approve \
  --approval-id <uuid> \
  --by "reviewer@example.com" \
  --rationale "Strong evidence"

# Reject a pending lead
python -m lead_hunter.cli reject \
  --approval-id <uuid> \
  --by "reviewer@example.com" \
  --rationale "Insufficient evidence"

# Pause a run
python -m lead_hunter.cli pause --run-id <uuid>

# Resume a paused run
python -m lead_hunter.cli resume --run-id <uuid>

# Cancel a run
python -m lead_hunter.cli cancel --run-id <uuid>

# Retry a failed stage
python -m lead_hunter.cli retry-stage --stage-id <uuid>

# Run as a service (long-running)
python -m lead_hunter.cli serve
```

### Programmatic Usage

```python
import asyncio
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow

async def main():
    pers = InMemoryPersistence()
    engine = OrchestrationEngine(pers)
    workflow = LeadHunterWorkflow(engine)

    run = await engine.start_run(configuration_id="my-config")
    run = await workflow.execute_run(
        run=run,
        lead_name="Acme Corp",
        industry="Technology",
        summary="A promising SaaS startup",
    )
    print(f"Run completed with status: {run.status}")

asyncio.run(main())
```

## Scheduler / Autonomous Operation

Lead Hunter includes a built-in scheduler for autonomous campaign execution:

```bash
# Start the service (enables scheduler)
python -m lead_hunter.cli serve

# The scheduler automatically recovers ACTIVE campaigns on startup
# and executes them according to their configured triggers (cron, interval, or date).
```

## Docker

```bash
# Build the image
docker build -t lead-hunter .

# Run with docker-compose
docker-compose up -d

# Check logs
docker-compose logs -f lead-hunter
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=lead_hunter --cov-report=html

# Run specific test file
pytest tests/unit/test_scoring.py -v
```

## Project Structure

```
lead_hunter/
├── src/lead_hunter/
│   ├── adapters/          # AI agent adapters (OpenAI, Gemini, Moonshot, Anthropic)
│   ├── approval/          # Human-in-the-loop approval service
│   ├── artifacts/         # Artifact schemas, factory, and validation
│   ├── config/            # Configuration management
│   ├── delivery/          # Email delivery via SMTP
│   ├── models/            # Domain models (Run, Stage, Artifact, etc.)
│   ├── observability/     # Metrics collection and health checks
│   ├── orchestrator/      # Orchestration engine, state machine, stage/run managers
│   ├── persistence/       # In-memory and SQL persistence adapters
│   ├── recovery/          # Crash recovery service
│   ├── security/          # Sanitizer, rate limiter, secrets manager
│   ├── workflow/          # Lead Hunter workflow and scoring engine
│   ├── cli.py             # Command-line interface
│   ├── exceptions.py      # Exception hierarchy
│   ├── logging_config.py  # Structured logging
│   └── shutdown.py        # Graceful shutdown handler
├── tests/
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## License

MIT License
