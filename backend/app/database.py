"""Async SQLAlchemy engine + session factory (spec F2: PostgreSQL)."""
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Declarative base class all ORM models inherit from."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a request-scoped async DB session."""
    async with SessionLocal() as session:
        yield session


# Columns added to models AFTER their table may already exist somewhere.
# create_all only creates missing TABLES — it silently skips new columns,
# which then 500s every query on that table. Until we move to Alembic, list
# such columns here; each is applied idempotently on boot (the ALTER simply
# fails and rolls back if the column is already there).
_COLUMN_BOOTSTRAP = [
    # Added 2026-07-13 (gamification / configurable protein multiplier):
    "ALTER TABLE nutrition_profiles ADD COLUMN protein_multiplier "
    "FLOAT NOT NULL DEFAULT 1.52",
]


async def init_models() -> None:
    """Create tables if they don't exist. For real deploys use Alembic migrations;
    this is a convenience bootstrap for the Increment-1 build."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    for stmt in _COLUMN_BOOTSTRAP:
        try:
            # Each ALTER gets its own transaction: on Postgres a failed
            # statement poisons the whole transaction, so it can't share one
            # with create_all (or with the other ALTERs).
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception:
            pass  # column already exists — expected on every boot after the first
