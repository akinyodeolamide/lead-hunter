"""Persistence factory for creating the appropriate persistence adapter."""
from __future__ import annotations

import os
from typing import Any

from lead_hunter.config.config import PersistenceConfig
from lead_hunter.logging_config import get_logger
from lead_hunter.orchestrator.interfaces import Persistence
from lead_hunter.persistence.database import DatabaseManager
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.persistence.sql_adapter import SQLPersistence

logger = get_logger("persistence_factory")


async def create_persistence(
    database_url: str | None = None,
    config: PersistenceConfig | None = None,
) -> Persistence:
    """Create and initialize the appropriate persistence adapter.

    Priority:
    1. Explicit database_url parameter
    2. Explicit config parameter
    3. DATABASE_URL environment variable
    4. Fallback to InMemoryPersistence

    Args:
        database_url: Optional explicit database URL.
        config: Optional persistence configuration.

    Returns:
        Initialized Persistence instance.
    """
    resolved_url = database_url or (config.database_url if config else None) or os.environ.get("DATABASE_URL")

    if resolved_url:
        logger.info(f"Initializing SQL persistence with database: {resolved_url.split('://')[0]}://***")
        pers_config = config or PersistenceConfig(database_url=resolved_url)
        db_manager = DatabaseManager(pers_config)
        db_manager.initialize()
        await db_manager.create_tables()
        return SQLPersistence(db_manager)

    logger.info("No DATABASE_URL configured; using InMemoryPersistence")
    return InMemoryPersistence()


def create_persistence_sync(
    database_url: str | None = None,
    config: PersistenceConfig | None = None,
) -> Persistence:
    """Synchronous version of create_persistence for non-async contexts.

    This creates the persistence adapter without initializing tables.
    Callers must ensure tables exist (e.g., via alembic migrate).

    Args:
        database_url: Optional explicit database URL.
        config: Optional persistence configuration.

    Returns:
        Persistence instance (not fully initialized for SQL).
    """
    import asyncio

    resolved_url = database_url or (config.database_url if config else None) or os.environ.get("DATABASE_URL")

    if resolved_url:
        logger.info(f"Initializing SQL persistence (sync) with database: {resolved_url.split('://')[0]}://***")
        pers_config = config or PersistenceConfig(database_url=resolved_url)
        db_manager = DatabaseManager(pers_config)
        db_manager.initialize()
        # Run table creation in a temporary event loop if needed
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an async context, return without creating tables
            # The caller is responsible for async initialization
            return SQLPersistence(db_manager)
        except RuntimeError:
            # No running loop — safe to create one
            asyncio.run(db_manager.create_tables())
            return SQLPersistence(db_manager)

    logger.info("No DATABASE_URL configured; using InMemoryPersistence")
    return InMemoryPersistence()
