"""Tests for persistence factory."""
from __future__ import annotations

import os

import pytest

from lead_hunter.persistence.factory import create_persistence, create_persistence_sync
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.persistence.sql_adapter import SQLPersistence


class TestPersistenceFactory:
    @pytest.mark.asyncio
    async def test_default_returns_in_memory(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        pers = await create_persistence()
        assert isinstance(pers, InMemoryPersistence)

    @pytest.mark.asyncio
    async def test_database_url_returns_sql(self) -> None:
        url = "sqlite+aiosqlite:///file::memory:?cache=shared"
        pers = await create_persistence(database_url=url)
        assert isinstance(pers, SQLPersistence)

    def test_sync_default_returns_in_memory(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        pers = create_persistence_sync()
        assert isinstance(pers, InMemoryPersistence)

    def test_sync_database_url_returns_sql(self) -> None:
        url = "sqlite+aiosqlite:///file::memory:?cache=shared"
        pers = create_persistence_sync(database_url=url)
        assert isinstance(pers, SQLPersistence)

    @pytest.mark.asyncio
    async def test_campaign_roundtrip_sql(self) -> None:
        from lead_hunter.scheduler.campaign import CampaignSchedule, CampaignStatus, ScheduleType
        url = "sqlite+aiosqlite:///file::memory:?cache=shared"
        pers = await create_persistence(database_url=url)
        campaign = CampaignSchedule(
            name="Test Campaign",
            status=CampaignStatus.ACTIVE,
            schedule_type=ScheduleType.INTERVAL,
            schedule_config={"seconds": 60},
        )
        await pers.save_campaign(campaign)
        retrieved = await pers.get_campaign(campaign.campaign_id)
        assert retrieved is not None
        assert retrieved.name == "Test Campaign"
        campaigns = await pers.list_campaigns()
        assert len(campaigns) == 1
        deleted = await pers.delete_campaign(campaign.campaign_id)
        assert deleted is True
        assert await pers.get_campaign(campaign.campaign_id) is None
