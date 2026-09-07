"""Stable boundaries for future integrations. No model or GPU is invoked in phase one."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    media_type: str


@dataclass(frozen=True)
class RenderReceipt:
    execution_id: str
    state: str


class AgentProvider(Protocol):
    async def plan(self, brief: str, *, operation_id: str) -> dict: ...


class RenderPort(Protocol):
    async def submit(self, workflow: dict, *, operation_id: str) -> RenderReceipt: ...

    async def inspect(self, execution_id: str) -> RenderReceipt: ...


class MediaPort(Protocol):
    async def compose(self, inputs: list[ArtifactRef], *, operation_id: str) -> ArtifactRef: ...


class StoragePort(Protocol):
    async def put(self, data: bytes, media_type: str) -> ArtifactRef: ...

    async def read(self, ref: ArtifactRef) -> bytes: ...
