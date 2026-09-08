from sqlalchemy import select

from video_generation.application.commands import CommandHandler, append_event
from video_generation.contracts.content import (
    Approval,
    ApprovalPage,
    ApprovalRef,
    ContentHead,
    ContentRef,
    ContentRevision,
    RevisionPage,
    SaveRevision,
    ScriptContent,
    StoryboardContent,
    SubmitApproval,
)
from video_generation.contracts.models import CommandResult
from video_generation.domain.content import canonical_digest, validate_complete, validate_structure
from video_generation.domain.errors import DomainError, not_found
from video_generation.infrastructure.persistence.models import (
    ApprovalRow,
    ContentHeadRow,
    ContentRevisionRow,
    ProjectRow,
    new_id,
    utcnow,
)


def revision_dto(row: ContentRevisionRow) -> ContentRevision:
    return ContentRevision(
        ref=ContentRef(entity_kind=row.entity_kind, revision_id=row.id, digest=row.digest),
        project_id=row.project_id,
        revision=row.revision,
        schema_version=row.schema_version,
        parent_revision_id=row.parent_revision_id,
        payload=row.payload,
        created_by=row.created_by,
        created_at=row.created_at.isoformat(),
    )


def approval_dto(row: ApprovalRow) -> Approval:
    return Approval(
        approval_id=row.id,
        project_id=row.project_id,
        subject_ref=row.subject_ref,
        decision=row.decision,
        policy_version=row.policy_version,
        comment=row.comment,
        actor_id=row.actor_id,
        command_id=row.command_id,
        created_at=row.created_at.isoformat(),
    )


async def get_project(session, tenant_id, project_id, *, write=False):
    project = await session.get(ProjectRow, (tenant_id, project_id), with_for_update=write)
    if project is None:
        raise not_found()
    if write and project.archived_at:
        raise DomainError("PROJECT_ARCHIVED", "请先恢复项目，再进行内容或制作操作。", 409)
    return project


async def resolve_ref(session, tenant_id, project_id, ref: ContentRef):
    row = await session.get(ContentRevisionRow, (tenant_id, ref.revision_id))
    if row is None or row.project_id != project_id:
        raise not_found()
    if row.entity_kind != ref.entity_kind or row.digest != ref.digest:
        raise DomainError("VERSION_CONFLICT", "内容引用与实际版本摘要不匹配。", 409)
    return row


def upstream_ref(payload):
    if isinstance(payload, ScriptContent):
        return payload.brief_ref
    if isinstance(payload, StoryboardContent):
        return payload.script_ref
    return None


async def check_upstream(session, tenant_id, project_id, payload, *, current=False):
    ref = upstream_ref(payload)
    if ref is None:
        return None
    row = await resolve_ref(session, tenant_id, project_id, ref)
    if current:
        head = await session.get(ContentHeadRow, (tenant_id, project_id, ref.entity_kind))
        if head is None or head.revision_id != ref.revision_id:
            raise DomainError("DEPENDENCY_NOT_READY", "上游内容已经更新，请重新关联当前版本。", 409)
    upstream = revision_dto(row).payload
    if current:
        await check_upstream(session, tenant_id, project_id, upstream, current=True)
    return upstream


async def read_heads(session, tenant_id, project_id) -> list[ContentHead]:
    rows = list(
        await session.scalars(
            select(ContentHeadRow).where(
                ContentHeadRow.tenant_id == tenant_id,
                ContentHeadRow.project_id == project_id,
            )
        )
    )
    result = []
    for head in sorted(rows, key=lambda h: ("brief", "script", "storyboard").index(h.entity_kind)):
        current = revision_dto(await session.get(ContentRevisionRow, (tenant_id, head.revision_id)))
        outdated = False
        try:
            await check_upstream(session, tenant_id, project_id, current.payload, current=True)
        except DomainError:
            outdated = True
        result.append(
            ContentHead(
                entity_kind=head.entity_kind,
                row_version=head.row_version,
                current=current,
                review_status=head.review_status,
                upstream_outdated=outdated,
            )
        )
    return result


async def read_approvals(session, tenant_id, project_id, revision_id=None, limit=100):
    query = select(ApprovalRow).where(
        ApprovalRow.tenant_id == tenant_id,
        ApprovalRow.project_id == project_id,
    )
    if revision_id:
        query = query.where(ApprovalRow.revision_id == revision_id)
    return [
        approval_dto(r)
        for r in await session.scalars(
            query.order_by(ApprovalRow.created_at.desc(), ApprovalRow.id.desc()).limit(limit)
        )
    ]


class ContentService:
    def __init__(self, sessions):
        self.sessions = sessions
        self.commands = CommandHandler(sessions)

    async def save(self, actor, project_id: str, request: SaveRevision):
        actor.require_editor()

        async def mutation(session):
            project = await get_project(session, actor.tenant_id, project_id, write=True)
            head = await session.get(
                ContentHeadRow, (actor.tenant_id, project_id, request.entity_kind)
            )
            version = head.row_version if head else 0
            if version != request.expected_row_version:
                raise DomainError(
                    "VERSION_CONFLICT", "内容已更新，请比较最新版本后再保存。", 409, version
                )
            validate_structure(request.payload)
            await check_upstream(session, actor.tenant_id, project_id, request.payload)
            previous = (
                await session.get(ContentRevisionRow, (actor.tenant_id, head.revision_id))
                if head
                else None
            )
            payload = request.payload.model_dump(mode="json")
            revision = ContentRevisionRow(
                tenant_id=actor.tenant_id,
                id=new_id(),
                project_id=project_id,
                entity_kind=request.entity_kind,
                revision=previous.revision + 1 if previous else 1,
                schema_version=1,
                parent_revision_id=previous.id if previous else None,
                payload=payload,
                digest=canonical_digest({"schema_version": 1, "payload": payload}),
                created_by=actor.actor_id,
                created_at=utcnow(),
            )
            session.add(revision)
            await session.flush()
            if head is None:
                head = ContentHeadRow(
                    tenant_id=actor.tenant_id,
                    project_id=project_id,
                    entity_kind=request.entity_kind,
                )
                session.add(head)
            head.revision_id = revision.id
            head.row_version = version + 1
            head.review_status = "DRAFT"
            ref = revision_dto(revision).ref
            append_event(
                session,
                project,
                request.command_id,
                "content.saved",
                ref,
                {"revision": revision.revision},
                head.row_version,
            )
            return CommandResult(
                command_id=request.command_id, status="APPLIED", business_result_ref=ref
            )

        return await self.commands.execute(
            actor,
            request.command_id,
            "content.save",
            {"project_id": project_id, **request.model_dump(mode="json")},
            mutation,
            201,
        )

    async def history(self, actor, project_id, entity_kind, before=None, limit=30):
        async with self.sessions() as session:
            await get_project(session, actor.tenant_id, project_id)
            query = select(ContentRevisionRow).where(
                ContentRevisionRow.tenant_id == actor.tenant_id,
                ContentRevisionRow.project_id == project_id,
                ContentRevisionRow.entity_kind == entity_kind,
            )
            if before:
                query = query.where(ContentRevisionRow.revision < before)
            rows = list(
                await session.scalars(
                    query.order_by(ContentRevisionRow.revision.desc()).limit(limit + 1)
                )
            )
            return RevisionPage(
                items=[revision_dto(r) for r in rows[:limit]],
                next_before=rows[limit - 1].revision if len(rows) > limit else None,
            )

    async def approve(self, actor, project_id, request: SubmitApproval):
        actor.require_reviewer()

        async def mutation(session):
            project = await get_project(session, actor.tenant_id, project_id, write=True)
            row = await resolve_ref(session, actor.tenant_id, project_id, request.subject_ref)
            head = await session.get(ContentHeadRow, (actor.tenant_id, project_id, row.entity_kind))
            if head is None or head.revision_id != row.id:
                raise DomainError(
                    "STALE_REVIEW",
                    "当前内容版本已变化，请重新查看后审批。",
                    409,
                    head.row_version if head else 0,
                )
            if head.row_version != request.expected_row_version:
                raise DomainError(
                    "STALE_REVIEW", "内容或审批已变化，请重新核对。", 409, head.row_version
                )
            if request.decision == "APPROVED":
                payload = revision_dto(row).payload
                upstream = await check_upstream(
                    session, actor.tenant_id, project_id, payload, current=True
                )
                validate_complete(payload, upstream)
            if request.decision == "REVOKED" and head.review_status != "APPROVED":
                raise DomainError("VALIDATION_FAILED", "只有当前有效批准可以撤销。", 409)
            approval = ApprovalRow(
                tenant_id=actor.tenant_id,
                id=new_id(),
                project_id=project_id,
                revision_id=row.id,
                subject_ref=request.subject_ref.model_dump(mode="json"),
                decision=request.decision,
                policy_version="manual-content/v1",
                comment=request.comment,
                actor_id=actor.actor_id,
                command_id=request.command_id,
                created_at=utcnow(),
            )
            session.add(approval)
            head.row_version += 1
            head.review_status = request.decision
            ref = ApprovalRef(approval_id=approval.id)
            append_event(
                session,
                project,
                request.command_id,
                "content.reviewed",
                ref,
                {
                    "subject_ref": request.subject_ref.model_dump(mode="json"),
                    "decision": request.decision,
                },
                head.row_version,
            )
            return CommandResult(
                command_id=request.command_id, status="APPLIED", business_result_ref=ref
            )

        return await self.commands.execute(
            actor,
            request.command_id,
            "content.approve",
            {"project_id": project_id, **request.model_dump(mode="json")},
            mutation,
            201,
        )

    async def approvals(self, actor, project_id, revision_id=None):
        async with self.sessions() as session:
            await get_project(session, actor.tenant_id, project_id)
            return ApprovalPage(
                items=await read_approvals(session, actor.tenant_id, project_id, revision_id)
            )
