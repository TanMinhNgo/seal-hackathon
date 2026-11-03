from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.db import engine, sync_engine
from app.core.errors import register_error_handlers
from app.modules.ai_reviews.router import router as ai_reviews_router
from app.modules.auth.dependencies import SystemServiceDependency
from app.modules.auth.router import admin_router, auth_router, users_router
from app.modules.commits.router import router as commits_router
from app.modules.events.router import router as events_router
from app.modules.judging.router import router as judging_router
from app.modules.notifications.router import router as notifications_router
from app.modules.reports.router import router as reports_router
from app.modules.submissions.router import router as submissions_router
from app.modules.teams.router import router as teams_router
from app.realtime import shutdown, sio

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await shutdown()
        await engine.dispose()
        sync_engine.dispose()


api = FastAPI(title=settings.app_name, lifespan=lifespan)
register_error_handlers(api)
api.include_router(auth_router)
api.include_router(users_router)
api.include_router(admin_router)
api.include_router(events_router)
api.include_router(teams_router)
api.include_router(submissions_router)
api.include_router(judging_router)
api.include_router(commits_router)
api.include_router(ai_reviews_router)
api.include_router(notifications_router)
api.include_router(reports_router)
api.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


@api.get("/api/v1/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.get(
    "/api/v1/ready", tags=["health"], responses={503: {"description": "Dependencies unavailable"}}
)
async def ready(service: SystemServiceDependency) -> JSONResponse:
    ok = await service.ready()
    return JSONResponse(
        {"status": "ready" if ok else "not_ready"},
        status_code=200 if ok else 503,
        headers={"Cache-Control": "no-store"},
    )


@api.get("/api/v1/time", tags=["health"])
def server_time() -> dict[str, str]:
    return {"now": datetime.now(UTC).isoformat().replace("+00:00", "Z")}


app = socketio.ASGIApp(sio, other_asgi_app=api)
