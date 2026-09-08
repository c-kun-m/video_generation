import asyncio

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_projects import BASE, create, second_identity

from video_generation.infrastructure.persistence.models import (
    ApprovalRow,
    ContentRevisionRow,
    OutboxRow,
    ProductionRunRow,
    ProductionSnapshotRow,
    new_id,
)


async def snapshot(client, project_id):
    result = await client.get(f"{BASE}/projects/{project_id}/snapshot")
    assert result.status_code == 200, result.text
    return result.json()


async def save(client, project_id, payload, version=0):
    result = await client.post(
        f"{BASE}/projects/{project_id}/revisions",
        json={
            "command_id": new_id(),
            "entity_kind": payload["kind"],
            "expected_row_version": version,
            "payload": payload,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()["business_result_ref"]


async def approve(client, project_id, kind, decision="APPROVED", headers=None):
    head = next(
        h for h in (await snapshot(client, project_id))["contents"] if h["entity_kind"] == kind
    )
    return await client.post(
        f"{BASE}/projects/{project_id}/approvals",
        headers=headers,
        json={
            "command_id": new_id(),
            "subject_ref": head["current"]["ref"],
            "expected_row_version": head["row_version"],
            "decision": decision,
        },
    )


async def prepared_project(client):
    project, _ = await create(client, "版本审批与演练")
    pid = project["project_id"]
    brief = await save(
        client,
        pid,
        {
            "kind": "brief",
            "theme": "城市晨光",
            "audience": "城市居民",
            "purpose": "展示早晨生活",
            "style": "温暖写实",
        },
    )
    segment_id = new_id()
    script = await save(
        client,
        pid,
        {
            "kind": "script",
            "brief_ref": brief,
            "segments": [
                {
                    "segment_id": segment_id,
                    "spoken_text": "清晨，城市慢慢醒来。",
                    "visual_description": "阳光照进街道",
                },
            ],
        },
    )
    storyboard = await save(
        client,
        pid,
        {
            "kind": "storyboard",
            "script_ref": script,
            "shots": [
                {
                    "shot_id": new_id(),
                    "segment_ids": [segment_id],
                    "intent": f"晨光镜头 {i + 1}",
                    "camera": "缓慢推进",
                    "duration_frames": 240,
                }
                for i in range(3)
            ],
        },
    )
    for kind in ("brief", "script", "storyboard"):
        response = await approve(client, pid, kind)
        assert response.status_code == 201, response.text
    return project, {"brief": brief, "script": script, "storyboard": storyboard}


def start_body(project, refs):
    return {
        "command_id": new_id(),
        "execution_mode": "simulation",
        "input_refs": refs,
        "expected_row_version": project["row_version"],
    }


async def test_content_revisions_concurrent_edits_and_event_order(client):
    project, _ = await create(client)
    pid = project["project_id"]
    payload = {"kind": "brief", "theme": "初稿"}
    ref = await save(client, pid, payload)
    responses = await asyncio.gather(
        *[
            client.post(
                f"{BASE}/projects/{pid}/revisions",
                json={
                    "command_id": new_id(),
                    "entity_kind": "brief",
                    "expected_row_version": 1,
                    "payload": {**payload, "theme": title},
                },
            )
            for title in ("新稿甲", "新稿乙")
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    view = await snapshot(client, pid)
    assert view["project"]["row_version"] == 1
    assert view["contents"][0]["current"]["revision"] == 2
    assert view["contents"][0]["current"]["parent_revision_id"] == ref["revision_id"]
    assert view["contents"][0]["review_status"] == "DRAFT"
    history = (
        await client.get(f"{BASE}/projects/{pid}/revisions?entity_kind=brief&limit=1")
    ).json()
    assert history["next_before"] == 2
    old = (await client.get(f"{BASE}/projects/{pid}/revisions?entity_kind=brief&before=2")).json()
    assert old["items"][0]["ref"] == ref
    events = (await client.get(f"{BASE}/projects/{pid}/events")).json()["items"]
    assert [e["seq"] for e in events] == [1, 2, 3]
    assert events[-1]["type"] == "content.saved"


async def test_incomplete_draft_is_saved_but_approval_rejected(client):
    project, _ = await create(client)
    await save(client, project["project_id"], {"kind": "brief"})
    response = await approve(client, project["project_id"], "brief")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_twenty_start_commands_one_snapshot_run_outbox(client, app):
    project, refs = await prepared_project(client)
    pid = project["project_id"]
    body = start_body(project, refs)
    replies = await asyncio.gather(
        *[client.post(f"{BASE}/projects/{pid}/production-runs", json=body) for _ in range(20)]
    )
    assert all(r.status_code == 202 for r in replies), [r.text for r in replies]
    assert all(r.json() == replies[0].json() for r in replies)
    result_ref = replies[0].json()["business_result_ref"]
    async with app.state.sessions() as session:
        for model in (ProductionRunRow, ProductionSnapshotRow):
            count = await session.scalar(
                select(func.count()).select_from(model).where(model.project_id == pid)
            )
            assert count == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OutboxRow)
                .where(OutboxRow.run_id == result_ref["production_run_id"])
            )
            == 1
        )
    duplicate = await client.post(
        f"{BASE}/projects/{pid}/production-runs", json={**body, "expected_row_version": 2}
    )
    assert duplicate.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    stored = (await client.get(f"{BASE}/commands/{body['command_id']}")).json()
    assert stored["status"] == "ACCEPTED"
    detail = (await client.get(f"{BASE}/production-runs/{result_ref['production_run_id']}")).json()
    assert detail["snapshot"]["input_refs"] == refs
    assert detail["run"]["total_shots"] == 3
    assert len(detail["snapshot"]["approval_ids"]) == 3


async def test_new_revision_does_not_inherit_approval_or_mutate_snapshot(client):
    project, refs = await prepared_project(client)
    pid = project["project_id"]
    first = await client.post(
        f"{BASE}/projects/{pid}/production-runs", json=start_body(project, refs)
    )
    assert first.status_code == 202, first.text
    run_id = first.json()["business_result_ref"]["production_run_id"]
    old = (await snapshot(client, pid))["contents"][2]
    changed = dict(old["current"]["payload"])
    changed["shots"][0]["intent"] = "新的镜头描述"
    new_ref = await save(client, pid, changed, old["row_version"])
    rejected = await client.post(
        f"{BASE}/projects/{pid}/production-runs",
        json=start_body(project, {**refs, "storyboard": new_ref}),
    )
    assert rejected.json()["error"]["code"] == "DEPENDENCY_NOT_READY"
    stale = await client.post(
        f"{BASE}/projects/{pid}/approvals",
        json={
            "command_id": new_id(),
            "subject_ref": refs["storyboard"],
            "expected_row_version": old["row_version"],
            "decision": "APPROVED",
        },
    )
    assert stale.json()["error"]["code"] == "STALE_REVIEW"
    history = (
        await client.get(
            f"{BASE}/projects/{pid}/approvals",
            params={"revision_id": refs["storyboard"]["revision_id"]},
        )
    ).json()
    assert history["items"][0]["decision"] == "APPROVED"
    detail = (await client.get(f"{BASE}/production-runs/{run_id}")).json()
    assert detail["snapshot"]["input_refs"] == refs
    assert (
        detail["snapshot"]["contents"][2]["payload"]["shots"][0]["intent"]
        != changed["shots"][0]["intent"]
    )


async def test_upstream_change_is_visible_and_blocks_new_start(client):
    project, refs = await prepared_project(client)
    pid = project["project_id"]
    brief = (await snapshot(client, pid))["contents"][0]
    new_ref = await save(
        client, pid, {**brief["current"]["payload"], "theme": "新主题"}, brief["row_version"]
    )
    assert (await approve(client, pid, "brief")).status_code == 201
    view = await snapshot(client, pid)
    assert all(h["upstream_outdated"] for h in view["contents"][1:])
    start = await client.post(
        f"{BASE}/projects/{pid}/production-runs",
        json=start_body(project, {**refs, "brief": new_ref}),
    )
    assert start.json()["error"]["code"] == "DEPENDENCY_NOT_READY"


async def test_approval_revocation_and_role_tenant_boundaries(client, app):
    project, refs = await prepared_project(client)
    pid = project["project_id"]
    editor = await second_identity(app, tenant_id=project["tenant_id"], role="editor")
    assert (await approve(client, pid, "brief", headers=editor)).status_code == 403
    reviewer = await second_identity(app, tenant_id=project["tenant_id"], role="reviewer")
    assert (await approve(client, pid, "brief", "REVOKED", reviewer)).status_code == 201
    start = await client.post(
        f"{BASE}/projects/{pid}/production-runs", json=start_body(project, refs)
    )
    assert start.status_code == 409
    assert (
        await client.post(
            f"{BASE}/projects/{pid}/production-runs",
            headers=reviewer,
            json=start_body(project, refs),
        )
    ).status_code == 403
    outsider = await second_identity(app)
    assert (
        await client.get(f"{BASE}/projects/{pid}/revisions?entity_kind=brief", headers=outsider)
    ).status_code == 404
    other, _ = await create(client, "另一项目")
    wrong_ref = await client.post(
        f"{BASE}/projects/{other['project_id']}/revisions",
        json={
            "command_id": new_id(),
            "entity_kind": "script",
            "expected_row_version": 0,
            "payload": {"kind": "script", "brief_ref": refs["brief"]},
        },
    )
    assert wrong_ref.status_code == 404


async def test_database_rejects_revision_approval_and_snapshot_rewrite(client, app):
    project, refs = await prepared_project(client)
    response = await client.post(
        f"{BASE}/projects/{project['project_id']}/production-runs", json=start_body(project, refs)
    )
    assert response.status_code == 202, response.text
    for table in (
        ContentRevisionRow.__tablename__,
        ApprovalRow.__tablename__,
        ProductionSnapshotRow.__tablename__,
    ):
        async with app.state.sessions() as session, session.begin():
            with pytest.raises(DBAPIError, match="immutable record"):
                async with session.begin_nested():
                    await session.execute(
                        text(f"UPDATE {table} SET project_id = project_id WHERE project_id = :pid"),
                        {"pid": project["project_id"]},
                    )


async def test_run_control_admission_is_durable_and_cancel_irreversible(client):
    project, refs = await prepared_project(client)
    response = await client.post(
        f"{BASE}/projects/{project['project_id']}/production-runs", json=start_body(project, refs)
    )
    run_id = response.json()["business_result_ref"]["production_run_id"]
    for action in ("pause", "resume", "cancel"):
        body = {"command_id": new_id(), "action": action}
        response = await client.post(f"{BASE}/production-runs/{run_id}/commands", json=body)
        assert response.status_code == 202, response.text
        assert (
            await client.post(f"{BASE}/production-runs/{run_id}/commands", json=body)
        ).json() == response.json()
    detail = (await client.get(f"{BASE}/production-runs/{run_id}")).json()
    assert detail["run"]["status"] == "CANCEL_REQUESTED"
    assert detail["run"]["control_seq"] == 3
    resume = await client.post(
        f"{BASE}/production-runs/{run_id}/commands",
        json={"command_id": new_id(), "action": "resume"},
    )
    assert resume.json()["error"]["code"] == "CANCEL_IN_PROGRESS"


async def test_snapshot_cannot_mix_content_with_an_older_event_cursor(client, monkeypatch):
    from video_generation.application import projects

    project, _ = await create(client)
    pid = project["project_id"]
    first = await save(client, pid, {"kind": "brief", "theme": "snapshot input"})
    before = await snapshot(client, pid)
    original = projects.read_heads

    async def write_between_snapshot_queries(session, tenant_id, project_id):
        # Commit a new version after the snapshot read its project/cursor, before it reads heads.
        await save(client, pid, {"kind": "brief", "theme": "concurrent update"}, 1)
        return await original(session, tenant_id, project_id)

    monkeypatch.setattr(projects, "read_heads", write_between_snapshot_queries)
    during = await snapshot(client, pid)
    monkeypatch.setattr(projects, "read_heads", original)
    after = await snapshot(client, pid)
    assert during["contents"][0]["current"]["ref"] == first
    assert during["event_cursor"] == before["event_cursor"]
    assert after["contents"][0]["current"]["revision"] == 2
    assert after["event_cursor"] == before["event_cursor"] + 1
