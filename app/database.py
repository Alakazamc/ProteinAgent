from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from .config import load_config

# Load configuration (assumes single app start lifecycle)
config = load_config()

# Create SQLAlchemy async engine
engine = create_async_engine(
    config.db_url,
    echo=False,  # Set to True for SQL query logging
    connect_args={"check_same_thread": False} if "sqlite" in config.db_url else {},
)

# Create an async session maker
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    """FastAPI Dependency for getting an async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def initialize_database() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_schema_patches)


def _apply_schema_patches(sync_conn) -> None:
    inspector = sa.inspect(sync_conn)
    if not inspector.has_table("agent_executions"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("agent_executions")}
    patch_statements = []

    if "matched_keywords" not in existing_columns:
        patch_statements.append(
            "ALTER TABLE agent_executions ADD COLUMN matched_keywords JSON"
        )
    if "trace_events" not in existing_columns:
        patch_statements.append(
            "ALTER TABLE agent_executions ADD COLUMN trace_events JSON"
        )

    for statement in patch_statements:
        sync_conn.exec_driver_sql(statement)
