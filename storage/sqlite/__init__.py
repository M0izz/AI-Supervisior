"""
Storage subsystem for AI Supervisor.
Provides durable, local-first persistence layers.
"""

from storage.sqlite.db import DatabaseManager
from storage.sqlite.repositories import (
    MissionRepository,
    TaskRepository,
    AgentRepository,
    EventRepository,
    MemoryRepository,
    ApprovalRepository,
    VerificationRepository,
    HandoffRepository,
    RoutingRepository,
    AbsenceRepository,
    attach_sqlite_persistence,
)
from storage.sqlite.sync_repo import SyncRepository

__all__ = [
    "DatabaseManager",
    "MissionRepository",
    "TaskRepository",
    "AgentRepository",
    "EventRepository",
    "MemoryRepository",
    "ApprovalRepository",
    "VerificationRepository",
    "HandoffRepository",
    "RoutingRepository",
    "AbsenceRepository",
    "SyncRepository",
    "attach_sqlite_persistence",
]

