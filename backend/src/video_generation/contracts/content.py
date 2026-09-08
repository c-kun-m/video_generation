from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from video_generation.contracts.common import Contract, Identifier

ContentKind = Literal["brief", "script", "storyboard"]
Text = Annotated[str, Field(max_length=20000)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ContentRef(Contract):
    kind: Literal["content"] = "content"
    entity_kind: ContentKind
    revision_id: Identifier
    digest: Digest


class BriefContent(Contract):
    kind: Literal["brief"] = "brief"
    theme: Text = ""
    audience: Text = ""
    purpose: Text = ""
    style: Text = ""
    constraints: Text = ""


class ScriptSegment(Contract):
    segment_id: Identifier
    spoken_text: Text = ""
    visual_description: Text = ""


class ScriptContent(Contract):
    kind: Literal["script"] = "script"
    brief_ref: ContentRef | None = None
    segments: list[ScriptSegment] = Field(default_factory=list, max_length=100)


class StoryboardShot(Contract):
    shot_id: Identifier
    segment_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    intent: Text = ""
    camera: Text = ""
    duration_frames: int = Field(default=240, ge=1, le=1440)


class StoryboardContent(Contract):
    kind: Literal["storyboard"] = "storyboard"
    script_ref: ContentRef | None = None
    fps: Literal[24] = 24
    shots: list[StoryboardShot] = Field(default_factory=list, max_length=8)


ContentPayload = Annotated[
    BriefContent | ScriptContent | StoryboardContent, Field(discriminator="kind")
]


class SaveRevision(Contract):
    @staticmethod
    def _kind_schema(schema: dict) -> None:
        schema["allOf"] = [
            {
                "if": {"properties": {"entity_kind": {"const": kind}}, "required": ["entity_kind"]},
                "then": {"properties": {"payload": {"properties": {"kind": {"const": kind}}}}},
            }
            for kind in ("brief", "script", "storyboard")
        ]

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra=_kind_schema)
    command_id: Identifier
    entity_kind: ContentKind
    expected_row_version: int = Field(ge=0)
    payload: ContentPayload

    @model_validator(mode="after")
    def matching_kind(self):
        if self.entity_kind != self.payload.kind:
            raise ValueError("entity_kind 必须与 payload.kind 相同")
        return self


class ContentRevision(Contract):
    ref: ContentRef
    project_id: Identifier
    revision: int = Field(ge=1)
    schema_version: Literal[1] = 1
    parent_revision_id: Identifier | None
    payload: ContentPayload
    created_by: Identifier
    created_at: str


class ContentHead(Contract):
    entity_kind: ContentKind
    row_version: int
    current: ContentRevision
    review_status: Literal["DRAFT", "APPROVED", "REJECTED", "REVOKED"]
    upstream_outdated: bool = False


class RevisionPage(Contract):
    items: list[ContentRevision]
    next_before: int | None


class ApprovalRef(Contract):
    kind: Literal["approval"] = "approval"
    approval_id: Identifier


class SubmitApproval(Contract):
    command_id: Identifier
    subject_ref: ContentRef
    expected_row_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED", "REVOKED"]
    comment: Annotated[str, Field(max_length=2000)] = ""


class Approval(Contract):
    approval_id: Identifier
    project_id: Identifier
    subject_ref: ContentRef
    decision: Literal["APPROVED", "REJECTED", "REVOKED"]
    policy_version: Literal["manual-content/v1"] = "manual-content/v1"
    comment: str
    actor_id: Identifier
    command_id: Identifier
    created_at: str


class ApprovalPage(Contract):
    items: list[Approval]


class RunRef(Contract):
    kind: Literal["production_run"] = "production_run"
    production_run_id: Identifier
    snapshot_id: Identifier


class RunInputs(Contract):
    @staticmethod
    def _kind_schema(schema: dict) -> None:
        schema["allOf"] = [
            {
                "properties": {
                    kind: {"properties": {"entity_kind": {"const": kind}}}
                    for kind in ("brief", "script", "storyboard")
                }
            }
        ]

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra=_kind_schema)
    brief: ContentRef
    script: ContentRef
    storyboard: ContentRef

    @model_validator(mode="after")
    def matching_kinds(self):
        for kind in ("brief", "script", "storyboard"):
            if getattr(self, kind).entity_kind != kind:
                raise ValueError(f"{kind} 引用的内容类型不匹配")
        return self


class StartProductionRun(Contract):
    command_id: Identifier
    execution_mode: Literal["simulation"]
    input_refs: RunInputs
    expected_row_version: int = Field(ge=1)


class ControlProductionRun(Contract):
    command_id: Identifier
    action: Literal["pause", "resume", "cancel"]


class ProductionSnapshot(Contract):
    snapshot_id: Identifier
    project_id: Identifier
    execution_mode: Literal["simulation"] = "simulation"
    profile_ref: Literal["narrated-portrait/v1"] = "narrated-portrait/v1"
    schema_version: Literal[1] = 1
    input_refs: RunInputs
    contents: list[ContentRevision]
    approval_ids: list[Identifier]
    digest: Digest
    created_at: str


class SimulationStep(Contract):
    operation_id: str
    stage: str
    shot_id: Identifier | None = None
    result: dict
    completed_at: str


RunStatus = Literal[
    "CREATED",
    "PREPARING",
    "RENDERING",
    "COMPLETED",
    "PAUSED",
    "FAILED",
    "CANCEL_REQUESTED",
    "CANCELLED",
]


class ProductionRun(Contract):
    production_run_id: Identifier
    project_id: Identifier
    snapshot_id: Identifier
    execution_mode: Literal["simulation"] = "simulation"
    workflow_id: str
    temporal_run_id: str | None
    status: RunStatus
    stage: str
    pause_requested: bool
    row_version: int
    control_seq: int
    completed_shots: int
    total_shots: int
    error: str | None
    created_at: str
    updated_at: str


class OutboxDelivery(Contract):
    event_id: Identifier
    kind: str
    transport_status: Literal["PENDING", "SENT", "DEAD"]
    attempts: int
    consumed: bool
    error: str | None


class ProductionRunDetail(Contract):
    run: ProductionRun
    snapshot: ProductionSnapshot
    steps: list[SimulationStep]
    deliveries: list[OutboxDelivery] = Field(default_factory=list)


class OutboxStatus(Contract):
    pending: int
    dead_letters: int
    last_worker_seen_at: str | None
    last_dispatcher_seen_at: str | None
