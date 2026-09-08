import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from video_generation.application.production import TERMINAL
from video_generation.application.simulation import SimulationService
from video_generation.config import Settings
from video_generation.infrastructure.persistence.database import create_database
from video_generation.infrastructure.persistence.models import (
    InboxRow,
    OutboxRow,
    ProductionRunRow,
    new_id,
    utcnow,
)
from video_generation.infrastructure.persistence.outbox import OutboxRepository, heartbeat
from video_generation.orchestration.messages import ProductionInput, StepRequest
from video_generation.orchestration.production import SimulationProductionWorkflow
from video_generation.workers.faults import crash_if_selected

log = logging.getLogger("video.dispatcher")


class OutboxDispatcher:
    def __init__(self, sessions, client: Client, settings: Settings):
        self.sessions = sessions
        self.client = client
        self.settings = settings
        self.outbox = OutboxRepository(sessions)

    async def deliver(self, event):
        async with self.sessions() as session:
            run = await session.get(ProductionRunRow, (event.tenant_id, event.run_id))
        if run is None or run.snapshot_id != event.payload["snapshot_id"]:
            raise ValueError("OUTBOX_BINDING_CONFLICT")
        if run.status in TERMINAL:
            return
        handle = self.client.get_workflow_handle(run.workflow_id)
        if event.kind == "start":
            execution = ProductionInput(
                run.tenant_id,
                run.project_id,
                run.id,
                run.snapshot_id,
                event.id,
                self.settings.simulation_step_seconds,
            )
            try:
                await self.client.start_workflow(
                    SimulationProductionWorkflow.run,
                    execution,
                    id=run.workflow_id,
                    task_queue=self.settings.temporal_task_queue,
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                    memo={
                        "tenant_id": run.tenant_id,
                        "production_run_id": run.id,
                        "snapshot_id": run.snapshot_id,
                    },
                    rpc_timeout=timedelta(seconds=5),
                )
            except WorkflowAlreadyStartedError:
                description = await handle.describe(rpc_timeout=timedelta(seconds=5))
                memo = await description.memo()
                if any(
                    memo.get(key) != value
                    for key, value in {
                        "tenant_id": run.tenant_id,
                        "production_run_id": run.id,
                        "snapshot_id": run.snapshot_id,
                    }.items()
                ):
                    raise ValueError("WORKFLOW_BINDING_CONFLICT") from None
        else:
            await handle.signal("business_event", event.payload, rpc_timeout=timedelta(seconds=5))

    async def dispatch_once(self, run_id=None):
        event = await self.outbox.claim(run_id)
        if event is None:
            return False
        try:
            await self.deliver(event)
        except Exception as exc:
            # Do not log connection strings or provider response bodies.
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            await self.outbox.finish(event, reason)
            log.warning(
                "outbox_delivery_failed event=%s run=%s reason=%s", event.id, event.run_id, reason
            )
        else:
            crash_if_selected(self.settings, "outbox_after_send", event.run_id)
            await self.outbox.finish(event)
        return True

    async def reconcile(self):
        # Re-notify deliveries that have no business receipt. A signal ACK isn't consumption.
        async with self.sessions() as session, session.begin():
            rows = list(
                await session.scalars(
                    select(OutboxRow)
                    .join(
                        ProductionRunRow,
                        (ProductionRunRow.tenant_id == OutboxRow.tenant_id)
                        & (ProductionRunRow.id == OutboxRow.run_id),
                    )
                    .where(
                        OutboxRow.status == "SENT",
                        OutboxRow.delivered_at < utcnow() - timedelta(seconds=30),
                        ProductionRunRow.status.not_in(TERMINAL),
                        ~select(InboxRow.event_id)
                        .where(
                            InboxRow.tenant_id == OutboxRow.tenant_id,
                            InboxRow.event_id == OutboxRow.id,
                            InboxRow.consumer == ProductionRunRow.workflow_id,
                        )
                        .exists(),
                    )
                    .order_by(OutboxRow.delivered_at)
                    .limit(100)
                )
            )
            for event in rows:
                run = await session.get(ProductionRunRow, (event.tenant_id, event.run_id))
                if run.status not in TERMINAL and not await session.get(
                    InboxRow, (event.tenant_id, run.workflow_id, event.id)
                ):
                    event.status = "PENDING"
                    event.available_at = utcnow()

        async with self.sessions() as session:
            runs = list(
                await session.scalars(
                    select(ProductionRunRow)
                    .where(
                        ProductionRunRow.status.not_in(TERMINAL),
                        ProductionRunRow.temporal_run_id.is_not(None),
                    )
                    .order_by(ProductionRunRow.updated_at)
                    .limit(100)
                )
            )
        for run in runs:
            reason = None
            try:
                description = await self.client.get_workflow_handle(run.workflow_id).describe(
                    rpc_timeout=timedelta(seconds=5)
                )
                if description.status != WorkflowExecutionStatus.RUNNING:
                    reason = "编排已结束但业务状态未结束，请查看 Temporal 历史。"
            except RPCError as exc:
                if exc.status == RPCStatusCode.NOT_FOUND:
                    reason = "已启动的编排历史不存在，需检查 Temporal 持久化服务。"
                else:
                    continue
            if reason:
                async with self.sessions() as session:
                    event = await session.scalar(
                        select(OutboxRow).where(
                            OutboxRow.tenant_id == run.tenant_id,
                            OutboxRow.run_id == run.id,
                            OutboxRow.kind == "start",
                        )
                    )
                if event:
                    await SimulationService(self.sessions).transition(
                        StepRequest(
                            ProductionInput(
                                run.tenant_id, run.project_id, run.id, run.snapshot_id, event.id
                            ),
                            "fail",
                            run.temporal_run_id,
                            error=reason,
                        )
                    )


async def run_dispatcher(settings=None):
    settings = settings or Settings()
    engine, sessions = create_database(settings)
    instance_id = new_id()
    try:
        while True:
            try:
                client = await Client.connect(
                    settings.temporal_address, namespace=settings.temporal_namespace
                )
                dispatcher = OutboxDispatcher(sessions, client, settings)
                next_maintenance = 0
                while True:
                    now = asyncio.get_running_loop().time()
                    if now >= next_maintenance:
                        await dispatcher.reconcile()
                        await heartbeat(sessions, "dispatcher", instance_id)
                        next_maintenance = now + 10
                    handled = await dispatcher.dispatch_once()
                    if not handled:
                        await asyncio.sleep(settings.outbox_poll_seconds)
            except (RPCError, RuntimeError, OSError, SQLAlchemyError) as exc:
                log.warning("dispatcher_connection_retry reason=%s", type(exc).__name__)
                await asyncio.sleep(5)
    finally:
        await engine.dispose()
