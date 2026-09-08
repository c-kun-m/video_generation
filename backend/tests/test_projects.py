import asyncio
from datetime import timedelta

import httpx
from sqlalchemy import delete, func, select

from video_generation.api.app import create_app
from video_generation.application.auth import initialize_owner, secret_hash
from video_generation.infrastructure.persistence.models import (
    Actor,
    Command,
    DeviceSession,
    Event,
    Membership,
    Workspace,
    new_id,
    utcnow,
)

BASE = "/video/v1"


async def create(client, title="第一支短片"):
    body = {"command_id": new_id(), "title": title}
    result = await client.post(BASE + "/projects", json=body)
    assert result.status_code == 201, result.text
    return result.json()["project"], body


async def test_twenty_concurrent_retries_and_digest_conflict(client, app):
    body = {"command_id": new_id(), "title": "并发去重"}
    replies = await asyncio.gather(*[client.post(BASE + "/projects", json=body) for _ in range(20)])
    assert all(response.status_code == 201 for response in replies)
    ids = {response.json()["project"]["project_id"] for response in replies}
    assert len(ids) == 1
    async with app.state.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.causation_command_id == body["command_id"])
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Command)
                .where(Command.command_id == body["command_id"])
            )
            == 1
        )
    changed = await client.post(BASE + "/projects", json={**body, "title": "不同请求"})
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


async def test_lifecycle_conflict_events_and_restart(client, app):
    project, body = await create(client)
    project_id = project["project_id"]
    path = f"{BASE}/projects/{project_id}"
    changes = [
        {"command_id": new_id(), "expected_row_version": 1, "title": name}
        for name in ["新标题甲", "新标题乙"]
    ]
    replies = await asyncio.gather(*[client.patch(path, json=change) for change in changes])
    assert sorted(r.status_code for r in replies) == [200, 409]
    rejected = replies.index(next(r for r in replies if r.status_code == 409))
    stored = await client.get(f"{BASE}/commands/{changes[rejected]['command_id']}")
    assert stored.json()["status"] == "REJECTED"
    replay = await client.patch(path, json=changes[rejected])
    assert replay.status_code == 409
    for version, archived in [(2, True), (3, False)]:
        result = await client.patch(
            path,
            json={"command_id": new_id(), "expected_row_version": version, "archived": archived},
        )
        assert result.status_code == 200
        assert bool(result.json()["project"]["archived_at"]) == archived
    snapshot = (await client.get(path + "/snapshot")).json()
    assert snapshot["event_cursor"] == snapshot["project"]["row_version"] == 4
    events = (await client.get(path + "/events?after=0&limit=2")).json()
    assert [event["seq"] for event in events["items"]] == [1, 2] and events["has_more"]
    tail = (await client.get(path + "/events?after=2")).json()
    assert [event["seq"] for event in tail["items"]] == [3, 4]
    assert (await client.get(path + "/events?after=999")).status_code == 409
    restarted = create_app(app.state.settings)
    async with (
        restarted.router.lifespan_context(restarted),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted),
            base_url="http://127.0.0.1",
            headers=client.headers,
        ) as second,
    ):
        assert (await second.get(path + "/snapshot")).json() == snapshot
        assert (await second.get(f"{BASE}/commands/{body['command_id']}")).json()["project"][
            "project_id"
        ] == project_id
        assert (await second.get("/health/ready")).status_code == 200
    async with app.state.sessions() as session, session.begin():
        await session.execute(delete(Event).where(Event.project_id == project_id, Event.seq == 3))
    assert (await client.get(path + "/events?after=1")).json()["error"][
        "code"
    ] == "SNAPSHOT_REQUIRED"


async def second_identity(app, *, tenant_id=None, role="owner", kind="user"):
    async with app.state.sessions() as session, session.begin():
        if tenant_id is None:
            workspace = Workspace(id=new_id(), slug=new_id(), name="独立空间")
            session.add(workspace)
            tenant_id = workspace.id
        actor = Actor(id=new_id(), display_name="另一个用户", kind=kind)
        session.add(actor)
        await session.flush()
        session.add(Membership(tenant_id=tenant_id, actor_id=actor.id, role=role))
        await session.flush()
        token = new_id()
        session.add(
            DeviceSession(
                tenant_id=tenant_id,
                actor_id=actor.id,
                device_name="test",
                token_hash=secret_hash(token),
                expires_at=utcnow() + timedelta(days=1),
            )
        )
    return {"Authorization": f"Bearer {token}"}


async def test_tenant_actor_and_role_boundaries(client, app):
    project, body = await create(client, "私有项目")
    path = f"{BASE}/projects/{project['project_id']}"
    outsider = await second_identity(app)
    for endpoint in [path + "/snapshot", path + "/events", f"{BASE}/commands/{body['command_id']}"]:
        assert (await client.get(endpoint, headers=outsider)).status_code == 404
    assert (await client.get(BASE + "/projects", headers=outsider)).json()["items"] == []
    assert (
        await client.patch(
            path,
            headers=outsider,
            json={"command_id": new_id(), "expected_row_version": 1, "title": "越权"},
        )
    ).status_code == 404
    viewer = await second_identity(app, tenant_id=project["tenant_id"], role="viewer")
    assert (await client.get(path + "/snapshot", headers=viewer)).status_code == 200
    assert (
        await client.post(
            BASE + "/projects", headers=viewer, json={"command_id": new_id(), "title": "越权"}
        )
    ).status_code == 403
    assert (
        await client.get(f"{BASE}/commands/{body['command_id']}", headers=viewer)
    ).status_code == 404
    system = await second_identity(app, kind="system")
    assert (await client.get(BASE + "/me", headers=system)).status_code == 401
    assert (
        await client.post(BASE + "/projects", json={**body, "tenant_id": project["tenant_id"]})
    ).status_code == 422


async def test_pairing_replay_logout_validation_and_pagination(client, app):
    code = await initialize_owner(app.state.sessions, app.state.settings)
    body = {"pairing_code": code, "device_name": "设备"}
    pairs = await asyncio.gather(*[client.post(BASE + "/auth/pair", json=body) for _ in range(2)])
    assert sorted(r.status_code for r in pairs) == [200, 401]
    for value in ["", "   ", 123, True]:
        assert (
            await client.post(BASE + "/projects", json={"command_id": new_id(), "title": value})
        ).status_code == 422
    project, _ = await create(client)
    assert (
        await client.patch(
            f"{BASE}/projects/{project['project_id']}",
            json={"command_id": new_id(), "expected_row_version": 1, "title": None},
        )
    ).status_code == 422
    await create(client, "分页项目")
    first = (await client.get(BASE + "/projects?limit=1")).json()
    second = (
        await client.get(BASE + "/projects", params={"limit": 1, "cursor": first["next_cursor"]})
    ).json()
    assert first["items"][0]["project_id"] != second["items"][0]["project_id"]
    assert (await client.get(BASE + "/projects?cursor=invalid")).status_code == 422
    assert (
        await client.post(
            BASE + "/projects",
            headers={"Origin": "https://untrusted.example"},
            json={"command_id": new_id(), "title": "网页调用"},
        )
    ).status_code == 403
    assert (await client.post(BASE + "/auth/logout")).status_code == 200
    assert (await client.get(BASE + "/me")).status_code == 401
