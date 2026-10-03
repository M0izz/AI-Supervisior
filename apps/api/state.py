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


class AppState:
    """Singleton application state holding core services."""
    def __init__(self):
        self.event_bus = EventBus()
        # Persist events to supervisor_events.jsonl in workspace
        self.event_store = InMemoryEventStore(persistence_file=Path("./supervisor_events.jsonl"))
        self.mission_manager = MissionManager(event_bus=self.event_bus)
        self.task_manager = TaskManager(event_bus=self.event_bus)
        self.policy_config = PolicyConfig()

        # Wire event store to automatically record all published events
        self.event_bus._global_subscribers.append(self.event_store.append)

        # Control Plane Subsystems
        self.memory_store = MemoryStore(event_bus=self.event_bus)
        self.agent_registry = AgentRegistry(event_bus=self.event_bus)
        self.telemetry = TelemetryTracker(event_bus=self.event_bus)
        self.approval_manager = ApprovalManager(event_bus=self.event_bus)

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
            approval_manager=self.approval_manager
        )


# Global instance
app_state = AppState()
