from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.db import engine, sync_engine
from app.core.errors import register_error_handlers
from app.modules.auth.router import admin_router, auth_router, users_router
from app.modules.events.router import router as events_router
from app.modules.submissions.router import router as submissions_router
from app.modules.teams.router import router as teams_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
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


@api.get("/api/v1/time", tags=["health"])
def server_time() -> dict[str, str]:
    return {"now": datetime.now(UTC).isoformat().replace("+00:00", "Z")}


sio = socketio.AsyncServer(
    async_mode="asgi",
    client_manager=socketio.AsyncRedisManager(str(settings.redis_url)),
    cors_allowed_origins=settings.cors_origins,
)


@sio.event
async def connect(sid: str, environ: dict[str, object], auth: object) -> bool:
    # Chặn kết nối tới khi có xác thực và phân quyền phòng theo cuộc thi.
    return False


app = socketio.ASGIApp(sio, other_asgi_app=api)
