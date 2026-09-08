import json
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from video_generation import __version__
from video_generation.api.routes import router
from video_generation.config import MIGRATION_HEAD, Settings
from video_generation.contracts.models import ErrorDetail, ErrorResponse, FieldIssue, Health
from video_generation.domain.errors import DomainError
from video_generation.infrastructure.persistence.database import create_database

log = logging.getLogger("video.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine, sessions = create_database(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Video Generation API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = sessions
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    pairing_attempts: dict[str, deque] = defaultdict(deque)

    @app.middleware("http")
    async def trace_and_guard(request: Request, call_next):
        request.state.trace_id = str(uuid.uuid4())
        start = time.monotonic()
        # Desktop Main uses no browser Origin. Reject cross-site local API requests.
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("origin"):
            return error_response(
                DomainError("FORBIDDEN", "此接口仅接受已配对桌面客户端。", 403), request
            )
        if request.url.path == "/video/v1/auth/pair":
            key = request.client.host if request.client else "local"
            if len(pairing_attempts) > 1024:
                pairing_attempts.clear()
            attempts = pairing_attempts[key]
            while attempts and attempts[0] < start - 60:
                attempts.popleft()
            if len(attempts) >= 20:
                return error_response(
                    DomainError("RATE_LIMITED", "配对尝试过多，请稍后重试。", 429), request
                )
            attempts.append(start)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.trace_id
        response.headers["Cache-Control"] = "no-store"
        log.info(
            json.dumps(
                {
                    "service": "video-api",
                    "trace_id": request.state.trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "elapsed_ms": round((time.monotonic() - start) * 1000),
                }
            )
        )
        return response

    def error_response(exc: DomainError, request: Request) -> JSONResponse:
        detail = exc.detail.model_copy(update={"trace_id": getattr(request.state, "trace_id", "")})
        return JSONResponse(ErrorResponse(error=detail).model_dump(), status_code=exc.status_code)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return error_response(exc, request)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        detail = ErrorDetail(
            code="VALIDATION_FAILED",
            message="提交内容未通过校验。",
            trace_id=getattr(request.state, "trace_id", ""),
            fields=[
                FieldIssue(field=".".join(map(str, err["loc"])), message=err["msg"])
                for err in exc.errors()
            ],
        )
        return JSONResponse(ErrorResponse(error=detail).model_dump(), status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        log.error(json.dumps({"error": type(exc).__name__, "trace_id": request.state.trace_id}))
        return error_response(
            DomainError("SERVICE_UNAVAILABLE", "数据库暂不可用，请稍后重试。", 503), request
        )

    @app.get("/health/live", response_model=Health, operation_id="liveness", tags=["system"])
    async def live():
        return Health(status="ok")

    @app.get(
        "/health/ready",
        response_model=Health,
        responses={503: {"model": Health}},
        operation_id="readiness",
        tags=["system"],
    )
    async def ready():
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                exists = await connection.scalar(
                    text("SELECT to_regclass('public.alembic_version')")
                )
                revision = (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    if exists
                    else None
                )
            healthy = revision == MIGRATION_HEAD
            result = Health(
                status="ready" if healthy else "unavailable",
                database="ready",
                migrations="ready" if healthy else "pending",
            )
        except SQLAlchemyError:
            healthy = False
            result = Health(status="unavailable", database="unavailable", migrations="unknown")
        return JSONResponse(result.model_dump(), status_code=200 if healthy else 503)

    app.include_router(router)
    return app
