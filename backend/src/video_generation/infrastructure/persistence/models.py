import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class Actor(Base):
    __tablename__ = "actors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="user")


class Membership(Base):
    __tablename__ = "memberships"
    tenant_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Pairing(Base):
    __tablename__ = "pairings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "actor_id"], ["memberships.tenant_id", "memberships.actor_id"]
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(String(36))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceSession(Base):
    __tablename__ = "device_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "actor_id"], ["memberships.tenant_id", "memberships.actor_id"]
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(String(36))
    device_name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_list", "tenant_id", "archived_at", "created_at", "id"),)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    product_profile_ref: Mapped[str] = mapped_column(String(100))
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    event_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Command(Base):
    __tablename__ = "commands"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "actor_id"], ["memberships.tenant_id", "memberships.actor_id"]
        ),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    command_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(80))
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    http_status: Mapped[int] = mapped_column(Integer, default=200)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    __tablename__ = "project_events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "project_id"], ["projects.tenant_id", "projects.id"]),
        UniqueConstraint("tenant_id", "project_id", "seq", name="uq_project_event_seq"),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(80))
    row_version: Mapped[int] = mapped_column(Integer)
    causation_command_id: Mapped[str] = mapped_column(String(36))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    subject_ref: Mapped[dict | None] = mapped_column(JSONB)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class ContentRevisionRow(Base):
    __tablename__ = "content_revisions"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "project_id"], ["projects.tenant_id", "projects.id"]),
        UniqueConstraint("tenant_id", "project_id", "entity_kind", "revision"),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36))
    entity_kind: Mapped[str] = mapped_column(String(20))
    revision: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    parent_revision_id: Mapped[str | None] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContentHeadRow(Base):
    __tablename__ = "content_heads"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "project_id"], ["projects.tenant_id", "projects.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "revision_id"], ["content_revisions.tenant_id", "content_revisions.id"]
        ),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    revision_id: Mapped[str] = mapped_column(String(36))
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    review_status: Mapped[str] = mapped_column(String(20), default="DRAFT")


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "project_id"], ["projects.tenant_id", "projects.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "revision_id"], ["content_revisions.tenant_id", "content_revisions.id"]
        ),
        Index("ix_approvals_revision", "tenant_id", "revision_id", "created_at"),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36))
    revision_id: Mapped[str] = mapped_column(String(36))
    subject_ref: Mapped[dict] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column(String(20))
    policy_version: Mapped[str] = mapped_column(String(80), default="manual-content/v1")
    comment: Mapped[str] = mapped_column(String(2000))
    actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    command_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductionSnapshotRow(Base):
    __tablename__ = "production_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "project_id"], ["projects.tenant_id", "projects.id"]),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36))
    data: Mapped[dict] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductionRunRow(Base):
    __tablename__ = "production_runs"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "project_id"], ["projects.tenant_id", "projects.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["production_snapshots.tenant_id", "production_snapshots.id"],
        ),
        Index("ix_runs_project", "tenant_id", "project_id", "created_at"),
        UniqueConstraint("workflow_id"),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(36))
    snapshot_id: Mapped[str] = mapped_column(String(36))
    execution_mode: Mapped[str] = mapped_column(String(20), default="simulation")
    workflow_id: Mapped[str] = mapped_column(String(200))
    temporal_run_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(30), default="CREATED")
    stage: Mapped[str] = mapped_column(String(80), default="waiting_for_worker")
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    control_seq: Mapped[int] = mapped_column(Integer, default=0)
    consumed_control_seq: Mapped[int] = mapped_column(Integer, default=0)
    completed_shots: Mapped[int] = mapped_column(Integer, default=0)
    total_shots: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(2000))
    start_actor_id: Mapped[str] = mapped_column(String(36))
    start_command_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunControlRow(Base):
    __tablename__ = "run_controls"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"], ["production_runs.tenant_id", "production_runs.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "actor_id", "command_id"],
            ["commands.tenant_id", "commands.actor_id", "commands.command_id"],
        ),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(String(36))
    command_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SimulationStepRow(Base):
    __tablename__ = "simulation_steps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"], ["production_runs.tenant_id", "production_runs.id"]
        ),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    stage: Mapped[str] = mapped_column(String(80))
    shot_id: Mapped[str | None] = mapped_column(String(36))
    result: Mapped[dict] = mapped_column(JSONB)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxRow(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"], ["production_runs.tenant_id", "production_runs.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "id"], ["project_events.tenant_id", "project_events.id"]
        ),
        Index("ix_outbox_delivery", "status", "available_at"),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InboxRow(Base):
    __tablename__ = "inbox"
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    consumer: Mapped[str] = mapped_column(String(200), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    result: Mapped[dict] = mapped_column(JSONB)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ServiceHeartbeatRow(Base):
    __tablename__ = "service_heartbeats"
    service: Mapped[str] = mapped_column(String(50), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
