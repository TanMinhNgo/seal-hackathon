from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers


def test_validation_error_contract():
    api = FastAPI()
    register_error_handlers(api)

    @api.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    with TestClient(api) as client:
        response = client.get("/items/not-an-integer")
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request data", "code": "VALIDATION_ERROR"}


def test_internal_error_does_not_expose_exception():
    api = FastAPI()
    register_error_handlers(api)

    @api.get("/broken")
    def broken() -> None:
        raise RuntimeError("sensitive upstream information")

    with TestClient(api, raise_server_exceptions=False) as client:
        response = client.get("/broken")
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error",
        "code": "INTERNAL_SERVER_ERROR",
    }
