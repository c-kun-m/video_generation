import asyncio
from datetime import timedelta

import pytest
from google.protobuf.duration_pb2 import Duration
from temporalio.api.workflowservice.v1 import RegisterNamespaceRequest
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Replayer, Worker
from test_projects import BASE, new_id
from test_simulation import admitted_run, control

from video_generation.config import Settings
from video_generation.infrastructure.persistence.models import OutboxRow, ProductionRunRow, utcnow
from video_generation.orchestration.activities import ProductionActivities
from video_generation.orchestration.production import SimulationProductionWorkflow
from video_generation.workers.dispatcher import OutboxDispatcher


@pytest.fixture
async def temporal_client():
    settings = Settings()
    client = await Client.connect(settings.temporal_address, namespace="video-tests")
    try:
        await client.workflow_service.register_namespace(
            RegisterNamespaceRequest(
                namespace="video-tests",
                workflow_execution_retention_period=Duration(seconds=86400),
            )
        )
    except RPCError as exc:
        if exc.status != RPCStatusCode.ALREADY_EXISTS:
            raise
    return client


def make_worker(client, app, queue):
    return Worker(
        client,
        task_queue=queue,
        workflows=[SimulationProductionWorkflow],
        activities=[ProductionActivities(app.state.sessions).transition],
    )


async def await_state(client, run_id, predicate, seconds=30):
    async with asyncio.timeout(seconds):
        while True:
            response = await client.get(f"{BASE}/production-runs/{run_id}")
            assert response.status_code == 200, response.text
            detail = response.json()
            if predicate(detail):
                return detail
            await asyncio.sleep(0.1)


async def test_real_temporal_delivery_crash_replay_and_snapshot_binding(
    client, app, temporal_client
):
    execution, _ = await admitted_run(client, app)
    settings = Settings(temporal_task_queue="test-" + new_id(), simulation_step_seconds=1)
    dispatcher = OutboxDispatcher(app.state.sessions, temporal_client, settings)
    event = await dispatcher.outbox.claim(execution.run_id)
    # A sender crash after delivery leaves the lease unacknowledged.
    await dispatcher.deliver(event)
    workflow_id = f"production/{execution.tenant_id}/{execution.run_id}"
    handle = temporal_client.get_workflow_handle(workflow_id)
    original = await handle.describe()
    async with app.state.sessions() as session, session.begin():
        row = await session.get(OutboxRow, (event.tenant_id, event.id))
        row.lease_until = utcnow() - timedelta(seconds=1)
    await dispatcher.dispatch_once(execution.run_id)
    assert (await handle.describe()).run_id == original.run_id
    async with make_worker(temporal_client, app, settings.temporal_task_queue):
        assert await asyncio.wait_for(handle.result(), 45) == "COMPLETED"
    detail = await await_state(
        client, execution.run_id, lambda d: d["run"]["status"] == "COMPLETED"
    )
    assert len(detail["steps"]) == 4 and detail["run"]["completed_shots"] == 3
    await Replayer(workflows=[SimulationProductionWorkflow]).replay_workflow(
        await handle.fetch_history()
    )
    await dispatcher.deliver(event)
    assert (await handle.describe()).run_id == original.run_id


async def test_worker_restart_pause_resume_and_cancel_on_persistent_server(
    client, app, temporal_client
):
    execution, _ = await admitted_run(client, app)
    settings = Settings(temporal_task_queue="test-" + new_id(), simulation_step_seconds=3)
    dispatcher = OutboxDispatcher(app.state.sessions, temporal_client, settings)
    await dispatcher.dispatch_once(execution.run_id)
    workflow_id = f"production/{execution.tenant_id}/{execution.run_id}"
    async with make_worker(temporal_client, app, settings.temporal_task_queue):
        await await_state(
            client, execution.run_id, lambda d: d["run"]["stage"].startswith("simulate_shot:")
        )
        await control(client, execution, "pause")
        await dispatcher.dispatch_once(execution.run_id)
        paused = await await_state(
            client, execution.run_id, lambda d: d["run"]["status"] == "PAUSED"
        )
        assert paused["run"]["completed_shots"] == 1
    async with app.state.sessions() as session:
        run = await session.get(ProductionRunRow, (execution.tenant_id, execution.run_id))
        old_temporal_run_id = run.temporal_run_id
    # New Worker instance has no in-memory workflow state; it replays the persisted history.
    async with make_worker(temporal_client, app, settings.temporal_task_queue):
        await control(client, execution, "resume")
        await dispatcher.dispatch_once(execution.run_id)
        resumed = await await_state(
            client, execution.run_id, lambda d: d["run"]["stage"].startswith("simulate_shot:")
        )
        assert resumed["run"]["completed_shots"] == 1
        await control(client, execution, "cancel")
        await dispatcher.dispatch_once(execution.run_id)
        assert (
            await asyncio.wait_for(temporal_client.get_workflow_handle(workflow_id).result(), 45)
            == "CANCELLED"
        )
    final = await await_state(client, execution.run_id, lambda d: d["run"]["status"] == "CANCELLED")
    assert final["run"]["temporal_run_id"] == old_temporal_run_id
    assert not any(step["stage"] == "simulation_report" for step in final["steps"])
    assert final["run"]["snapshot_id"] == execution.snapshot_id
