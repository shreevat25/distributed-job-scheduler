"""FastAPI application entry point with middleware, error handling, and routing."""

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import (
    generate_request_id,
    get_logger,
    request_id_ctx,
    current_user_id_ctx,
    setup_logging,
)
from app.db.session import engine

# Import routes
from app.api.routes import auth, projects, retry_policies, queues, jobs, batches, workers, dlq, schedules

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: setup logging and dispose engine on shutdown."""
    setup_logging(settings.LOG_LEVEL)
    logger.info("application_starting", log_level=settings.LOG_LEVEL)
    yield
    await engine.dispose()
    logger.info("application_shutdown")


app = FastAPI(
    title="Distributed Job Scheduler",
    description="A production-inspired distributed job scheduling platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Assign or propagate a request ID for every HTTP request.

    Policy: If client sends a valid UUID in X-Request-ID, reuse it.
    Otherwise, generate a new one.
    """
    client_request_id = request.headers.get(REQUEST_ID_HEADER)
    if client_request_id:
        try:
            uuid.UUID(client_request_id)
            rid = client_request_id
        except ValueError:
            rid = generate_request_id()
    else:
        rid = generate_request_id()

    request_id_ctx.set(rid)
    request.state.request_id = rid

    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = rid
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle domain exceptions with structured error responses."""
    rid = getattr(request.state, "request_id", "")
    logger.warning(
        "app_error",
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": rid,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — never leak stack traces to clients."""
    rid = getattr(request.state, "request_id", "")
    logger.error(
        "unhandled_exception",
        error_type=type(exc).__name__,
        error_message=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {},
                "request_id": rid,
            }
        },
    )


# API version prefix
API_V1_PREFIX = "/api/v1"

# Register routes
app.include_router(auth.router, prefix=API_V1_PREFIX)
app.include_router(projects.router, prefix=API_V1_PREFIX)
app.include_router(retry_policies.router, prefix=API_V1_PREFIX)
app.include_router(queues.router, prefix=API_V1_PREFIX)
app.include_router(jobs.router, prefix=API_V1_PREFIX)
app.include_router(batches.router, prefix=API_V1_PREFIX)
app.include_router(workers.router, prefix=API_V1_PREFIX)
app.include_router(dlq.router, prefix=API_V1_PREFIX)
app.include_router(schedules.router, prefix=API_V1_PREFIX + "/schedules", tags=["schedules"])


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
