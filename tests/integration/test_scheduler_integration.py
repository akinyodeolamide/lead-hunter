"""Integration tests for scheduler with real orchestrator components."""
from __future__ import annotations

import asyncio
import pytest
from uuid import uuid4

from lead_hunter.models.domain import RunStatus, StageStatus, StageType
from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.scheduler.campaign import CampaignSchedule, CampaignStatus, ScheduleType
from lead_hunter.scheduler.scheduler_service import SchedulerService
from lead_hunter.workflow.lead_hunter_workflow import LeadHunterWorkflow


@pytest.fixture
def persistence() -> InMemoryPersistence:
    return InMemoryPersistence()


@pytest.fixture
def engine(persistence: InMemoryPersistence) -> OrchestrationEngine:
    return OrchestrationEngine(persistence)


class TestSchedulerWithEngine:
    """Integration tests for SchedulerService with OrchestrationEngine."""

    @pytest.mark.asyncio
    async def test_campaign_creates_and_runs(self, engine: OrchestrationEngine, persistence: InMemoryPersistence) -> None:
        """A campaign should trigger a workflow run when executed."""
        workflow_factory = lambda: LeadHunterWorkflow(
            engine,
            config={"screening_min_evidence": 1},
        )

        scheduler = SchedulerService(
            persistence=persistence,
            engine=engine,
            workflow_factory=workflow_factory,
        )
        await scheduler.start()

        campaign = CampaignSchedule(
            name="Integration Test Campaign",
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 3600},
            configuration_id="test-config",
            lead_name_template="TestCorp",
            industry="Software",
            summary_template="A test lead",
            initial_claims=["claim1"],
        )
        created = await scheduler.create_campaign(campaign)
        assert created.campaign_id in scheduler._campaigns

        # Manually trigger execution
        await scheduler._execute_campaign(created.campaign_id)

        # Verify a run was created
        runs = await persistence.list_runs()
        assert len(runs) >= 1
        run = runs[-1]
        assert run.metadata.get("lead_name") == "TestCorp"
        assert run.metadata.get("industry") == "Software"

        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_campaign_max_runs(self, engine: OrchestrationEngine, persistence: InMemoryPersistence) -> None:
        """Campaign should stop after max_runs."""
        workflow_factory = lambda: LeadHunterWorkflow(
            engine,
            config={"screening_min_evidence": 1},
        )

        scheduler = SchedulerService(
            persistence=persistence,
            engine=engine,
            workflow_factory=workflow_factory,
        )
        await scheduler.start()

        campaign = CampaignSchedule(
            name="Max Runs Test",
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 3600},
            max_runs=1,
            configuration_id="test-config",
            lead_name_template="TestCorp",
            industry="Software",
            summary_template="A test lead",
        )
        created = await scheduler.create_campaign(campaign)

        # First execution
        await scheduler._execute_campaign(created.campaign_id)
        assert campaign.run_count == 1
        assert campaign.status == CampaignStatus.COMPLETED

        # Campaign should be removed after completion
        remaining = await scheduler.list_campaigns()
        assert len(remaining) == 0

        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_campaign_list_and_get(self, engine: OrchestrationEngine, persistence: InMemoryPersistence) -> None:
        """Test listing and retrieving campaigns."""
        scheduler = SchedulerService(
            persistence=persistence,
            engine=engine,
            workflow_factory=lambda: None,
        )
        await scheduler.start()

        c1 = CampaignSchedule(name="Campaign 1", schedule_type=ScheduleType.INTERVAL, schedule_config={"seconds": 60})
        c2 = CampaignSchedule(name="Campaign 2", schedule_type=ScheduleType.CRON, schedule_config={"hour": "9"})
        await scheduler.create_campaign(c1)
        await scheduler.create_campaign(c2)

        campaigns = await scheduler.list_campaigns()
        assert len(campaigns) == 2

        found = await scheduler.get_campaign(c1.campaign_id)
        assert found is not None
        assert found.name == "Campaign 1"

        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_campaign_pause_resume_delete(self, engine: OrchestrationEngine, persistence: InMemoryPersistence) -> None:
        """Test full campaign lifecycle."""
        scheduler = SchedulerService(
            persistence=persistence,
            engine=engine,
            workflow_factory=lambda: None,
        )
        await scheduler.start()

        campaign = CampaignSchedule(
            name="Lifecycle Test",
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 300},
        )
        created = await scheduler.create_campaign(campaign)

        # Pause
        paused = await scheduler.pause_campaign(created.campaign_id)
        assert paused is not None
        assert paused.status == CampaignStatus.PAUSED

        # Resume
        resumed = await scheduler.resume_campaign(created.campaign_id)
        assert resumed is not None
        assert resumed.status == CampaignStatus.ACTIVE

        # Delete
        deleted = await scheduler.delete_campaign(created.campaign_id)
        assert deleted is True
        assert await scheduler.get_campaign(created.campaign_id) is None

        await scheduler.shutdown()
