from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_rejects_unknown_origin():
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_server_time_is_current_utc():
    before = datetime.now(UTC)
    with TestClient(app) as client:
        response = client.get("/api/v1/time")
    assert response.status_code == 200
    assert response.json()["now"].endswith("Z")
    assert before <= datetime.fromisoformat(response.json()["now"]) <= datetime.now(UTC)


def test_not_found_error_contract():
    with TestClient(app) as client:
        response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "code": "NOT_FOUND"}
