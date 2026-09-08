from sqlalchemy import select

from video_generation.application.commands import append_event
from video_generation.application.production import TERMINAL, run_ref
from video_generation.contracts.content import ProductionSnapshot
from video_generation.contracts.models import CommandResult
from video_generation.domain.content import canonical_digest
from video_generation.domain.errors import DomainError, not_found
from video_generation.infrastructure.persistence.models import (
    Command,
    InboxRow,
    ProductionRunRow,
    ProductionSnapshotRow,
    ProjectRow,
    RunControlRow,
    SimulationStepRow,
    utcnow,
)
from video_generation.orchestration.messages import StepRequest, StepResponse


class SimulationService:
    """Idempotent business transitions called by trusted worker Activities, never HTTP."""

    def __init__(self, sessions):
        self.sessions = sessions

    async def _ack(self, session, run, actor_id, command_id, event_id, result="APPLIED"):
        consumer = run.workflow_id
        if await session.get(InboxRow, (run.tenant_id, consumer, event_id)):
            return
        command = await session.get(
            Command, (run.tenant_id, actor_id, command_id), with_for_update=True
        )
        if command:
            stored = CommandResult.model_validate(command.result)
            if stored.status == "ACCEPTED":
                command.result = stored.model_copy(update={"status": result}).model_dump(
                    mode="json"
                )
                command.http_status = 200
        session.add(
            InboxRow(
                tenant_id=run.tenant_id,
                consumer=consumer,
                event_id=event_id,
                result={"status": result, "production_run_id": run.id},
            )
        )

    async def _consume_controls(self, session, run):
        # Notifications only wake the workflow. The database supplies every ordered command.
        controls = list(
            await session.scalars(
                select(RunControlRow)
                .where(
                    RunControlRow.tenant_id == run.tenant_id,
                    RunControlRow.run_id == run.id,
                    RunControlRow.seq > run.consumed_control_seq,
                )
                .order_by(RunControlRow.seq)
            )
        )
        for control in controls:
            if control.seq != run.consumed_control_seq + 1:
                raise DomainError("CONTROL_GAP", "制作控制记录存在缺口。", 409)
            await self._ack(session, run, control.actor_id, control.command_id, control.event_id)
            run.consumed_control_seq = control.seq

    async def transition(self, request: StepRequest) -> StepResponse:
        execution = request.execution
        async with self.sessions() as session, session.begin():
            # API commands and Activities always acquire project -> run locks in that order.
            project = await session.get(
                ProjectRow, (execution.tenant_id, execution.project_id), with_for_update=True
            )
            run = await session.get(
                ProductionRunRow, (execution.tenant_id, execution.run_id), with_for_update=True
            )
            if project is None or run is None or run.project_id != execution.project_id:
                raise not_found()
            if run.snapshot_id != execution.snapshot_id:
                raise DomainError("SNAPSHOT_CONFLICT", "Workflow 绑定的快照不匹配。", 409)
            snapshot_row = await session.get(
                ProductionSnapshotRow, (run.tenant_id, run.snapshot_id)
            )
            snapshot = ProductionSnapshot.model_validate(snapshot_row.data)
            if (
                canonical_digest(snapshot.model_dump(mode="json", exclude={"digest"}))
                != snapshot.digest
            ):
                raise DomainError("SNAPSHOT_CONFLICT", "冻结快照摘要校验失败。", 409)
            shot_ids = [
                s.shot_id
                for c in snapshot.contents
                if c.ref.entity_kind == "storyboard"
                for s in c.payload.shots
            ]
            before = (
                run.status,
                run.stage,
                run.temporal_run_id,
                run.consumed_control_seq,
                run.error,
            )
            saved_step = False
            run.temporal_run_id = request.temporal_run_id
            await self._ack(
                session, run, run.start_actor_id, run.start_command_id, execution.start_event_id
            )

            if run.status not in TERMINAL:
                # This Activity runs only at safe checkpoints. A workflow timer represents
                # the in-flight simulator; cancellation interrupts it before this transition.
                if run.status == "CANCEL_REQUESTED":
                    run.status = "CANCELLED"
                    run.stage = "cancelled"
                elif request.action == "fail":
                    run.status = "FAILED"
                    run.stage = "failed"
                    run.error = request.error or "模拟流程失败。"
                else:
                    if request.action == "complete_step":
                        if (
                            request.operation_id != f"{run.id}/shot/{request.shot_id}"
                            or request.shot_id not in shot_ids
                        ):
                            raise DomainError("INVALID_OPERATION", "镜头操作不属于冻结快照。", 409)
                        existing = await session.get(
                            SimulationStepRow, (run.tenant_id, run.id, request.operation_id)
                        )
                        if existing is None:
                            saved_step = True
                            session.add(
                                SimulationStepRow(
                                    tenant_id=run.tenant_id,
                                    run_id=run.id,
                                    operation_id=request.operation_id,
                                    stage="simulate_shot",
                                    shot_id=request.shot_id,
                                    result={
                                        "simulated": True,
                                        "shot_id": request.shot_id,
                                        "snapshot_digest": snapshot.digest,
                                    },
                                )
                            )
                            run.completed_shots += 1
                            append_event(
                                session,
                                project,
                                run.start_command_id,
                                "run.step_completed",
                                run_ref(run),
                                {"operation_id": request.operation_id, "shot_id": request.shot_id},
                                run.row_version + 1,
                            )
                    if run.pause_requested:
                        run.status = "PAUSED"
                        run.stage = "paused"
                    elif request.action == "finish":
                        if run.completed_shots != run.total_shots:
                            raise DomainError("DEPENDENCY_NOT_READY", "尚有模拟镜头未完成。", 409)
                        operation_id = f"{run.id}/report"
                        if (
                            await session.get(
                                SimulationStepRow, (run.tenant_id, run.id, operation_id)
                            )
                            is None
                        ):
                            session.add(
                                SimulationStepRow(
                                    tenant_id=run.tenant_id,
                                    run_id=run.id,
                                    operation_id=operation_id,
                                    stage="simulation_report",
                                    result={
                                        "simulated": True,
                                        "completed_shots": run.completed_shots,
                                        "snapshot_digest": snapshot.digest,
                                        "message": "模拟演练完成，未生成视频文件。",
                                    },
                                )
                            )
                        run.status = "COMPLETED"
                        run.stage = "completed"
                    else:
                        run.status = "PREPARING" if request.action == "load" else "RENDERING"
                        run.stage = request.stage or "snapshot_verified"
                await self._consume_controls(session, run)
            else:
                # A terminal result may have won the race before a notification arrived.
                await self._consume_controls(session, run)
            after = (
                run.status,
                run.stage,
                run.temporal_run_id,
                run.consumed_control_seq,
                run.error,
            )
            if after != before or saved_step:
                run.row_version += 1
                run.updated_at = utcnow()
                append_event(
                    session,
                    project,
                    run.start_command_id,
                    "run.updated",
                    run_ref(run),
                    {"status": run.status, "stage": run.stage},
                    run.row_version,
                )
            await session.flush()
            operations = list(
                await session.scalars(
                    select(SimulationStepRow.operation_id).where(
                        SimulationStepRow.tenant_id == run.tenant_id,
                        SimulationStepRow.run_id == run.id,
                    )
                )
            )
            return StepResponse(
                run.status, run.pause_requested, shot_ids, operations, run.control_seq
            )
