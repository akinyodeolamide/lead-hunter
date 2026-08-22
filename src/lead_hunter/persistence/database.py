"""Database manager with SQLAlchemy ORM."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from lead_hunter.config.config import PersistenceConfig
from lead_hunter.exceptions import PersistenceError


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, config: PersistenceConfig) -> None:
        self.config = config
        self._engine = None
        self._session_factory = None

    def _make_url(self, url: str) -> str:
        """Convert SQLite URL to async variant if needed."""
        if url.startswith("sqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return url

    def initialize(self) -> None:
        """Initialize the database engine."""
        url = self._make_url(self.config.database_url)
        self._engine = create_async_engine(
            url,
            echo=self.config.echo_sql,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def close(self) -> None:
        """Close the database engine."""
        if self._engine:
            await self._engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide an async database session."""
        if not self._session_factory:
            raise PersistenceError("Database not initialized")
        async with self._session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    async def create_tables(self) -> None:
        """Create all tables from ORM models."""
        from lead_hunter.persistence.orm_models import Base
        if not self._engine:
            raise PersistenceError("Database not initialized")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self) -> None:
        """Drop all tables (for testing)."""
        from lead_hunter.persistence.orm_models import Base
        if not self._engine:
            raise PersistenceError("Database not initialized")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
