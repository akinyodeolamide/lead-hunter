"""Campaign schedule definitions for Lead Hunter."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class CampaignStatus(str, Enum):
    """Status of a campaign schedule."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class ScheduleType(str, Enum):
    """Type of schedule trigger."""
    CRON = "CRON"
    INTERVAL = "INTERVAL"
    DATE = "DATE"


@dataclass
class CampaignSchedule:
    """A scheduled campaign for recurring lead research."""
    campaign_id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    status: CampaignStatus = CampaignStatus.ACTIVE
    schedule_type: ScheduleType = ScheduleType.INTERVAL
    schedule_config: dict[str, Any] = field(default_factory=dict)
    # For workflow execution
    configuration_id: str = ""
    lead_name_template: str = ""
    industry: str = ""
    summary_template: str = ""
    initial_claims: list[str] = field(default_factory=list)
    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    run_count: int = 0
    max_runs: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
