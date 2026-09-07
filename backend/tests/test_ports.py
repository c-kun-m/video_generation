from hashlib import sha256

from video_generation.adapters.ports import (
    AgentProvider,
    ArtifactRef,
    MediaPort,
    RenderPort,
    RenderReceipt,
    StoragePort,
)


class FakeStorage:
    def __init__(self):
        self.objects = {}

    async def put(self, data, media_type):
        ref = ArtifactRef(sha256(data).hexdigest(), media_type)
        self.objects[ref.artifact_id] = data
        return ref

    async def read(self, ref):
        return self.objects[ref.artifact_id]


class FakeAgent:
    async def plan(self, brief, *, operation_id):
        return {"brief": brief, "operation_id": operation_id, "test_double": True}


class FakeRender:
    async def submit(self, workflow, *, operation_id):
        return RenderReceipt(operation_id, "TEST_ONLY")

    async def inspect(self, execution_id):
        return RenderReceipt(execution_id, "TEST_ONLY")


class FakeMedia:
    async def compose(self, inputs, *, operation_id):
        return ArtifactRef(operation_id, "application/x-test-only")


async def test_ports_can_be_composed_without_external_services():
    storage: StoragePort = FakeStorage()
    agent: AgentProvider = FakeAgent()
    render: RenderPort = FakeRender()
    media: MediaPort = FakeMedia()
    ref = await storage.put(b"fixture", "application/x-test-only")
    assert await storage.read(ref) == b"fixture"
    plan = await agent.plan("fixture brief", operation_id="fixture-op")
    receipt = await render.submit(plan, operation_id="fixture-op")
    assert await render.inspect(receipt.execution_id) == receipt
    assert (
        await media.compose([ref], operation_id="fixture-op")
    ).media_type == "application/x-test-only"
