"""Persistence layer for Lead Hunter."""
from lead_hunter.persistence.factory import create_persistence, create_persistence_sync
from lead_hunter.persistence.in_memory import InMemoryPersistence
from lead_hunter.persistence.database import DatabaseManager
from lead_hunter.persistence.sql_adapter import SQLPersistence

__all__ = [
    "create_persistence",
    "create_persistence_sync",
    "InMemoryPersistence",
    "DatabaseManager",
    "SQLPersistence",
]
