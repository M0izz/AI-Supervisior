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
    PlanRepository,
    TaskRepository,
    AgentRepository,
    EventRepository,
    MemoryRepository,
    ApprovalRepository,
    VerificationRepository,
    HandoffRepository,
    RoutingRepository,
    AbsenceRepository,
    SyncRepository,
)
from core.absence import AbsencePolicyEngine
from sync import SyncServerStore, SyncEngine, derive_project_id, Device, DeviceStatus
from storage.graph import FalkorDBClient, FalkorDBGraphRepository


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
        self.plan_repo = PlanRepository(self.db)
        self.task_repo = TaskRepository(self.db)
        self.agent_repo = AgentRepository(self.db)
        self.event_repo = EventRepository(self.db)
        self.memory_repo = MemoryRepository(self.db)
        self.approval_repo = ApprovalRepository(self.db)
        self.verification_repo = VerificationRepository(self.db)
        self.handoff_repo = HandoffRepository(self.db)
        self.routing_repo = RoutingRepository(self.db)
        self.absence_repo = AbsenceRepository(self.db)
        self.sync_repo = SyncRepository(self.db)

        # FalkorDB Authoritative Graph Memory & Coordination Layer
        self.falkordb_client = FalkorDBClient()
        self.graph_repo = FalkorDBGraphRepository(self.falkordb_client)
        self.graph_repo.initialize_schema()

        # Cloud Sync & Multi-Device Subsystem (Phase 12)
        self.sync_server = SyncServerStore()
        self.device_id = os.getenv("SUPERVISOR_DEVICE_ID", "dev_local_primary")
        self.device_token = os.getenv("SUPERVISOR_DEVICE_TOKEN", "tok_local_primary_sec")
        self.project_id = os.getenv("SUPERVISOR_PROJECT_ID") or derive_project_id()
        self.sync_engine = SyncEngine(
            db=self.db,
            sync_repo=self.sync_repo,
            server_store=self.sync_server,
            device_id=self.device_id,
            device_token=self.device_token,
            project_id=self.project_id,
        )

        self.mission_manager = MissionManager(
            event_bus=self.event_bus,
            repository=self.mission_repo,
            graph_repository=self.graph_repo,
        )
        self.task_manager = TaskManager(
            event_bus=self.event_bus,
            repository=self.task_repo,
            graph_repository=self.graph_repo,
        )
        self.policy_config = PolicyConfig()
        self.absence_engine = AbsencePolicyEngine(repository=self.absence_repo, event_bus=self.event_bus)

        # Wire event store (jsonl), SQLite, and FalkorDB graph event sinks
        self.event_bus._global_subscribers.append(self.event_store.append)
        self.event_bus.subscribe_sync(self._sqlite_event_sink)
        self.event_bus.subscribe_sync(self._falkordb_event_sink)

        # Control Plane Subsystems
        self.memory_store = MemoryStore(event_bus=self.event_bus, repository=self.memory_repo)
        self.agent_registry = AgentRegistry(event_bus=self.event_bus, repository=self.agent_repo)
        self.telemetry = TelemetryTracker(event_bus=self.event_bus)
        self.approval_manager = ApprovalManager(event_bus=self.event_bus)

        # Execution & Isolation Managers
        from execution.worktree import GitWorktreeManager
        from adapters.registry import AdapterRegistry
        from adapters.claude_code import ClaudeCodeAdapter
        from adapters.codex import CodexAdapter
        from adapters.gemini import GeminiAdapter
        from adapters.qwen import QwenAdapter
        from adapters.opencode import OpenCodeAdapter
        from adapters.kimi import KimiAdapter
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

        self.gemini_adapter = GeminiAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
        )
        self.adapter_registry.register_adapter(self.gemini_adapter)

        self.qwen_adapter = QwenAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
        )
        self.adapter_registry.register_adapter(self.qwen_adapter)

        self.opencode_adapter = OpenCodeAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
        )
        self.adapter_registry.register_adapter(self.opencode_adapter)

        self.kimi_adapter = KimiAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
        )
        self.adapter_registry.register_adapter(self.kimi_adapter)

        # Extended Provider Ecosystem (Hermes, DigitalOcean, Goose, Cline)
        from adapters.hermes import HermesAdapter
        from adapters.digitalocean_agent import DigitalOceanManagedAgentAdapter
        from adapters.goose import GooseAdapter
        from adapters.cline import ClineAdapter
        from integrations.digitalocean import DigitalOceanProvider, DigitalOceanClient, GemmaReasoner
        from integrations.gemini import GeminiProvider, GeminiClient, GeminiReasoner

        self.digitalocean_client = DigitalOceanClient()
        self.digitalocean_provider = DigitalOceanProvider(client=self.digitalocean_client)
        self.gemma_reasoner = GemmaReasoner(client=self.digitalocean_client)

        self.gemini_client = GeminiClient()
        self.gemini_provider = GeminiProvider(client=self.gemini_client)
        self.gemini_reasoner = GeminiReasoner(client=self.gemini_client)

        from integrations.openrouter import OpenRouterProvider, OpenRouterClient, OpenRouterReasoner
        from integrations.backboard import BackboardProvider, BackboardClient

        self.openrouter_client = OpenRouterClient()
        self.openrouter_provider = OpenRouterProvider(client=self.openrouter_client)
        self.openrouter_reasoner = OpenRouterReasoner(client=self.openrouter_client)

        self.backboard_client = BackboardClient()
        self.backboard_provider = BackboardProvider(client=self.backboard_client)

        from integrations.huggingface import HuggingFaceProvider, HuggingFaceClient

        self.huggingface_client = HuggingFaceClient()
        self.huggingface_provider = HuggingFaceProvider(client=self.huggingface_client)

        self.hermes_adapter = HermesAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
        )
        self.adapter_registry.register_adapter(self.hermes_adapter)

        self.do_agent_adapter = DigitalOceanManagedAgentAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
            provider=self.digitalocean_provider,
        )
        self.adapter_registry.register_adapter(self.do_agent_adapter)

        self.goose_adapter = GooseAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
        )
        self.adapter_registry.register_adapter(self.goose_adapter)

        self.cline_adapter = ClineAdapter(
            event_bus=self.event_bus,
            worktree_manager=self.worktree_manager,
        )
        self.adapter_registry.register_adapter(self.cline_adapter)

        # Supervisory Watchdog Engine & Intervention Controller (Phase 3)
        self.watchdog_engine = WatchdogEngine(policy=self.policy_config)
        self.intervention_controller = InterventionController(
            watchdog_engine=self.watchdog_engine,
            adapter_registry=self.adapter_registry,
            event_bus=self.event_bus,
            approval_repo=self.approval_repo,
            event_repo=self.event_repo,
        )

        # Independent Verification Engine (Phase 4 + Phase 7 Memory Integration + FalkorDB)
        from core.verification.engine import VerificationEngine
        self.verification_engine = VerificationEngine(
            event_bus=self.event_bus,
            repository=self.verification_repo,
            task_manager=self.task_manager,
            worktree_manager=self.worktree_manager,
            memory_store=self.memory_store,
            graph_repository=self.graph_repo,
        )

        # Dynamic Agent Router (Phase 6 + Phase 7 Memory Integration)
        from core.routing import RoutingEngine
        self.routing_engine = RoutingEngine(
            adapter_registry=self.adapter_registry,
            routing_repo=self.routing_repo,
            verification_repo=self.verification_repo,
            handoff_repo=self.handoff_repo,
            event_bus=self.event_bus,
            memory_store=self.memory_store,
        )

        # Handoff Engine (Phase 5 + Phase 6 Dynamic Routing + Phase 7 Memory Integration + FalkorDB)
        self.handoff_engine = HandoffEngine(
            event_bus=self.event_bus,
            adapter_registry=self.adapter_registry,
            handoff_repo=self.handoff_repo,
            task_manager=self.task_manager,
            worktree_manager=self.worktree_manager,
            verification_engine=self.verification_engine,
            routing_engine=self.routing_engine,
            memory_store=self.memory_store,
            graph_repository=self.graph_repo,
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

        # Jenkins Provider (HTTP client when URL configured and enabled, otherwise deterministic mock)
        if os.getenv("JENKINS_ENABLED", "false").lower() == "true" and os.getenv("JENKINS_URL") and os.getenv("JENKINS_URL") != "mock":
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

        # Mission Runner Orchestrator
        from execution.mission_runner import MissionRunner
        self.mission_runner = MissionRunner(self)


    async def _sqlite_event_sink(self, event: Any) -> None:
        """Asynchronously persists event bus stream to SQLite without blocking handlers."""
        try:
            await self.event_repo.append(event)
        except Exception:
            pass

    async def _falkordb_event_sink(self, event: Any) -> None:
        """Streams relevant execution events and lifecycle entities to FalkorDB property graph."""
        try:
            task_id = getattr(event, "task_id", None)
            mission_id = getattr(event, "mission_id", None)
            agent_id = getattr(event, "agent_id", None)
            if not getattr(event, "type", None):
                return

            evt_type = event.type.value if hasattr(event.type, "value") else str(event.type)
            payload = getattr(event, "payload", {}) or {}
            attempt = payload.get("attempt", 1)
            exec_id = f"exec_{task_id}_{attempt}" if task_id else None
            evt_id = getattr(event, "id", None) or f"evt_{task_id or 'gen'}_{int(datetime.now(timezone.utc).timestamp())}"
            severity = event.severity.value if hasattr(event.severity, "value") else str(getattr(event, "severity", "INFO"))
            ts = getattr(event, "timestamp", None)
            ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")

            # 1. Lifecycle event dispatching to graph
            if evt_type == "task.started" and task_id:
                await self.graph_repo.record_execution_start(
                    execution_id=exec_id,
                    task_id=task_id,
                    mission_id=mission_id,
                    agent_id=agent_id or "worker_01",
                    attempt_number=attempt,
                )
            elif evt_type == "task.failed" and task_id and exec_id:
                await self.graph_repo.record_execution_failure(
                    execution_id=exec_id,
                    error_signature=payload.get("error_signature", "ExecutionFailed"),
                    reason=payload.get("reason"),
                    event_id=evt_id,
                )
            elif evt_type == "task.completed" and task_id and exec_id:
                await self.graph_repo.record_execution_success(
                    execution_id=exec_id,
                    summary=payload.get("summary", "Task completed"),
                    artifacts=payload.get("artifacts"),
                )
            elif (evt_type == "supervisor.decision" or "decision" in evt_type) and task_id:
                dec_id = payload.get("decision_id") or f"dec_{task_id}_{attempt}"
                await self.graph_repo.record_decision(
                    decision_id=dec_id,
                    mission_id=mission_id or "",
                    task_id=task_id,
                    decision_type=payload.get("decision_type", "SUPERVISORY_DECISION"),
                    action=payload.get("action", "RESOLVED"),
                    reason=payload.get("reason", "Automated supervisory decision"),
                    responding_to_event_id=payload.get("responding_to_event_id"),
                    selected_agent_id=payload.get("selected_agent_id") or agent_id,
                )
            elif evt_type == "verification.result" and task_id:
                ver_id = payload.get("verification_id") or f"ver_{task_id}_{attempt}"
                await self.graph_repo.record_verification(
                    verification_id=ver_id,
                    task_id=task_id,
                    mission_id=mission_id or "",
                    decision=payload.get("decision", "ACCEPT"),
                    summary=payload.get("summary", "Verified"),
                    evidence_items=payload.get("evidence_items"),
                    execution_id=exec_id,
                )

            # 2. Also emit execution event record if task-scoped
            if task_id and exec_id:
                await self.graph_repo.record_execution_event(
                    execution_id=exec_id,
                    event_id=evt_id,
                    event_type=evt_type,
                    severity=severity,
                    payload=payload,
                    timestamp=ts_str or None,
                )
        except Exception:
            pass


# Global instance
app_state = AppState()


