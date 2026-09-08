import base64
import json
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import and_, func, or_, select

from video_generation.application.auth import ActorContext
from video_generation.application.commands import CommandHandler, append_event
from video_generation.application.content import read_approvals, read_heads
from video_generation.application.production import read_runs
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
from video_generation.domain.errors import DomainError, not_found
from video_generation.infrastructure.persistence.models import Event, ProjectRow, new_id, utcnow


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

        async def apply(session):
            project = await mutation(session)
            return CommandResult(
                command_id=command_id,
                status="APPLIED",
                business_result_ref=ProjectRef(project_id=project.id),
                project=project_dto(project),
            )

        return await CommandHandler(self.sessions).execute(
            actor, command_id, action, payload, apply, success_status
        )

    _event = staticmethod(append_event)

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
        return await CommandHandler(self.sessions).get(actor, command_id)

    async def snapshot(self, actor: ActorContext, project_id: str) -> ProjectSnapshot:
        async with self.sessions() as session:
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            row = await session.get(ProjectRow, (actor.tenant_id, project_id))
            if row is None:
                raise not_found()
            return ProjectSnapshot(
                project=project_dto(row),
                event_cursor=row.event_seq,
                contents=await read_heads(session, actor.tenant_id, project_id),
                approvals=await read_approvals(session, actor.tenant_id, project_id),
                production_runs=await read_runs(session, actor.tenant_id, project_id),
            )

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
                        subject_ref=event.subject_ref,
                        payload=event.payload,
                    )
                    for event in selected
                ],
                next_cursor=selected[-1].seq if selected else after,
                has_more=len(rows) > limit,
            )
