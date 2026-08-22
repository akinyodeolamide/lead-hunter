"""SQLAlchemy ORM models for Lead Hunter."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunORM(Base):
    __tablename__ = "runs"

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    configuration_id: Mapped[str] = mapped_column(String(100), default="default")
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    stages: Mapped[list["StageORM"]] = relationship(back_populates="run", lazy="selectin")
    approvals: Mapped[list["ApprovalORM"]] = relationship(back_populates="run", lazy="selectin")
    events: Mapped[list["EventORM"]] = relationship(back_populates="run", lazy="selectin")
    artifacts: Mapped[list["ArtifactORM"]] = relationship(back_populates="run", lazy="selectin")
    errors: Mapped[list["ErrorORM"]] = relationship(back_populates="run", lazy="selectin")


class StageORM(Base):
    __tablename__ = "stages"

    stage_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("runs.run_id"))
    stage_type: Mapped[str] = mapped_column(String(30), default="INIT")
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped["RunORM"] = relationship(back_populates="stages")


class ApprovalORM(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("runs.run_id"))
    stage_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("stages.stage_id"))
    approval_type: Mapped[str] = mapped_column(String(30), default="MANUAL_REVIEW")
    decision: Mapped[str] = mapped_column(String(20), default="PENDING")
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_details: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped["RunORM"] = relationship(back_populates="approvals")


class EventORM(Base):
    __tablename__ = "events"

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("runs.run_id"), nullable=True)
    stage_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("stages.stage_id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), default="STARTUP")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)

    run: Mapped["RunORM | None"] = relationship(back_populates="events")


class ArtifactORM(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("runs.run_id"))
    artifact_type: Mapped[str] = mapped_column(String(30), default="RESEARCH_BRIEF")
    schema_version: Mapped[str] = mapped_column(String(10), default="1.0.0")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    producer: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    run: Mapped["RunORM"] = relationship(back_populates="artifacts")


class ErrorORM(Base):
    __tablename__ = "errors"

    error_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("runs.run_id"), nullable=True)
    stage_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("stages.stage_id"), nullable=True)
    error_type: Mapped[str] = mapped_column(String(50), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_recoverable: Mapped[bool] = mapped_column(default=False)
    recovery_attempted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    run: Mapped["RunORM | None"] = relationship(back_populates="errors")


class ConfigurationORM(Base):
    __tablename__ = "configurations"

    config_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    config_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class CampaignORM(Base):
    __tablename__ = "campaigns"

    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    schedule_type: Mapped[str] = mapped_column(String(20), default="INTERVAL")
    schedule_config: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration_id: Mapped[str] = mapped_column(String(100), default="default")
    lead_name_template: Mapped[str] = mapped_column(String(255), default="")
    industry: Mapped[str] = mapped_column(String(100), default="")
    summary_template: Mapped[str] = mapped_column(Text, default="")
    initial_claims: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    max_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
