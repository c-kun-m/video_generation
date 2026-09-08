from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from video_generation import __version__
from video_generation.application.auth import ActorContext, authenticate, logout, pair_device
from video_generation.application.content import ContentService
from video_generation.application.operations import execution_status
from video_generation.application.production import ProductionService
from video_generation.application.projects import ProjectService
from video_generation.contracts.content import (
    ApprovalPage,
    ContentKind,
    ControlProductionRun,
    OutboxStatus,
    ProductionRunDetail,
    RevisionPage,
    SaveRevision,
    StartProductionRun,
    SubmitApproval,
)
from video_generation.contracts.models import (
    Capabilities,
    Capability,
    CommandResult,
    CreateProject,
    ErrorResponse,
    EventPage,
    Identity,
    LogoutResponse,
    PairRequest,
    PairResponse,
    ProjectPage,
    ProjectSnapshot,
    UpdateProject,
)
from video_generation.domain.errors import DomainError

router = APIRouter(
    prefix="/video/v1",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
bearer = HTTPBearer(auto_error=False)


async def current_actor(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> ActorContext:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise DomainError("UNAUTHENTICATED", "请先配对本机设备。", 401)
    return await authenticate(request.app.state.sessions, credentials.credentials)


Authenticated = Annotated[ActorContext, Depends(current_actor)]


def service(request: Request) -> ProjectService:
    return ProjectService(request.app.state.sessions)


def command_response(result: CommandResult, status: int, request: Request):
    from video_generation.workers.faults import crash_if_selected

    crash_if_selected(request.app.state.settings, "api_after_commit", result.command_id)
    if result.status == "REJECTED":
        detail = result.error.model_copy(update={"trace_id": request.state.trace_id})
        return JSONResponse(ErrorResponse(error=detail).model_dump(), status_code=status)
    return JSONResponse(result.model_dump(mode="json"), status_code=status)


@router.post(
    "/auth/pair", response_model=PairResponse, operation_id="pairDevice", tags=["identity"]
)
async def pair(body: PairRequest, request: Request):
    return await pair_device(request.app.state.sessions, request.app.state.settings, body)


@router.get("/me", response_model=Identity, operation_id="getIdentity", tags=["identity"])
async def me(actor: Authenticated):
    return actor.identity


@router.post(
    "/auth/logout", response_model=LogoutResponse, operation_id="logout", tags=["identity"]
)
async def revoke(request: Request, actor: Authenticated):
    await logout(request.app.state.sessions, actor)
    return LogoutResponse(revoked=True)


@router.get("/projects", response_model=ProjectPage, operation_id="listProjects", tags=["projects"])
async def list_projects(
    request: Request,
    actor: Authenticated,
    archived: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
):
    return await service(request).list(actor, archived, limit, cursor)


@router.post(
    "/projects",
    response_model=CommandResult,
    status_code=201,
    operation_id="createProject",
    tags=["projects"],
)
async def create_project(body: CreateProject, request: Request, actor: Authenticated):
    result, status = await service(request).create(actor, body)
    return command_response(result, status, request)


@router.patch(
    "/projects/{project_id}",
    response_model=CommandResult,
    operation_id="updateProject",
    tags=["projects"],
)
async def update_project(
    project_id: str, body: UpdateProject, request: Request, actor: Authenticated
):
    result, status = await service(request).update(actor, project_id, body)
    return command_response(result, status, request)


@router.get(
    "/projects/{project_id}/snapshot",
    response_model=ProjectSnapshot,
    operation_id="getProjectSnapshot",
    tags=["projects"],
)
async def snapshot(project_id: str, request: Request, actor: Authenticated):
    return await service(request).snapshot(actor, project_id)


@router.get(
    "/projects/{project_id}/events",
    response_model=EventPage,
    operation_id="getProjectEvents",
    tags=["projects"],
)
async def events(
    project_id: str,
    request: Request,
    actor: Authenticated,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    return await service(request).events(actor, project_id, after, limit)


@router.get(
    "/commands/{command_id}",
    response_model=CommandResult,
    operation_id="getCommand",
    tags=["commands"],
)
async def command(command_id: str, request: Request, actor: Authenticated):
    return await service(request).get_command(actor, command_id)


@router.post(
    "/projects/{project_id}/revisions",
    response_model=CommandResult,
    status_code=201,
    operation_id="saveRevision",
    tags=["content"],
)
async def save_revision(
    project_id: str, body: SaveRevision, request: Request, actor: Authenticated
):
    result, status = await ContentService(request.app.state.sessions).save(actor, project_id, body)
    return command_response(result, status, request)


@router.get(
    "/projects/{project_id}/revisions",
    response_model=RevisionPage,
    operation_id="listRevisions",
    tags=["content"],
)
async def revisions(
    project_id: str,
    request: Request,
    actor: Authenticated,
    entity_kind: ContentKind,
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
):
    return await ContentService(request.app.state.sessions).history(
        actor, project_id, entity_kind, before, limit
    )


@router.post(
    "/projects/{project_id}/approvals",
    response_model=CommandResult,
    status_code=201,
    operation_id="submitApproval",
    tags=["content"],
)
async def submit_approval(
    project_id: str, body: SubmitApproval, request: Request, actor: Authenticated
):
    result, status = await ContentService(request.app.state.sessions).approve(
        actor, project_id, body
    )
    return command_response(result, status, request)


@router.get(
    "/projects/{project_id}/approvals",
    response_model=ApprovalPage,
    operation_id="listApprovals",
    tags=["content"],
)
async def approvals(
    project_id: str, request: Request, actor: Authenticated, revision_id: str | None = None
):
    return await ContentService(request.app.state.sessions).approvals(
        actor, project_id, revision_id
    )


@router.post(
    "/projects/{project_id}/production-runs",
    response_model=CommandResult,
    status_code=202,
    operation_id="startProductionRun",
    tags=["production"],
)
async def start_run(
    project_id: str, body: StartProductionRun, request: Request, actor: Authenticated
):
    result, status = await ProductionService(request.app.state.sessions).start(
        actor, project_id, body
    )
    return command_response(result, status, request)


@router.get(
    "/production-runs/{run_id}",
    response_model=ProductionRunDetail,
    operation_id="getProductionRun",
    tags=["production"],
)
async def run_detail(run_id: str, request: Request, actor: Authenticated):
    return await ProductionService(request.app.state.sessions).detail(actor, run_id)


@router.post(
    "/production-runs/{run_id}/commands",
    response_model=CommandResult,
    status_code=202,
    operation_id="controlProductionRun",
    tags=["production"],
)
async def control_run(
    run_id: str, body: ControlProductionRun, request: Request, actor: Authenticated
):
    result, status = await ProductionService(request.app.state.sessions).control(
        actor, run_id, body
    )
    return command_response(result, status, request)


@router.get(
    "/system/capabilities",
    response_model=Capabilities,
    operation_id="getCapabilities",
    tags=["system"],
)
async def capabilities(actor: Authenticated):
    return Capabilities(
        app_version=__version__,
        capabilities=[
            Capability(id="projects", name="项目管理", status="ready"),
            Capability(id="content", name="内容版本与审批", status="ready"),
            Capability(id="agent", name="LangChain 创作", status="not_integrated"),
            Capability(id="orchestration", name="Temporal 模拟演练", status="ready"),
            Capability(id="render", name="ComfyUI 镜头生成", status="not_integrated"),
            Capability(id="media", name="配音与成片合成", status="not_integrated"),
        ],
    )


@router.get(
    "/system/execution-status",
    response_model=OutboxStatus,
    operation_id="getExecutionStatus",
    tags=["system"],
)
async def runtime_status(request: Request, actor: Authenticated):
    return await execution_status(request.app.state.sessions, actor)
