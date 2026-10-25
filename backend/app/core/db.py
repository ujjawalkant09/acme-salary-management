from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


# `postgresql+psycopg` runs on psycopg's own async mode, so Alembic and the app share one URL.
engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. Services commit at the end of their work; anything
    left uncommitted (for example after an error) is rolled back here."""
    async with SessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()
