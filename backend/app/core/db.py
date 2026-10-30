from collections.abc import AsyncIterator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

engine = create_async_engine(str(get_settings().database_url), pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
sync_engine = create_engine(
    str(get_settings().database_url).replace("postgresql+asyncpg://", "postgresql+psycopg://", 1),
    pool_pre_ping=True,
)
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
