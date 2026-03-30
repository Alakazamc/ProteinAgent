from __future__ import annotations

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
