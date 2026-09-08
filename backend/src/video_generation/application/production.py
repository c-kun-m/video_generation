from sqlalchemy import select

from video_generation.application.commands import CommandHandler, append_event
from video_generation.application.content import (
    check_upstream,
    get_project,
    read_approvals,
    resolve_ref,
    revision_dto,
)
from video_generation.contracts.content import (
    ControlProductionRun,
    OutboxDelivery,
    ProductionRun,
    ProductionRunDetail,
    ProductionSnapshot,
    RunRef,
    SimulationStep,
    StartProductionRun,
)
from video_generation.contracts.models import CommandResult
from video_generation.domain.content import canonical_digest, validate_complete
from video_generation.domain.errors import DomainError, not_found
from video_generation.infrastructure.persistence.models import (
    ContentHeadRow,
    InboxRow,
    OutboxRow,
    ProductionRunRow,
    ProductionSnapshotRow,
    ProjectRow,
    RunControlRow,
    SimulationStepRow,
    new_id,
    utcnow,
)

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def run_dto(row: ProductionRunRow) -> ProductionRun:
    return ProductionRun(
        production_run_id=row.id,
        project_id=row.project_id,
        snapshot_id=row.snapshot_id,
        execution_mode=row.execution_mode,
        workflow_id=row.workflow_id,
        temporal_run_id=row.temporal_run_id,
        status=row.status,
        stage=row.stage,
        pause_requested=row.pause_requested,
        row_version=row.row_version,
        control_seq=row.control_seq,
        completed_shots=row.completed_shots,
        total_shots=row.total_shots,
        error=row.error,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def run_ref(row: ProductionRunRow):
    return RunRef(production_run_id=row.id, snapshot_id=row.snapshot_id)


async def read_runs(session, tenant_id, project_id):
    return [
        run_dto(row)
        for row in await session.scalars(
            select(ProductionRunRow)
            .where(
                ProductionRunRow.tenant_id == tenant_id,
                ProductionRunRow.project_id == project_id,
            )
            .order_by(ProductionRunRow.created_at.desc())
            .limit(20)
        )
    ]


def enqueue(session, project, run, command_id, kind, payload=None):
    event = append_event(
        session,
        project,
        command_id,
        "run.created" if kind == "start" else "run.control_requested",
        run_ref(run),
        payload,
        run.row_version,
    )
    session.add(
        OutboxRow(
            tenant_id=project.tenant_id,
            id=event.id,
            run_id=run.id,
            kind=kind,
            payload={
                "event_id": event.id,
                "project_event_seq": event.seq,
                "snapshot_id": run.snapshot_id,
                "subject_ref": run_ref(run).model_dump(mode="json"),
                **(payload or {}),
            },
        )
    )
    return event


class ProductionService:
    def __init__(self, sessions):
        self.sessions = sessions
        self.commands = CommandHandler(sessions)

    async def start(self, actor, project_id, request: StartProductionRun):
        actor.require_editor()

        async def mutation(session):
            project = await get_project(session, actor.tenant_id, project_id, write=True)
            if project.row_version != request.expected_row_version:
                raise DomainError(
                    "VERSION_CONFLICT", "项目已变化，请重新核对。", 409, project.row_version
                )
            contents, approval_ids = [], []
            for kind in ("brief", "script", "storyboard"):
                ref = getattr(request.input_refs, kind)
                row = await resolve_ref(session, actor.tenant_id, project_id, ref)
                head = await session.get(ContentHeadRow, (actor.tenant_id, project_id, kind))
                if head is None or head.revision_id != row.id or head.review_status != "APPROVED":
                    raise DomainError(
                        "DEPENDENCY_NOT_READY", "请先批准当前需求、剧本和分镜版本。", 409
                    )
                content = revision_dto(row)
                upstream = await check_upstream(
                    session, actor.tenant_id, project_id, content.payload, current=True
                )
                validate_complete(content.payload, upstream)
                approvals = await read_approvals(
                    session, actor.tenant_id, project_id, row.id, limit=1
                )
                if not approvals or approvals[0].decision != "APPROVED":
                    raise DomainError("DEPENDENCY_NOT_READY", "批准记录缺失或已撤销。", 409)
                approval_ids.append(approvals[0].approval_id)
                contents.append(content)
            now, snapshot_id, run_id = utcnow(), new_id(), new_id()
            frozen = {
                "snapshot_id": snapshot_id,
                "project_id": project_id,
                "execution_mode": "simulation",
                "profile_ref": project.product_profile_ref,
                "schema_version": 1,
                "input_refs": request.input_refs.model_dump(mode="json"),
                "contents": [c.model_dump(mode="json") for c in contents],
                "approval_ids": approval_ids,
                "created_at": now.isoformat(),
            }
            snapshot = ProductionSnapshot(**frozen, digest=canonical_digest(frozen))
            session.add(
                ProductionSnapshotRow(
                    tenant_id=actor.tenant_id,
                    id=snapshot_id,
                    project_id=project_id,
                    data=snapshot.model_dump(mode="json"),
                    digest=snapshot.digest,
                    created_at=now,
                )
            )
            await session.flush()
            run = ProductionRunRow(
                tenant_id=actor.tenant_id,
                id=run_id,
                project_id=project_id,
                snapshot_id=snapshot_id,
                execution_mode="simulation",
                workflow_id=f"production/{actor.tenant_id}/{run_id}",
                status="CREATED",
                stage="waiting_for_worker",
                row_version=1,
                total_shots=len(contents[-1].payload.shots),
                start_actor_id=actor.actor_id,
                start_command_id=request.command_id,
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            await session.flush()
            enqueue(session, project, run, request.command_id, "start")
            return CommandResult(
                command_id=request.command_id, status="ACCEPTED", business_result_ref=run_ref(run)
            )

        return await self.commands.execute(
            actor,
            request.command_id,
            "run.start",
            {"project_id": project_id, **request.model_dump(mode="json")},
            mutation,
            202,
        )

    async def control(self, actor, run_id, request: ControlProductionRun):
        actor.require_editor()

        async def mutation(session):
            existing = await session.get(ProductionRunRow, (actor.tenant_id, run_id))
            if existing is None:
                raise not_found()
            # Controls remain available for runs whose project has since been archived.
            project = await session.get(
                ProjectRow, (actor.tenant_id, existing.project_id), with_for_update=True
            )
            run = await session.get(
                ProductionRunRow,
                (actor.tenant_id, run_id),
                with_for_update=True,
                populate_existing=True,
            )
            if run.status in TERMINAL:
                raise DomainError("RUN_TERMINAL", "批次已经结束，不能再控制。", 409)
            if run.status == "CANCEL_REQUESTED" and request.action != "cancel":
                raise DomainError("CANCEL_IN_PROGRESS", "取消已接受，不能再暂停或恢复。", 409)
            if request.action == "cancel":
                run.status = "CANCEL_REQUESTED"
                run.pause_requested = False
            elif request.action == "pause":
                run.pause_requested = True
            else:
                run.pause_requested = False
            run.control_seq += 1
            run.row_version += 1
            run.updated_at = utcnow()
            event = enqueue(
                session,
                project,
                run,
                request.command_id,
                "control",
                {"action": request.action, "control_seq": run.control_seq},
            )
            session.add(
                RunControlRow(
                    tenant_id=actor.tenant_id,
                    run_id=run_id,
                    seq=run.control_seq,
                    event_id=event.id,
                    actor_id=actor.actor_id,
                    command_id=request.command_id,
                    action=request.action,
                )
            )
            return CommandResult(
                command_id=request.command_id, status="ACCEPTED", business_result_ref=run_ref(run)
            )

        return await self.commands.execute(
            actor,
            request.command_id,
            "run.control",
            {"production_run_id": run_id, **request.model_dump(mode="json")},
            mutation,
            202,
        )

    async def detail(self, actor, run_id):
        async with self.sessions() as session:
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            run = await session.get(ProductionRunRow, (actor.tenant_id, run_id))
            if run is None:
                raise not_found()
            snapshot = await session.get(ProductionSnapshotRow, (actor.tenant_id, run.snapshot_id))
            steps = await session.scalars(
                select(SimulationStepRow)
                .where(
                    SimulationStepRow.tenant_id == actor.tenant_id,
                    SimulationStepRow.run_id == run_id,
                )
                .order_by(SimulationStepRow.completed_at, SimulationStepRow.operation_id)
            )
            return ProductionRunDetail(
                run=run_dto(run),
                snapshot=snapshot.data,
                deliveries=[
                    OutboxDelivery(
                        event_id=event.id,
                        kind=event.kind,
                        transport_status=event.status,
                        attempts=event.attempts,
                        error=event.error,
                        consumed=await session.get(
                            InboxRow, (actor.tenant_id, run.workflow_id, event.id)
                        )
                        is not None,
                    )
                    for event in await session.scalars(
                        select(OutboxRow)
                        .where(
                            OutboxRow.tenant_id == actor.tenant_id,
                            OutboxRow.run_id == run_id,
                        )
                        .order_by(OutboxRow.created_at)
                    )
                ],
                steps=[
                    SimulationStep(
                        operation_id=s.operation_id,
                        stage=s.stage,
                        shot_id=s.shot_id,
                        result=s.result,
                        completed_at=s.completed_at.isoformat(),
                    )
                    for s in steps
                ],
            )
