import asyncio
import json
import os
import time
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import realtime
from app.integrations.realtime import publish
from app.modules.auth.models import EventRole
from tests.test_auth import database_query
from tests.test_events_teams import open_event


def packet(websocket):
    async def receive():
        return await asyncio.wait_for(websocket._send_rx.receive(), timeout=10)

    for _ in range(10):
        message = websocket.portal.call(receive)
        websocket._raise_on_close(message)
        value = message["text"]
        if value == "2":
            websocket.send_text("3")
        else:
            return value
    raise AssertionError("No Socket.IO packet")


@pytest.mark.skipif(
    os.environ.get("SEAL_TEST_REDIS") != "1", reason="Explicit real Redis socket smoke"
)
def test_socket_engineio_handshake_room_ack_and_redis_invalidation(
    world, auth_settings, monkeypatch
):
    w = world
    open_event(w)
    monkeypatch.setattr(
        realtime, "session_factory", async_sessionmaker(w.engine, expire_on_commit=False)
    )
    monkeypatch.setattr(realtime, "get_settings", lambda: auth_settings)
    with w.client.websocket_connect(
        "/socket.io/?EIO=4&transport=websocket",
        headers={"upgrade": "websocket", "connection": "upgrade"},
    ) as socket:
        assert packet(socket).startswith("0{")
        socket.send_text("40")
        assert packet(socket).startswith("40{")
        socket.send_text("421" + json.dumps(["join", {"room": f"event:{w.event['id']}:organizer"}]))
        assert json.loads(packet(socket)[3:])[0] == {"ok": False, "code": "FORBIDDEN"}
        socket.send_text("422" + json.dumps(["join", {"room": f"event:{w.event['id']}"}]))
        assert json.loads(packet(socket)[3:])[0] == {"ok": True}
        publish("leaderboard:unpublished", f"event:{w.event['id']}", {"round_id": w.round["id"]})
        assert json.loads(packet(socket)[2:]) == [
            "leaderboard:unpublished",
            {"round_id": w.round["id"]},
        ]
    login = w.client.post(
        "/api/v1/auth/login", json={"email": w.organizer.email, "password": "Test password 123!"}
    )
    token = login.json()["access_token"]
    with w.client.websocket_connect(
        "/socket.io/?EIO=4&transport=websocket",
        headers={"upgrade": "websocket", "connection": "upgrade"},
    ) as socket:
        assert packet(socket).startswith("0{")
        socket.send_text("40" + json.dumps({"token": token}))
        assert packet(socket).startswith("40{")
        for index, room in enumerate(
            (f"event:{w.event['id']}:organizer", f"event:{w.event['id']}"), 1
        ):
            socket.send_text(f"42{index}" + json.dumps(["join", {"room": room}]))
            assert json.loads(packet(socket)[3:])[0] == {"ok": True}
        time.sleep(12)
        publish("sync:updated", f"event:{w.event['id']}:organizer", {"team_id": "retained-marker"})
        assert json.loads(packet(socket)[2:]) == ["sync:updated", {"team_id": "retained-marker"}]
        database_query(
            w.engine,
            delete(EventRole).where(
                EventRole.event_id == UUID(w.event["id"]), EventRole.user_id == UUID(w.organizer.id)
            ),
        )
        publish("sync:updated", f"event:{w.event['id']}:organizer", {"team_id": "private-marker"})
        publish("leaderboard:unpublished", f"event:{w.event['id']}", {"round_id": w.round["id"]})
        assert json.loads(packet(socket)[2:])[0] == "leaderboard:unpublished"
        assert w.client.post("/api/v1/auth/logout").status_code == 204
        assert packet(socket) == "41"
