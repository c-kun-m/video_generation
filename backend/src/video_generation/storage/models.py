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
