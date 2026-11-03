import asyncio
import logging
from uuid import UUID

import socketio

from app.core.config import get_settings
from app.core.db import session_factory
from app.core.dependencies import (
    get_event_service,
    get_judging_service,
    get_submission_service,
    get_team_service,
)
from app.core.errors import ApiError
from app.integrations.system_monitor import ping_redis
from app.modules.ai_reviews.repository import ReviewRepository
from app.modules.ai_reviews.service import ReviewService
from app.modules.auth.dependencies import get_auth_service
from app.modules.commits.repository import CommitRepository
from app.modules.commits.service import CommitService
from app.modules.notifications.repository import NotificationRepository

logger = logging.getLogger(__name__)


async def allowed(
    token: str | None, room: str, event: str | None = None, payload: dict | None = None
) -> bool:
    async with session_factory() as session:
        settings = get_settings()
        auth = get_auth_service(session, settings)
        actor = await auth.current_user(token) if token else None
        parts = room.split(":")
        if len(parts) not in {2, 3}:
            return False
        try:
            resource_id = UUID(parts[1])
        except ValueError:
            return False
        events = get_event_service(session, auth)
        if parts[0] == "user" and len(parts) == 2:
            if not actor or actor.id != resource_id:
                return False
            if event == "notification:new":
                return await NotificationRepository(session).can_receive(
                    actor.id, UUID(payload["id"])
                )
            return True
        if parts[0] == "event":
            await events.read(resource_id, actor)
            if len(parts) == 2:
                return True
            if parts[2] == "organizer" and actor:
                await events.require_organizer(actor, resource_id)
                return True
            return False
        if parts[0] != "team" or len(parts) != 2 or not actor or actor.is_admin:
            return False
        teams = get_team_service(session, events, auth, settings)
        submissions = get_submission_service(session, teams, events, auth, settings)
        judging = get_judging_service(session, teams, events, auth, settings, submissions)
        team = await teams.get(resource_id)
        roles = {r.role for r in await auth.roles_in_event(team.event_id) if r.user_id == actor.id}
        member = any(m.user_id == actor.id and m.status == "active" for m in team.members)
        assigned = bool(roles & {"mentor", "judge"}) and await judging.can_read_team(
            actor.id, resource_id
        )
        if not member and not assigned:
            return False
        commits = CommitService(CommitRepository(session), teams, events)
        reviews = ReviewService(ReviewRepository(session), commits, teams, events, judging, auth)
        ids, *_ = await reviews.scope(actor, resource_id, None)
        if event == "ai_review:new":
            row = await reviews.repository.review(UUID(payload["review_id"]))
            return bool(row and row.team_id == resource_id and row.round_id in ids)
        return bool(ids)


async def authorized(
    token: str | None, room: str, event: str | None = None, payload: dict | None = None
) -> bool:
    try:
        return await asyncio.wait_for(allowed(token, room, event, payload), timeout=2)
    except ApiError as exc:
        if exc.status_code >= 500:
            raise
        logger.info("Realtime access denied: %s, room=%s", exc.code, room)
        return False
    except (ValueError, KeyError, TypeError):
        return False


class GuardedRedisManager(socketio.AsyncRedisManager):
    async def _handle_emit(self, message: dict) -> None:
        room = message.get("room")
        if not room or not room.startswith(("user:", "event:", "team:")):
            return
        data = message["data"][0]
        # Chụp danh sách trước vì await bên dưới có thể làm room đổi thành viên.
        for sid, _ in list(self.get_participants("/", room)):
            try:
                state = await self.server.get_session(sid)
                if not await authorized(state.get("token"), room, message["event"], data):
                    await self.server.leave_room(sid, room)
                    continue
                local = {**message, "room": sid}
                await super()._handle_emit(local)
            except Exception:
                await self.server.disconnect(sid)


settings = get_settings()
sio = socketio.AsyncServer(
    async_mode="asgi",
    client_manager=GuardedRedisManager(
        str(settings.redis_url), redis_options={"socket_connect_timeout": 2, "socket_timeout": 2}
    ),
    cors_allowed_origins=settings.cors_origins,
    max_http_buffer_size=16384,
)
connections: dict[str, asyncio.Task] = {}


async def watch(sid: str) -> None:
    try:
        while sio.manager.is_connected(sid, "/"):
            await asyncio.sleep(5)
            await ping_redis(str(get_settings().redis_url))
            state = await sio.get_session(sid)
            token = state.get("token")
            for room in sio.rooms(sid):
                if room == sid:
                    continue
                if not await authorized(token, room):
                    logger.info("Realtime permission revoked", extra={"room": room})
                    await sio.disconnect(sid)
                    return
            # Token/session phải còn hợp lệ kể cả client chưa join room.
            if token:
                async with session_factory() as session:
                    await get_auth_service(session, get_settings()).current_user(token)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Realtime authorization unavailable: %s (%s)",
            type(exc).__name__,
            getattr(exc, "code", "dependency_error"),
        )
        await sio.disconnect(sid)


@sio.event
async def connect(sid: str, environ: dict, auth: object) -> bool:
    if auth is not None and not isinstance(auth, dict):
        return False
    token = auth.get("token") if auth else None
    if token is not None and (not isinstance(token, str) or not token):
        return False
    try:
        await ping_redis(str(get_settings().redis_url))
        if token:
            async with session_factory() as session:
                await get_auth_service(session, get_settings()).current_user(token)
        await sio.save_session(sid, {"token": token})
    except Exception:
        return False
    connections[sid] = sio.start_background_task(watch, sid)
    return True


@sio.event
async def join(sid: str, data: object) -> dict:
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("room"), str)
        or len(data["room"]) > 150
    ):
        return {"ok": False, "code": "INVALID_ROOM"}
    room = data["room"]
    try:
        await ping_redis(str(get_settings().redis_url))
        state = await sio.get_session(sid)
        if not await authorized(state.get("token"), room):
            return {"ok": False, "code": "FORBIDDEN"}
        if len(sio.rooms(sid)) >= 101:
            return {"ok": False, "code": "ROOM_LIMIT"}
        await sio.enter_room(sid, room)
        return {"ok": True}
    except Exception:
        await sio.disconnect(sid)
        return {"ok": False, "code": "REALTIME_UNAVAILABLE"}


@sio.event
async def disconnect(sid: str, reason: str = "") -> None:
    task = connections.pop(sid, None)
    if task and task is not asyncio.current_task():
        task.cancel()


async def shutdown() -> None:
    tasks = list(connections.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    connections.clear()
    if sio.eio.service_task_handle is not None:
        await sio.shutdown()
    sio.eio.service_task_event = None
    sio.eio.start_service_task = True
    thread = getattr(sio.manager, "thread", None)
    if thread:
        thread.cancel()
        await asyncio.gather(thread, return_exceptions=True)
    for name in ("pubsub", "redis"):
        client = getattr(sio.manager, name, None)
        if client:
            await client.aclose()
    sio.manager_initialized = False
