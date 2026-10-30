import asyncio
import os
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.main import api, app
from app.modules.auth.dependencies import rate_limit_auth
from worker.tasks.send_email import send_email


@pytest.fixture
def auth_settings():
    return Settings(
        _env_file=None,
        jwt_secret=SecretStr("test-signing-key-only-" * 3),
        smtp_host="smtp.example.com",
        smtp_username="sender@example.com",
        smtp_password=SecretStr("test-smtp-password"),
    )


@pytest.fixture
def email_queue(monkeypatch):
    publish = Mock()
    monkeypatch.setattr(send_email, "apply_async", publish)
    return publish


@pytest.fixture
def auth_engine(tmp_path):
    url = os.environ.get("SEAL_TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    if not url.startswith("sqlite"):
        database = make_url(url).database or ""
        if not database.startswith("seal_test_"):
            pytest.fail("Integration tests require a dedicated seal_test_* database")
    engine = create_async_engine(url, poolclass=NullPool)
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    async def create_tables():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def cleanup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(create_tables())
    try:
        yield engine
    finally:
        asyncio.run(cleanup())


@pytest.fixture
def auth_client(auth_engine, auth_settings, email_queue):
    factory = async_sessionmaker(auth_engine, expire_on_commit=False)

    async def database():
        async with factory() as session:
            yield session

    async def no_rate_limit():
        pass

    previous = api.dependency_overrides.copy()
    api.dependency_overrides[get_db] = database
    api.dependency_overrides[get_settings] = lambda: auth_settings
    api.dependency_overrides[rate_limit_auth] = no_rate_limit
    try:
        with TestClient(app) as client:
            yield client
    finally:
        api.dependency_overrides.clear()
        api.dependency_overrides.update(previous)
