"""Integration tests for scheduler campaign recovery."""
from __future__ import annotations

import pytest

from lead_hunter.orchestrator.orchestration_engine import OrchestrationEngine
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.scheduler.campaign import CampaignSchedule, CampaignStatus, ScheduleType
from lead_hunter.scheduler.scheduler_service import SchedulerService


class TestSchedulerRecovery:
    @pytest.mark.asyncio
    async def test_reload_campaigns_on_start(self) -> None:
        pers = InMemoryPersistence()
        engine = OrchestrationEngine(pers)
        scheduler = SchedulerService(pers, engine, lambda: None)

        # Create and manually persist a campaign
        campaign = CampaignSchedule(
            name="Recovery Test",
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 3600},
            status=CampaignStatus.ACTIVE,
        )
        await scheduler.create_campaign(campaign)
        await pers.save_campaign(campaign)

        # Create a new scheduler instance (simulating restart)
        scheduler2 = SchedulerService(pers, engine, lambda: None)
        await scheduler2.start()
        
        # Campaign should be reloaded
        reloaded = await scheduler2.get_campaign(campaign.campaign_id)
        assert reloaded is not None
        assert reloaded.name == "Recovery Test"
        
        await scheduler.shutdown()
        await scheduler2.shutdown()
