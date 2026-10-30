from types import SimpleNamespace

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core import config


def test_auth_migration_upgrade_schema_and_downgrade(tmp_path, monkeypatch):
    path = tmp_path / "migration.db"
    monkeypatch.setattr(
        config, "get_settings", lambda: SimpleNamespace(database_url=f"sqlite+aiosqlite:///{path}")
    )
    alembic = Config("alembic.ini")
    command.upgrade(alembic, "head")
    command.check(alembic)
    engine = create_engine(f"sqlite:///{path}")
    try:
        tables = inspect(engine).get_table_names()
        assert {"users", "password_reset_tokens", "audit_logs", "event_roles"} <= set(tables)
        command.downgrade(alembic, "0002_auth")
        tables = inspect(engine).get_table_names()
        assert (
            "users" in tables
            and "audit_logs" not in tables
            and "password_reset_tokens" not in tables
        )
        command.upgrade(alembic, "head")
        command.check(alembic)
    finally:
        engine.dispose()
