"""FastAPI application entry point."""

import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import get_settings
from models.database import check_database
from models.schemas import HealthResponse
from routers import pond_planner
from services.http_client import close_http_client

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configuration_errors = settings.validation_errors()
    if configuration_errors:
        raise RuntimeError("Invalid application configuration: " + "; ".join(configuration_errors))
    logger.info("application_start env=%s", settings.app_env)
    yield
    await close_http_client()
    logger.info("application_stop")


app = FastAPI(
    title=settings.app_name,
    description="Geospatial screening support for village pond planning; not a construction design or land-ownership authority.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-API-Key", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", supplied_request_id)
        else str(uuid.uuid4())
    )
    started = time.perf_counter()
    response = None
    contour_paths = {
        "/api/analyze-contour",
        "/api/analyzeContour",
        "/api/findCatchment",
    }
    if request.method == "POST" and request.url.path in contour_paths:
        content_length = request.headers.get("Content-Length")
        try:
            body_size = int(content_length) if content_length is not None else None
        except ValueError:
            body_size = None
        maximum_body_size = settings.contour_max_upload_bytes + 64 * 1024
        if body_size is not None and body_size > maximum_body_size:
            response = JSONResponse(
                status_code=413,
                content={
                    "detail": {
                        "code": "contour_file_too_large",
                        "message": (
                            "Contour upload exceeds the configured "
                            f"{settings.contour_max_upload_bytes // (1024 * 1024)} MB limit"
                        ),
                    }
                },
            )
    if response is None:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed request_id=%s path=%s", request_id, request.url.path)
            raise
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    logger.info(
        "request_complete request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


app.include_router(pond_planner.router, prefix="/api", tags=["Pond Planning"])


@app.get("/health/live", response_model=HealthResponse, tags=["Health"])
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok", checks={"api": "ok"})


@app.get("/health/ready", response_model=HealthResponse, tags=["Health"])
async def readiness() -> JSONResponse | HealthResponse:
    if not settings.history_enabled:
        return HealthResponse(status="ok", checks={"api": "ok", "database": "disabled"})
    try:
        await asyncio.to_thread(check_database)
        return HealthResponse(status="ok", checks={"api": "ok", "database": "ok"})
    except Exception as exc:
        logger.warning("readiness_database_failed error_type=%s", type(exc).__name__)
        payload = HealthResponse(
            status="degraded", checks={"api": "ok", "database": "unavailable"}
        )
        return JSONResponse(status_code=503, content=json.loads(payload.model_dump_json()))


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    payload = {
        "status": "ok",
        "message": "Village Pond Planning screening API",
    }
    if settings.enable_api_docs:
        payload["documentation"] = "/docs"
    return payload
