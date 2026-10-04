import os
from pathlib import Path
from typing import Optional

from core.events.bus import EventBus
from core.events.store import InMemoryEventStore
from core.missions.manager import MissionManager
from core.tasks.manager import TaskManager
from core.policies.models import PolicyConfig
from memory.store import MemoryStore
from agents.registry import AgentRegistry
from supervisor.telemetry import TelemetryTracker
from supervisor.approvals import ApprovalManager
from supervisor.engine import SupervisorEngine
from supervisor.reasoning import SupervisoryReasoner
from execution.manager import ExecutionManager
from integrations.nebius.provider import NebiusNemotronProvider, MockReasoningProvider
from integrations.jenkins.client import JenkinsHttpClient
from integrations.jenkins.mock import MockJenkinsProvider


from storage.sqlite import (
    DatabaseManager,
    MissionRepository,
    TaskRepository,
    AgentRepository,
    EventRepository,
    MemoryRepository,
    ApprovalRepository,
    VerificationRepository,
    HandoffRepository,
)


class AppState:
    """Singleton application state holding core services."""
    def __init__(self):
        self.event_bus = EventBus()
        # Persist events to supervisor_events.jsonl in workspace (backward compatibility)
        self.event_store = InMemoryEventStore(persistence_file=Path("./supervisor_events.jsonl"))

        # SQLite WAL local-first persistence kernel
        db_path = os.getenv("SUPERVISOR_DB_PATH", "./supervisor.db")
        self.db = DatabaseManager(db_path=db_path)
        self.mission_repo = MissionRepository(self.db)
        self.task_repo = TaskRepository(self.db)
        self.agent_repo = AgentRepository(self.db)
        self.event_repo = EventRepository(self.db)
        self.memory_repo = MemoryRepository(self.db)
        self.approval_repo = ApprovalRepository(self.db)
        self.verification_repo = VerificationRepository(self.db)
        self.handoff_repo = HandoffRepository(self.db)

        self.mission_manager = MissionManager(event_bus=self.event_bus, repository=self.mission_repo)
        self.task_manager = TaskManager(event_bus=self.event_bus, repository=self.task_repo)
        self.policy_config = PolicyConfig()

        # Wire event store (jsonl) and SQLite event repository to record all published events
        self.event_bus._global_subscribers.append(self.event_store.append)
        self.event_bus.subscribe_sync(self._sqlite_event_sink)

        # Control Plane Subsystems
        self.memory_store = MemoryStore(event_bus=self.event_bus)
        self.agent_registry = AgentRegistry(event_bus=self.event_bus, repository=self.agent_repo)
        self.telemetry = TelemetryTracker(event_bus=self.event_bus)
        self.approval_manager = ApprovalManager(event_bus=self.event_bus)

        # Execution & Isolation Managers
        from execution.worktree import GitWorktreeManager
        from adapters.registry import AdapterRegistry
        from adapters.claude_code import ClaudeCodeAdapter
        from adapters.codex import CodexAdapter
        from supervisor.watchdogs import WatchdogEngine, InterventionController
        from core.handoff import HandoffEngine

        self.worktree_manager = GitWorktreeManager(repo_root=Path("."))
        self.adapter_registry = AdapterRegistry()
        self.claude_adapter = ClaudeCodeAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
        )
        self.adapter_registry.register_adapter(self.claude_adapter)

        self.codex_adapter = CodexAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
        )
        self.adapter_registry.register_adapter(self.codex_adapter)

        # Supervisory Watchdog Engine & Intervention Controller (Phase 3)
        self.watchdog_engine = WatchdogEngine(policy=self.policy_config)
        self.intervention_controller = InterventionController(
            watchdog_engine=self.watchdog_engine,
            adapter_registry=self.adapter_registry,
            event_bus=self.event_bus,
            approval_repo=self.approval_repo,
            event_repo=self.event_repo,
        )

        # Independent Verification Engine (Phase 4)
        from core.verification.engine import VerificationEngine
        self.verification_engine = VerificationEngine(
            event_bus=self.event_bus,
            repository=self.verification_repo,
            task_manager=self.task_manager,
            worktree_manager=self.worktree_manager,
        )

        # Handoff Engine (Phase 5)
        self.handoff_engine = HandoffEngine(
            event_bus=self.event_bus,
            adapter_registry=self.adapter_registry,
            handoff_repo=self.handoff_repo,
            task_manager=self.task_manager,
            worktree_manager=self.worktree_manager,
            verification_engine=self.verification_engine,
            max_handoffs_per_task=int(os.getenv("SUPERVISOR_MAX_HANDOFFS_PER_TASK", "3")),
        )

        # Execution Manager (Docker sandboxing + local process fallback)
        self.execution_manager = ExecutionManager(event_bus=self.event_bus)


        # Reasoning Provider (Nebius Nemotron when API key configured, otherwise deterministic mock)
        if os.getenv("NEBIUS_API_KEY"):
            self.reasoning_provider = NebiusNemotronProvider()
        else:
            self.reasoning_provider = MockReasoningProvider()
        self.reasoner = SupervisoryReasoner(provider=self.reasoning_provider)

        # Jenkins Provider (HTTP client when URL configured, otherwise deterministic mock)
        if os.getenv("JENKINS_URL") and os.getenv("JENKINS_URL") != "mock":
            self.jenkins_client = JenkinsHttpClient()
        else:
            self.jenkins_client = MockJenkinsProvider()

        # Supervisor Engine
        self.supervisor_engine = SupervisorEngine(
            event_bus=self.event_bus,
            mission_manager=self.mission_manager,
            task_manager=self.task_manager,
            policy=self.policy_config,
            reasoner=self.reasoner,
            registry=self.agent_registry,
            telemetry=self.telemetry,
            approval_manager=self.approval_manager,
        )

    async def _sqlite_event_sink(self, event: Any) -> None:
        """Asynchronously persists event bus stream to SQLite without blocking handlers."""
        try:
            await self.event_repo.append(event)
        except Exception:
            pass


# Global instance
app_state = AppState()

