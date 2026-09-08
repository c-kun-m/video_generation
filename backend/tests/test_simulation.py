from datetime import timedelta

from sqlalchemy import func, select
from test_content import prepared_project, start_body
from test_projects import BASE, new_id

from video_generation.application.simulation import SimulationService
from video_generation.infrastructure.persistence.models import (
    Command,
    Event,
    InboxRow,
    OutboxRow,
    ProductionRunRow,
    SimulationStepRow,
    utcnow,
)
from video_generation.infrastructure.persistence.outbox import OutboxRepository
from video_generation.orchestration.messages import ProductionInput, StepRequest


async def admitted_run(client, app):
    project, refs = await prepared_project(client)
    body = start_body(project, refs)
    response = await client.post(
        f"{BASE}/projects/{project['project_id']}/production-runs", json=body
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["business_result_ref"]["production_run_id"]
    async with app.state.sessions() as session:
        run = await session.get(ProductionRunRow, (project["tenant_id"], run_id))
        event = await session.scalar(select(OutboxRow).where(OutboxRow.run_id == run_id))
        execution = ProductionInput(
            project["tenant_id"], project["project_id"], run_id, run.snapshot_id, event.id, 1
        )
    return execution, body


async def control(client, execution, action):
    body = {"command_id": new_id(), "action": action}
    result = await client.post(f"{BASE}/production-runs/{execution.run_id}/commands", json=body)
    assert result.status_code == 202, result.text
    return body


async def test_activity_result_loss_does_not_duplicate_results_or_events(client, app):
    execution, body = await admitted_run(client, app)
    service = SimulationService(app.state.sessions)
    temporal_id = new_id()
    loaded = await service.transition(StepRequest(execution, "load", temporal_id))
    assert loaded.status == "PREPARING"
    assert (await client.get(f"{BASE}/commands/{body['command_id']}")).json()["status"] == "APPLIED"
    for shot_id in loaded.shot_ids:
        request = StepRequest(
            execution,
            "complete_step",
            temporal_id,
            operation_id=f"{execution.run_id}/shot/{shot_id}",
            shot_id=shot_id,
            stage="shot_collected",
        )
        original = await service.transition(request)
        replay = await SimulationService(app.state.sessions).transition(request)
        assert replay == original
    await service.transition(StepRequest(execution, "finish", temporal_id))
    await service.transition(StepRequest(execution, "finish", temporal_id))
    async with app.state.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SimulationStepRow)
                .where(SimulationStepRow.run_id == execution.run_id)
            )
            == 4
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.project_id == execution.project_id, Event.type == "run.step_completed")
            )
            == 3
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(InboxRow)
                .where(InboxRow.consumer == f"production/{execution.tenant_id}/{execution.run_id}")
            )
            == 1
        )


async def test_pause_collects_inflight_and_resume_preserves_snapshot(client, app):
    execution, _ = await admitted_run(client, app)
    service = SimulationService(app.state.sessions)
    temporal_id = new_id()
    loaded = await service.transition(StepRequest(execution, "load", temporal_id))
    pause = await control(client, execution, "pause")
    shot_id = loaded.shot_ids[0]
    state = await service.transition(
        StepRequest(
            execution,
            "complete_step",
            temporal_id,
            operation_id=f"{execution.run_id}/shot/{shot_id}",
            shot_id=shot_id,
        )
    )
    assert state.status == "PAUSED" and len(state.completed_operations) == 1
    assert (await client.get(f"{BASE}/commands/{pause['command_id']}")).json()[
        "status"
    ] == "APPLIED"
    paused = await service.transition(StepRequest(execution, "checkpoint", temporal_id))
    assert paused == state
    await control(client, execution, "resume")
    resumed = await service.transition(StepRequest(execution, "checkpoint", temporal_id))
    assert (
        resumed.status == "RENDERING" and resumed.completed_operations == state.completed_operations
    )


async def test_cancel_wins_before_completion_and_no_report(client, app):
    execution, _ = await admitted_run(client, app)
    service = SimulationService(app.state.sessions)
    temporal_id = new_id()
    loaded = await service.transition(StepRequest(execution, "load", temporal_id))
    cancel = await control(client, execution, "cancel")
    state = await service.transition(
        StepRequest(
            execution,
            "complete_step",
            temporal_id,
            operation_id=f"{execution.run_id}/shot/{loaded.shot_ids[0]}",
            shot_id=loaded.shot_ids[0],
        )
    )
    assert state.status == "CANCELLED" and not state.completed_operations
    assert (await client.get(f"{BASE}/commands/{cancel['command_id']}")).json()[
        "status"
    ] == "APPLIED"
    final = await service.transition(StepRequest(execution, "finish", temporal_id))
    assert final.status == "CANCELLED" and not final.completed_operations


async def test_completion_wins_before_cancel_and_control_order_is_recovered(client, app):
    execution, _ = await admitted_run(client, app)
    service = SimulationService(app.state.sessions)
    temporal_id = new_id()
    loaded = await service.transition(StepRequest(execution, "load", temporal_id))
    pause = await control(client, execution, "pause")
    resume = await control(client, execution, "resume")
    # Even if only the resume wake-up reaches the workflow, both commands are consumed in order.
    state = await service.transition(StepRequest(execution, "checkpoint", temporal_id))
    assert state.status == "RENDERING" and state.control_seq == 2
    for body in (pause, resume):
        assert (await client.get(f"{BASE}/commands/{body['command_id']}")).json()[
            "status"
        ] == "APPLIED"
    for shot_id in loaded.shot_ids:
        await service.transition(
            StepRequest(
                execution,
                "complete_step",
                temporal_id,
                operation_id=f"{execution.run_id}/shot/{shot_id}",
                shot_id=shot_id,
            )
        )
    assert (
        await service.transition(StepRequest(execution, "finish", temporal_id))
    ).status == "COMPLETED"
    late = await client.post(
        f"{BASE}/production-runs/{execution.run_id}/commands",
        json={"command_id": new_id(), "action": "cancel"},
    )
    assert late.json()["error"]["code"] == "RUN_TERMINAL"


async def test_outbox_lease_recovers_after_sender_crash_and_dead_letter_retained(client, app):
    execution, _ = await admitted_run(client, app)
    repo = OutboxRepository(app.state.sessions)
    first = await repo.claim(execution.run_id)
    assert first and first.attempts == 1
    assert await repo.claim(execution.run_id) is None
    async with app.state.sessions() as session, session.begin():
        row = await session.get(OutboxRow, (first.tenant_id, first.id))
        row.lease_until = utcnow() - timedelta(seconds=1)
    second = await repo.claim(execution.run_id)
    assert second.id == first.id and second.lease_token != first.lease_token
    await repo.finish(first)
    async with app.state.sessions() as session:
        row = await session.get(OutboxRow, (first.tenant_id, first.id))
        assert row.status == "PENDING" and row.lease_token == second.lease_token
    async with app.state.sessions() as session, session.begin():
        row = await session.get(OutboxRow, (first.tenant_id, first.id))
        row.created_at = utcnow() - timedelta(hours=25)
    await repo.finish(second, "TestDeliveryError")
    async with app.state.sessions() as session:
        row = await session.get(OutboxRow, (first.tenant_id, first.id))
        assert row.status == "DEAD" and row.error == "TestDeliveryError"
        command = await session.get(
            Command,
            (
                row.tenant_id,
                (await session.get(ProductionRunRow, (row.tenant_id, row.run_id))).start_actor_id,
                (await session.get(ProductionRunRow, (row.tenant_id, row.run_id))).start_command_id,
            ),
        )
        assert command.result["status"] == "ACCEPTED"
