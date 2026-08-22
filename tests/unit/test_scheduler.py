"""Unit tests for scheduler components."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

from lead_hunter.scheduler.campaign import CampaignSchedule, CampaignStatus, ScheduleType
from lead_hunter.scheduler.scheduler_service import SchedulerService


class TestCampaignSchedule:
    """Tests for CampaignSchedule dataclass."""

    def test_default_campaign_creation(self) -> None:
        campaign = CampaignSchedule()
        assert campaign.campaign_id is not None
        assert isinstance(campaign.campaign_id, UUID)
        assert campaign.name == ""
        assert campaign.status == CampaignStatus.ACTIVE
        assert campaign.schedule_type == ScheduleType.INTERVAL
        assert campaign.schedule_config == {}
        assert campaign.run_count == 0
        assert campaign.max_runs is None
        assert campaign.created_at is not None

    def test_campaign_with_values(self) -> None:
        cid = uuid4()
        campaign = CampaignSchedule(
            campaign_id=cid,
            name="Test Campaign",
            description="A test campaign",
            status=CampaignStatus.PAUSED,
            schedule_type=ScheduleType.CRON,
            schedule_config={"hour": "9", "minute": "0"},
            configuration_id="cfg-123",
            lead_name_template="Acme Corp",
            industry="Technology",
            summary_template="Test summary",
            initial_claims=["claim1", "claim2"],
            max_runs=5,
        )
        assert campaign.campaign_id == cid
        assert campaign.name == "Test Campaign"
        assert campaign.status == CampaignStatus.PAUSED
        assert campaign.schedule_type == ScheduleType.CRON
        assert campaign.max_runs == 5

    def test_campaign_status_enum(self) -> None:
        assert CampaignStatus.ACTIVE.value == "ACTIVE"
        assert CampaignStatus.PAUSED.value == "PAUSED"
        assert CampaignStatus.COMPLETED.value == "COMPLETED"
        assert CampaignStatus.ERROR.value == "ERROR"

    def test_schedule_type_enum(self) -> None:
        assert ScheduleType.CRON.value == "CRON"
        assert ScheduleType.INTERVAL.value == "INTERVAL"
        assert ScheduleType.DATE.value == "DATE"


class TestSchedulerService:
    """Tests for SchedulerService."""

    @pytest.fixture
    def scheduler(self) -> SchedulerService:
        return SchedulerService(
            persistence=None,
            engine=None,
            workflow_factory=lambda: None,
        )

    @pytest.mark.asyncio
    async def test_start_shutdown(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        assert scheduler._scheduler is not None
        assert scheduler._scheduler.running
        await scheduler.shutdown()
        # APScheduler may not immediately reflect stopped state; verify no exception

    @pytest.mark.asyncio
    async def test_create_campaign_interval(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        campaign = CampaignSchedule(
            name="Interval Campaign",
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 3600},
        )
        result = await scheduler.create_campaign(campaign)
        assert result.campaign_id in scheduler._campaigns
        assert scheduler._campaigns[result.campaign_id].name == "Interval Campaign"
        assert result.next_run_at is not None
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_create_campaign_cron(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        campaign = CampaignSchedule(
            name="Cron Campaign",
            schedule_type=ScheduleType.CRON,
            schedule_config={"hour": "9", "minute": "0"},
        )
        result = await scheduler.create_campaign(campaign)
        assert result.campaign_id in scheduler._campaigns
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_pause_resume_campaign(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        campaign = CampaignSchedule(
            name="Pause Test",
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 3600},
        )
        created = await scheduler.create_campaign(campaign)

        paused = await scheduler.pause_campaign(created.campaign_id)
        assert paused is not None
        assert paused.status == CampaignStatus.PAUSED

        resumed = await scheduler.resume_campaign(created.campaign_id)
        assert resumed is not None
        assert resumed.status == CampaignStatus.ACTIVE

        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_pause_nonexistent_campaign(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        result = await scheduler.pause_campaign(uuid4())
        assert result is None
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_resume_nonexistent_campaign(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        result = await scheduler.resume_campaign(uuid4())
        assert result is None
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_delete_campaign(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        campaign = CampaignSchedule(
            name="Delete Test",
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 3600},
        )
        created = await scheduler.create_campaign(campaign)
        deleted = await scheduler.delete_campaign(created.campaign_id)
        assert deleted is True
        assert created.campaign_id not in scheduler._campaigns
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_campaign(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        deleted = await scheduler.delete_campaign(uuid4())
        assert deleted is False
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_list_campaigns(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        c1 = CampaignSchedule(name="C1", schedule_type=ScheduleType.INTERVAL, schedule_config={"seconds": 60})
        c2 = CampaignSchedule(name="C2", schedule_type=ScheduleType.INTERVAL, schedule_config={"seconds": 120})
        await scheduler.create_campaign(c1)
        await scheduler.create_campaign(c2)

        campaigns = await scheduler.list_campaigns()
        assert len(campaigns) == 2
        names = {c.name for c in campaigns}
        assert names == {"C1", "C2"}
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_get_campaign(self, scheduler: SchedulerService) -> None:
        await scheduler.start()
        campaign = CampaignSchedule(name="Get Test", schedule_type=ScheduleType.INTERVAL, schedule_config={"seconds": 60})
        created = await scheduler.create_campaign(campaign)

        found = await scheduler.get_campaign(created.campaign_id)
        assert found is not None
        assert found.name == "Get Test"

        not_found = await scheduler.get_campaign(uuid4())
        assert not_found is None
        await scheduler.shutdown()

    def test_build_trigger_interval(self, scheduler: SchedulerService) -> None:
        from apscheduler.triggers.interval import IntervalTrigger
        campaign = CampaignSchedule(
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 300},
        )
        trigger = scheduler._build_trigger(campaign)
        assert isinstance(trigger, IntervalTrigger)

    def test_build_trigger_cron(self, scheduler: SchedulerService) -> None:
        from apscheduler.triggers.cron import CronTrigger
        campaign = CampaignSchedule(
            schedule_type=ScheduleType.CRON,
            schedule_config={"hour": "9", "minute": "0"},
        )
        trigger = scheduler._build_trigger(campaign)
        assert isinstance(trigger, CronTrigger)

    def test_build_trigger_date(self, scheduler: SchedulerService) -> None:
        from apscheduler.triggers.date import DateTrigger
        run_date = datetime.now(timezone.utc) + timedelta(hours=1)
        campaign = CampaignSchedule(
            schedule_type=ScheduleType.DATE,
            schedule_config={"run_date": run_date},
        )
        trigger = scheduler._build_trigger(campaign)
        assert isinstance(trigger, DateTrigger)

    def test_build_trigger_unknown(self, scheduler: SchedulerService) -> None:
        campaign = CampaignSchedule(schedule_type="UNKNOWN")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="Unknown schedule type"):
            scheduler._build_trigger(campaign)

    @pytest.mark.asyncio
    async def test_scheduler_with_jobstore_url(self) -> None:
        """Test that jobstore_url is passed through correctly."""
        svc = SchedulerService(
            persistence=None,
            engine=None,
            workflow_factory=lambda: None,
            jobstore_url="sqlite:///test_scheduler_jobs.db",
        )
        assert svc._jobstore_url == "sqlite:///test_scheduler_jobs.db"


class TestSchedulerServiceCampaignExecution:
    """Tests for campaign execution logic."""

    @pytest.mark.asyncio
    async def test_execute_campaign_not_found(self) -> None:
        scheduler = SchedulerService(persistence=None, engine=None, workflow_factory=lambda: None)
        await scheduler.start()
        # Should not raise — campaign not in _campaigns
        await scheduler._execute_campaign(uuid4())
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_execute_campaign_inactive(self) -> None:
        scheduler = SchedulerService(persistence=None, engine=None, workflow_factory=lambda: None)
        await scheduler.start()
        campaign = CampaignSchedule(
            name="Inactive",
            status=CampaignStatus.PAUSED,
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 3600},
        )
        await scheduler.create_campaign(campaign)
        # Should skip because campaign is inactive
        await scheduler._execute_campaign(campaign.campaign_id)
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_execute_campaign_max_runs_reached(self) -> None:
        scheduler = SchedulerService(persistence=None, engine=None, workflow_factory=lambda: None)
        await scheduler.start()
        campaign = CampaignSchedule(
            name="Max Runs",
            status=CampaignStatus.ACTIVE,
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 3600},
            max_runs=2,
            run_count=2,
        )
        await scheduler.create_campaign(campaign)
        await scheduler._execute_campaign(campaign.campaign_id)
        assert campaign.status == CampaignStatus.COMPLETED
        await scheduler.shutdown()
