import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, text

from video_generation.config import Settings
from video_generation.contracts.models import Identity, PairRequest, PairResponse
from video_generation.domain.errors import DomainError
from video_generation.storage.models import (
    Actor,
    DeviceSession,
    Membership,
    Pairing,
    Workspace,
    new_id,
    utcnow,
)


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class ActorContext:
    tenant_id: str
    actor_id: str
    session_id: str
    role: str
    identity: Identity

    def require_editor(self) -> None:
        if self.role not in {"owner", "editor"}:
            raise DomainError("FORBIDDEN", "当前身份没有编辑项目的权限。", 403)


async def initialize_owner(sessions, settings: Settings, name: str = "本机创作者") -> str:
    """Management CLI only: create the owner once and issue a one-time pairing secret."""
    async with sessions() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(63852001)"))
        workspace = await session.scalar(select(Workspace).where(Workspace.slug == "local"))
        if workspace is None:
            workspace = Workspace(id=new_id(), slug="local", name="我的工作空间")
            actor = Actor(id=new_id(), display_name=name, kind="user")
            session.add_all([workspace, actor])
            await session.flush()
            session.add(Membership(tenant_id=workspace.id, actor_id=actor.id, role="owner"))
            await session.flush()
            actor_id = actor.id
        else:
            actor_id = await session.scalar(
                select(Membership.actor_id).where(
                    Membership.tenant_id == workspace.id,
                    Membership.role == "owner",
                    Membership.active.is_(True),
                )
            )
            if actor_id is None:
                raise DomainError("OWNER_MISSING", "本机工作空间缺少有效 owner，请检查数据。")
        # A new management invitation supersedes unused invitations for the same owner.
        unused = await session.scalars(
            select(Pairing).where(
                Pairing.tenant_id == workspace.id,
                Pairing.actor_id == actor_id,
                Pairing.consumed_at.is_(None),
            )
        )
        for old in unused:
            old.consumed_at = utcnow()
        code = secrets.token_urlsafe(32)
        session.add(
            Pairing(
                tenant_id=workspace.id,
                actor_id=actor_id,
                code_hash=secret_hash(code),
                expires_at=utcnow() + timedelta(seconds=settings.pairing_ttl_seconds),
            )
        )
    return code


async def _identity(session, device: DeviceSession) -> Identity:
    row = (
        await session.execute(
            select(Actor, Workspace, Membership)
            .join(Membership, Membership.actor_id == Actor.id)
            .join(Workspace, Workspace.id == Membership.tenant_id)
            .where(
                Actor.id == device.actor_id,
                Workspace.id == device.tenant_id,
                Actor.kind == "user",
                Membership.active.is_(True),
            )
        )
    ).first()
    if row is None:
        raise DomainError("UNAUTHENTICATED", "设备会话已失效，请重新配对。", 401)
    actor, workspace, membership = row
    return Identity(
        actor_id=actor.id,
        tenant_id=workspace.id,
        display_name=actor.display_name,
        workspace_name=workspace.name,
        role=membership.role,
        session_id=device.id,
    )


async def pair_device(sessions, settings: Settings, request: PairRequest) -> PairResponse:
    async with sessions() as session, session.begin():
        invitation = await session.scalar(
            select(Pairing)
            .where(Pairing.code_hash == secret_hash(request.pairing_code))
            .with_for_update()
        )
        now = utcnow()
        if invitation is None or invitation.consumed_at or invitation.expires_at <= now:
            raise DomainError("PAIRING_INVALID", "配对码不可用或已过期，请生成新的配对码。", 401)
        token = secrets.token_urlsafe(48)
        device = DeviceSession(
            id=new_id(),
            tenant_id=invitation.tenant_id,
            actor_id=invitation.actor_id,
            token_hash=secret_hash(token),
            device_name=request.device_name,
            expires_at=now + timedelta(days=settings.session_days),
        )
        identity = await _identity(session, device)
        invitation.consumed_at = now
        session.add(device)
        return PairResponse(
            access_token=token, expires_at=device.expires_at.isoformat(), identity=identity
        )


async def authenticate(sessions, token: str) -> ActorContext:
    async with sessions() as session:
        device = await session.scalar(
            select(DeviceSession).where(
                DeviceSession.token_hash == secret_hash(token),
                DeviceSession.revoked_at.is_(None),
                DeviceSession.expires_at > utcnow(),
            )
        )
        if device is None:
            raise DomainError("UNAUTHENTICATED", "设备未配对或会话已过期。", 401)
        identity = await _identity(session, device)
        return ActorContext(
            identity.tenant_id, identity.actor_id, identity.session_id, identity.role, identity
        )


async def logout(sessions, actor: ActorContext) -> None:
    async with sessions() as session, session.begin():
        device = await session.get(DeviceSession, actor.session_id, with_for_update=True)
        if device and device.tenant_id == actor.tenant_id and device.actor_id == actor.actor_id:
            device.revoked_at = utcnow()
