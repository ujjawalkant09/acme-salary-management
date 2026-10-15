from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> AsyncEngine:
    """`DATABASE_URL` keeps its sync form, which Alembic uses as is. SQLite runs on
    aiosqlite; `postgresql+psycopg` uses psycopg's own async mode."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        # A SQLite connection is cheap to open, and not pooling keeps each one on the event
        # loop that opened it (the test client runs the app on a loop of its own).
        engine = create_async_engine(parsed.set(drivername="sqlite+aiosqlite"), poolclass=NullPool)

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_async_engine(parsed, pool_pre_ping=True)


engine = make_engine(get_settings().database_url)
SessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. Services commit at the end of their work; anything
    left uncommitted (for example after an error) is rolled back here."""
    async with SessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()
