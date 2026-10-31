import asyncio

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.core.db import Base
from app.modules.auth import models  # noqa: F401
from app.modules.events import models as event_models  # noqa: F401
from app.modules.judging import models as judging_models  # noqa: F401
from app.modules.submissions import models as submission_models  # noqa: F401
from app.modules.teams import models as team_models  # noqa: F401

# Import model của từng module tại đây khi thêm bảng để autogenerate nhận diện.
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=str(get_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    engine = create_async_engine(str(get_settings().database_url), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
