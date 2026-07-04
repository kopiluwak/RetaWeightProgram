"""Async SQLAlchemy engine + session factory (spec F2: PostgreSQL)."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    """Create tables if they don't exist. For real deploys use Alembic migrations;
    this is a convenience bootstrap for the Increment-1 build."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
