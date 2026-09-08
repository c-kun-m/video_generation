from collections.abc import Awaitable, Callable

from sqlalchemy.dialects.postgresql import insert

from video_generation.contracts.models import CommandResult
from video_generation.domain.auth import ActorContext
from video_generation.domain.content import canonical_digest
from video_generation.domain.errors import DomainError, not_found
from video_generation.infrastructure.persistence.models import Command, Event, ProjectRow, new_id


class CommandHandler:
    """One transaction owns command admission, the business result, events and outbox."""

    def __init__(self, sessions):
        self.sessions = sessions

    async def execute(
        self,
        actor: ActorContext,
        command_id: str,
        action: str,
        payload: dict,
        mutation: Callable[..., Awaitable[CommandResult]],
        success_status: int = 200,
    ) -> tuple[CommandResult, int]:
        digest = canonical_digest({"action": action, "payload": payload})
        async with self.sessions() as session, session.begin():
            claim = await session.scalar(
                insert(Command)
                .values(
                    tenant_id=actor.tenant_id,
                    actor_id=actor.actor_id,
                    command_id=command_id,
                    action=action,
                    request_digest=digest,
                    result={},
                )
                .on_conflict_do_nothing()
                .returning(Command.command_id)
            )
            record = await session.get(Command, (actor.tenant_id, actor.actor_id, command_id))
            if claim is None:
                if record.request_digest != digest:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "同一命令 ID 已用于不同请求。", 409)
                return CommandResult.model_validate(record.result), record.http_status
            try:
                async with session.begin_nested():
                    result = await mutation(session)
                status = success_status
            except DomainError as exc:
                result = CommandResult(command_id=command_id, status="REJECTED", error=exc.detail)
                status = exc.status_code
            record.result = result.model_dump(mode="json")
            record.http_status = status
        return result, status

    async def get(self, actor: ActorContext, command_id: str) -> CommandResult:
        async with self.sessions() as session:
            record = await session.get(Command, (actor.tenant_id, actor.actor_id, command_id))
            if record is None:
                raise not_found()
            return CommandResult.model_validate(record.result)


def append_event(
    session,
    project: ProjectRow,
    command_id: str,
    event_type: str,
    subject_ref=None,
    payload=None,
    row_version=None,
) -> Event:
    # Every writer locks the project first. Sequence allocation and commit share that lock.
    project.event_seq += 1
    event = Event(
        id=new_id(),
        tenant_id=project.tenant_id,
        project_id=project.id,
        seq=project.event_seq,
        type=event_type,
        row_version=row_version or project.row_version,
        causation_command_id=command_id,
        subject_ref=subject_ref.model_dump(mode="json") if subject_ref else None,
        payload=payload or {},
    )
    session.add(event)
    return event
