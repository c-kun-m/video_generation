import base64
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from video_generation.contracts.models import (
    CommandResult,
    CreateProject,
    EventPage,
    Project,
    ProjectEvent,
    ProjectPage,
    ProjectRef,
    ProjectSnapshot,
    UpdateProject,
)
from video_generation.domain.auth import ActorContext
from video_generation.domain.errors import DomainError, not_found
from video_generation.storage.models import Command, Event, ProjectRow, new_id, utcnow


def project_dto(row: ProjectRow) -> Project:
    return Project(
        project_id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        product_profile_ref=row.product_profile_ref,
        row_version=row.row_version,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        archived_at=row.archived_at.isoformat() if row.archived_at else None,
    )


def canonical_digest(value: dict) -> str:
    data = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(data.encode()).hexdigest()


class ProjectService:
    def __init__(self, sessions):
        self.sessions = sessions

    async def _command(
        self,
        actor: ActorContext,
        command_id: str,
        action: str,
        payload: dict,
        mutation: Callable[..., Awaitable[ProjectRow]],
        success_status: int = 200,
    ) -> tuple[CommandResult, int]:
        actor.require_editor()
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
                # Domain errors must occur before writes in the mutation. A savepoint also
                # protects future mutations that perform writes before detecting a rejection.
                async with session.begin_nested():
                    project = await mutation(session)
                    result = CommandResult(
                        command_id=command_id,
                        status="APPLIED",
                        business_result_ref=ProjectRef(project_id=project.id),
                        project=project_dto(project),
                    )
                http_status = success_status
            except DomainError as exc:
                result = CommandResult(command_id=command_id, status="REJECTED", error=exc.detail)
                http_status = exc.status_code
            record.result = result.model_dump(mode="json")
            record.http_status = http_status
        return result, http_status

    @staticmethod
    def _event(session, row: ProjectRow, command_id: str, event_type: str) -> None:
        row.event_seq += 1
        session.add(
            Event(
                tenant_id=row.tenant_id,
                project_id=row.id,
                seq=row.event_seq,
                type=event_type,
                row_version=row.row_version,
                causation_command_id=command_id,
            )
        )

    async def create(self, actor: ActorContext, request: CreateProject):
        async def mutation(session):
            now = utcnow()
            row = ProjectRow(
                tenant_id=actor.tenant_id,
                id=new_id(),
                title=request.title,
                product_profile_ref=request.product_profile_ref,
                row_version=1,
                event_seq=0,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            self._event(session, row, request.command_id, "project.created")
            return row

        return await self._command(
            actor, request.command_id, "project.create", request.model_dump(), mutation, 201
        )

    async def update(self, actor: ActorContext, project_id: str, request: UpdateProject):
        async def mutation(session):
            row = await session.get(ProjectRow, (actor.tenant_id, project_id), with_for_update=True)
            if row is None:
                raise not_found()
            if row.row_version != request.expected_row_version:
                raise DomainError(
                    "VERSION_CONFLICT",
                    "项目已被其他操作更新，请比较最新内容后再保存。",
                    409,
                    row.row_version,
                )
            if request.title is not None:
                row.title = request.title
            now = utcnow()
            if request.archived is not None:
                row.archived_at = (row.archived_at or now) if request.archived else None
            row.updated_at = now
            row.row_version += 1
            self._event(session, row, request.command_id, "project.updated")
            return row

        return await self._command(
            actor,
            request.command_id,
            "project.update",
            {"project_id": project_id, **request.model_dump(exclude_none=True)},
            mutation,
        )

    async def get_command(self, actor: ActorContext, command_id: str) -> CommandResult:
        async with self.sessions() as session:
            record = await session.get(Command, (actor.tenant_id, actor.actor_id, command_id))
            if record is None:
                raise not_found()
            return CommandResult.model_validate(record.result)

    async def snapshot(self, actor: ActorContext, project_id: str) -> ProjectSnapshot:
        async with self.sessions() as session:
            row = await session.get(ProjectRow, (actor.tenant_id, project_id))
            if row is None:
                raise not_found()
            # Metadata and cursor come from one SELECT, so they cannot straddle commits.
            return ProjectSnapshot(project=project_dto(row), event_cursor=row.event_seq)

    async def list(
        self, actor: ActorContext, archived: bool, limit: int, cursor: str | None
    ) -> ProjectPage:
        filters = [
            ProjectRow.tenant_id == actor.tenant_id,
            ProjectRow.archived_at.is_not(None) if archived else ProjectRow.archived_at.is_(None),
        ]
        cursor_filters = []
        if cursor:
            try:
                stamp, identifier = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                parsed = datetime.fromisoformat(stamp)
                if parsed.tzinfo is None or not isinstance(identifier, str):
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError) as exc:
                raise DomainError("VALIDATION_FAILED", "分页游标无效。", 422) from exc
            cursor_filters = [
                or_(
                    ProjectRow.created_at < parsed,
                    and_(ProjectRow.created_at == parsed, ProjectRow.id < identifier),
                )
            ]
        async with self.sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(ProjectRow).where(*filters)
            )
            rows = list(
                await session.scalars(
                    select(ProjectRow)
                    .where(*filters, *cursor_filters)
                    .order_by(ProjectRow.created_at.desc(), ProjectRow.id.desc())
                    .limit(limit + 1)
                )
            )
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                next_cursor = base64.urlsafe_b64encode(
                    json.dumps([last.created_at.isoformat(), last.id]).encode()
                ).decode()
            return ProjectPage(
                items=[project_dto(row) for row in rows[:limit]],
                total=total,
                next_cursor=next_cursor,
            )

    async def events(
        self, actor: ActorContext, project_id: str, after: int, limit: int
    ) -> EventPage:
        async with self.sessions() as session:
            row = await session.get(ProjectRow, (actor.tenant_id, project_id))
            if row is None:
                raise not_found()
            # Bound the page by the observed cursor; events committed later are read next time.
            upper = row.event_seq
            first_seq = await session.scalar(
                select(func.min(Event.seq)).where(
                    Event.tenant_id == actor.tenant_id, Event.project_id == project_id
                )
            )
            if after > upper or (first_seq is not None and after < first_seq - 1):
                raise DomainError("SNAPSHOT_REQUIRED", "事件游标已失效，请重新加载项目快照。", 409)
            rows = list(
                await session.scalars(
                    select(Event)
                    .where(
                        Event.tenant_id == actor.tenant_id,
                        Event.project_id == project_id,
                        Event.seq > after,
                        Event.seq <= upper,
                    )
                    .order_by(Event.seq)
                    .limit(limit + 1)
                )
            )
            selected = rows[:limit]
            if any(event.seq != after + index + 1 for index, event in enumerate(rows)) or (
                not rows and after < upper
            ):
                raise DomainError("SNAPSHOT_REQUIRED", "事件存在缺口，请重新加载快照。", 409)
            return EventPage(
                items=[
                    ProjectEvent(
                        event_id=event.id,
                        seq=event.seq,
                        type=event.type,
                        project_id=event.project_id,
                        row_version=event.row_version,
                        causation_command_id=event.causation_command_id,
                        occurred_at=event.occurred_at.isoformat(),
                    )
                    for event in selected
                ],
                next_cursor=selected[-1].seq if selected else after,
                has_more=len(rows) > limit,
            )
