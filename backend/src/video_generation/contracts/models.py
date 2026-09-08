# Re-export the wire models for the contract exporter and generated clients.
# ruff: noqa: F401
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from video_generation.contracts.common import Contract, Identifier
from video_generation.contracts.content import (
    Approval,
    ApprovalPage,
    ApprovalRef,
    BriefContent,
    ContentHead,
    ContentRef,
    ContentRevision,
    ControlProductionRun,
    OutboxStatus,
    ProductionRun,
    ProductionRunDetail,
    ProductionSnapshot,
    RevisionPage,
    RunInputs,
    RunRef,
    SaveRevision,
    ScriptContent,
    ScriptSegment,
    SimulationStep,
    StartProductionRun,
    StoryboardContent,
    StoryboardShot,
    SubmitApproval,
)

Title = Annotated[str, StringConstraints(pattern=r"\S", min_length=1, max_length=200)]


class FieldIssue(Contract):
    field: str
    message: str


class ErrorDetail(Contract):
    code: str
    message: str
    trace_id: str = ""
    fields: list[FieldIssue] = Field(default_factory=list)
    current_row_version: int | None = None


class ErrorResponse(Contract):
    error: ErrorDetail


class PairRequest(Contract):
    pairing_code: Annotated[str, StringConstraints(min_length=16, max_length=256)]
    device_name: Annotated[str, StringConstraints(pattern=r"\S", min_length=1, max_length=80)]


class Identity(Contract):
    actor_id: Identifier
    tenant_id: Identifier
    display_name: str
    workspace_name: str
    role: Literal["owner", "editor", "reviewer", "viewer", "operator"]
    session_id: Identifier


class PairResponse(Contract):
    access_token: str
    expires_at: str
    identity: Identity


class LogoutResponse(Contract):
    revoked: bool


class ProductProfile(Contract):
    profile_id: Literal["narrated-portrait/v1"] = "narrated-portrait/v1"
    name: str = "中文解说 · 竖屏短片"
    width: int = 720
    height: int = 1280
    fps: int = 24
    min_seconds: int = 30
    max_seconds: int = 60


class Project(Contract):
    project_id: Identifier
    tenant_id: Identifier
    title: Title
    product_profile_ref: Literal["narrated-portrait/v1"]
    row_version: int = Field(ge=1)
    created_at: str
    updated_at: str
    archived_at: str | None


class CreateProject(Contract):
    command_id: Identifier
    title: Title
    product_profile_ref: Literal["narrated-portrait/v1"] = "narrated-portrait/v1"


class UpdateProject(Contract):
    @staticmethod
    def _change_schema(schema: dict) -> None:
        schema["allOf"] = [
            {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {"title": {"type": "string"}},
                        "required": ["title"],
                    },
                    {
                        "type": "object",
                        "properties": {"archived": {"type": "boolean"}},
                        "required": ["archived"],
                    },
                ]
            }
        ]
        for name in ("title", "archived"):
            prop = schema["properties"][name]
            schema["properties"][name] = prop["anyOf"][0]

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra=_change_schema)

    command_id: Identifier
    expected_row_version: int = Field(ge=1)
    title: Title | None = None
    archived: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UpdateProject":
        changes = self.model_fields_set & {"title", "archived"}
        if not changes:
            raise ValueError("至少提供 title 或 archived")
        if any(getattr(self, field) is None for field in changes):
            raise ValueError("title 和 archived 不能为 null")
        return self


class ProjectRef(Contract):
    kind: Literal["project"] = "project"
    project_id: Identifier


class CommandResult(Contract):
    command_id: Identifier
    status: Literal["ACCEPTED", "APPLIED", "REJECTED"]
    business_result_ref: ProjectRef | ContentRef | ApprovalRef | RunRef | None = None
    project: Project | None = None
    error: ErrorDetail | None = None


class ProjectPage(Contract):
    items: list[Project]
    total: int
    next_cursor: str | None


class ProjectSnapshot(Contract):
    project: Project
    event_cursor: int
    contents: list[ContentHead] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    production_runs: list[ProductionRun] = Field(default_factory=list)


class ProjectEvent(Contract):
    event_id: Identifier
    seq: int
    type: Literal[
        "project.created",
        "project.updated",
        "content.saved",
        "content.reviewed",
        "run.created",
        "run.control_requested",
        "run.updated",
        "run.step_completed",
    ]
    schema_version: int = 1
    subject_ref: ProjectRef | ContentRef | ApprovalRef | RunRef | None = None
    payload: dict = Field(default_factory=dict)
    project_id: Identifier
    row_version: int
    causation_command_id: Identifier
    occurred_at: str


class EventPage(Contract):
    items: list[ProjectEvent]
    next_cursor: int
    has_more: bool


class Capability(Contract):
    id: str
    name: str
    status: Literal["ready", "not_integrated"]


class Capabilities(Contract):
    app_version: str
    contract_version: Literal["video/v1"] = "video/v1"
    product_profile: ProductProfile = Field(default_factory=ProductProfile)
    capabilities: list[Capability]


class Health(Contract):
    status: Literal["ok", "ready", "unavailable"]
    database: Literal["ready", "unavailable"] | None = None
    migrations: Literal["ready", "pending", "unknown"] | None = None
