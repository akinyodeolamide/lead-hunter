"""Scheduler service for Lead Hunter using APScheduler."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from lead_hunter.logging_config import get_logger, log_event
from lead_hunter.scheduler.campaign import CampaignSchedule, CampaignStatus, ScheduleType

logger = get_logger("scheduler")


class SchedulerService:
    """APScheduler-based scheduler for campaign management."""

    def __init__(
        self,
        persistence: Any,
        engine: Any,
        workflow_factory: Any,
        jobstore_url: str | None = None,
    ) -> None:
        self.persistence = persistence
        self.engine = engine
        self.workflow_factory = workflow_factory
        self._scheduler: AsyncIOScheduler | None = None
        self._jobstore_url = jobstore_url
        self._campaigns: dict[UUID, CampaignSchedule] = {}

    def _get_scheduler(self) -> AsyncIOScheduler:
        """Lazy initialization of the scheduler."""
        if self._scheduler is None:
            jobstores = {}
            if self._jobstore_url:
                from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
                jobstores["default"] = SQLAlchemyJobStore(url=self._jobstore_url)
            self._scheduler = AsyncIOScheduler(jobstores=jobstores)
        return self._scheduler

    async def start(self) -> None:
        """Start the scheduler and reload any persisted campaigns."""
        scheduler = self._get_scheduler()
        scheduler.start()
        # Reload persisted campaigns if persistence supports it
        if hasattr(self.persistence, 'list_campaigns'):
            campaigns = await self.persistence.list_campaigns()
            for campaign in campaigns:
                if campaign.status == CampaignStatus.ACTIVE:
                    try:
                        trigger = self._build_trigger(campaign)
                        scheduler.add_job(
                            func=self._execute_campaign,
                            trigger=trigger,
                            id=str(campaign.campaign_id),
                            name=campaign.name,
                            replace_existing=True,
                            kwargs={"campaign_id": campaign.campaign_id},
                            max_instances=1,
                        )
                        self._campaigns[campaign.campaign_id] = campaign
                        log_event(logger, "INFO", f"Reloaded campaign {campaign.campaign_id}: {campaign.name}")
                    except Exception as exc:
                        log_event(logger, "WARNING", f"Failed to reload campaign {campaign.campaign_id}: {exc}")
        log_event(logger, "INFO", "Scheduler started")

    async def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=True)
            except Exception:
                pass
            log_event(logger, "INFO", "Scheduler shut down")

    async def create_campaign(self, campaign: CampaignSchedule) -> CampaignSchedule:
        """Create and schedule a new campaign."""
        scheduler = self._get_scheduler()
        trigger = self._build_trigger(campaign)

        job = scheduler.add_job(
            func=self._execute_campaign,
            trigger=trigger,
            id=str(campaign.campaign_id),
            name=campaign.name,
            replace_existing=True,
            kwargs={"campaign_id": campaign.campaign_id},
            max_instances=1,
        )

        campaign.next_run_at = getattr(job, "next_run_time", None)
        self._campaigns[campaign.campaign_id] = campaign

        # Persist campaign if persistence supports it
        if hasattr(self.persistence, 'save_campaign'):
            await self.persistence.save_campaign(campaign)

        log_event(
            logger,
            "INFO",
            f"Campaign {campaign.campaign_id} scheduled: {campaign.name}",
            context={"schedule_type": campaign.schedule_type.name},
        )
        return campaign

    async def pause_campaign(self, campaign_id: UUID) -> CampaignSchedule | None:
        """Pause a campaign."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            return None
        scheduler = self._get_scheduler()
        scheduler.pause_job(str(campaign_id))
        campaign.status = CampaignStatus.PAUSED
        log_event(logger, "INFO", f"Campaign {campaign_id} paused")
        return campaign

    async def resume_campaign(self, campaign_id: UUID) -> CampaignSchedule | None:
        """Resume a paused campaign."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            return None
        scheduler = self._get_scheduler()
        scheduler.resume_job(str(campaign_id))
        campaign.status = CampaignStatus.ACTIVE
        log_event(logger, "INFO", f"Campaign {campaign_id} resumed")
        return campaign

    async def delete_campaign(self, campaign_id: UUID) -> bool:
        """Delete a campaign."""
        scheduler = self._get_scheduler()
        try:
            scheduler.remove_job(str(campaign_id))
        except Exception:
            pass
        if campaign_id in self._campaigns:
            del self._campaigns[campaign_id]
            # Remove from persistence if supported
            if hasattr(self.persistence, 'delete_campaign'):
                await self.persistence.delete_campaign(campaign_id)
            log_event(logger, "INFO", f"Campaign {campaign_id} deleted")
            return True
        return False

    async def list_campaigns(self) -> list[CampaignSchedule]:
        """List all campaigns."""
        return list(self._campaigns.values())

    async def get_campaign(self, campaign_id: UUID) -> CampaignSchedule | None:
        """Get a campaign by ID."""
        return self._campaigns.get(campaign_id)

    def _build_trigger(self, campaign: CampaignSchedule) -> Any:
        """Build an APScheduler trigger from campaign config."""
        config = campaign.schedule_config
        if campaign.schedule_type == ScheduleType.CRON:
            return CronTrigger(**config)
        elif campaign.schedule_type == ScheduleType.INTERVAL:
            return IntervalTrigger(**config)
        elif campaign.schedule_type == ScheduleType.DATE:
            return DateTrigger(**config)
        else:
            raise ValueError(f"Unknown schedule type: {campaign.schedule_type}")

    async def _execute_campaign(self, campaign_id: UUID) -> None:
        """Execute a campaign run."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None or campaign.status != CampaignStatus.ACTIVE:
            log_event(logger, "WARNING", f"Campaign {campaign_id} not found or inactive, skipping")
            return

        if campaign.max_runs is not None and campaign.run_count >= campaign.max_runs:
            log_event(logger, "INFO", f"Campaign {campaign_id} reached max runs ({campaign.max_runs})")
            campaign.status = CampaignStatus.COMPLETED
            await self.delete_campaign(campaign_id)
            return

        try:
            run = await self.engine.start_run(configuration_id=campaign.configuration_id)
            workflow = self.workflow_factory()
            run = await workflow.execute_run(
                run=run,
                lead_name=campaign.lead_name_template,
                industry=campaign.industry,
                summary=campaign.summary_template,
                initial_claims=campaign.initial_claims,
            )
            campaign.run_count += 1
            campaign.last_run_at = datetime.now(timezone.utc)
            log_event(
                logger,
                "INFO",
                f"Campaign {campaign_id} executed run {run.run_id}: {run.status.name}",
            )
            # Check if max runs reached after execution
            if campaign.max_runs is not None and campaign.run_count >= campaign.max_runs:
                log_event(logger, "INFO", f"Campaign {campaign_id} reached max runs ({campaign.max_runs})")
                campaign.status = CampaignStatus.COMPLETED
                await self.delete_campaign(campaign_id)
                return
        except Exception as exc:
            campaign.status = CampaignStatus.ERROR
            log_event(logger, "ERROR", f"Campaign {campaign_id} execution failed: {exc}")
