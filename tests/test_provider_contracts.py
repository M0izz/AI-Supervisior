import asyncio
import os
import pytest
from pathlib import Path
from core.events.bus import EventBus
from core.protocol.schema import TaskDispatchPackage
from adapters.base import AgentAdapter
from adapters.models import (
    AdapterCapability,
    AdapterAvailabilityStatus,
    AdapterProcessStatus,
    RuntimeType,
    ExecutionMode,
)
from adapters.claude_code import ClaudeCodeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter
from adapters.qwen import QwenAdapter
from adapters.opencode import OpenCodeAdapter
from adapters.kimi import KimiAdapter
from adapters.hermes import HermesAdapter
from adapters.digitalocean_agent import DigitalOceanManagedAgentAdapter
from adapters.goose import GooseAdapter
from adapters.cline import ClineAdapter
from adapters.custom import CustomAgentAdapter, CustomAgentRegistration
from integrations.digitalocean import DigitalOceanProvider, DigitalOceanClient, GemmaReasoner
from integrations.nebius.provider import NebiusNemotronProvider


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def sample_dispatch():
    return TaskDispatchPackage(
        mission_id="msn_contract_test",
        task_id="TASK-CONTRACT-01",
        objective="Run standardized provider contract verification",
        workspace=".",
        allowed_files=["src/test.py"],
        dependencies=[],
        context={"repo": "contract-validation"},
        verification_requirements=["pytest test_contract.py"],
        timeout_seconds=30
    )


def get_all_adapters(event_bus):
    return [
        ClaudeCodeAdapter(event_bus=event_bus),
        CodexAdapter(event_bus=event_bus),
        GeminiAdapter(event_bus=event_bus),
        QwenAdapter(event_bus=event_bus),
        OpenCodeAdapter(event_bus=event_bus),
        KimiAdapter(event_bus=event_bus),
        HermesAdapter(event_bus=event_bus),
        DigitalOceanManagedAgentAdapter(event_bus=event_bus),
        GooseAdapter(event_bus=event_bus),
        ClineAdapter(event_bus=event_bus),
        CustomAgentAdapter(
            registration=CustomAgentRegistration(
                name="Mock Custom Tester",
                adapter_id="mock_custom",
                command_or_endpoint="python --version",
                capabilities=[AdapterCapability.CODE_EXECUTION.value]
            ),
            event_bus=event_bus
        ),
    ]


@pytest.mark.asyncio
async def test_all_adapters_contract_identity(event_bus):
    """Verifies that every adapter adheres to the universal identity schema."""
    adapters = get_all_adapters(event_bus)
    for adapter in adapters:
        ident = adapter.identity
        assert ident.adapter_id, f"Adapter {adapter} missing adapter_id"
        assert ident.display_name, f"Adapter {ident.adapter_id} missing display_name"
        assert ident.provider, f"Adapter {ident.adapter_id} missing provider"
        assert isinstance(ident.capabilities, list)
        assert len(ident.capabilities) > 0, f"Adapter {ident.adapter_id} declared 0 capabilities"
        assert ident.runtime_type in (RuntimeType.AGENT_RUNTIME, RuntimeType.MODEL, RuntimeType.INFRASTRUCTURE)
        assert ident.execution_mode in (ExecutionMode.LOCAL_PROCESS, ExecutionMode.REMOTE_MANAGED, ExecutionMode.SERVERLESS_INFERENCE)


@pytest.mark.asyncio
async def test_all_adapters_contract_availability_probe(event_bus):
    """Verifies that every adapter implements non-crashing availability checking (offline-safe)."""
    adapters = get_all_adapters(event_bus)
    for adapter in adapters:
        avail = await adapter.check_availability()
        assert avail.status in AdapterAvailabilityStatus
        assert isinstance(avail.available, bool)
        assert isinstance(avail.message, str)


@pytest.mark.asyncio
async def test_all_adapters_contract_prepare(event_bus, sample_dispatch):
    """Verifies pre-flight validation on every adapter."""
    adapters = get_all_adapters(event_bus)
    for adapter in adapters:
        prep_ok = await adapter.prepare(sample_dispatch)
        assert prep_ok is True


@pytest.mark.asyncio
async def test_all_adapters_contract_lifecycle(event_bus, sample_dispatch):
    """Verifies status, cancel, and cleanup contracts across all adapters."""
    adapters = get_all_adapters(event_bus)
    for adapter in adapters:
        tid = f"task_{adapter.identity.adapter_id}"
        # Status before run
        st = await adapter.status(tid)
        assert st in (AdapterProcessStatus.PENDING, AdapterProcessStatus.STARTING)

        # Cancel returns bool (True if running process killed, False if already stopped/not found)
        cancelled = await adapter.cancel(tid)
        assert isinstance(cancelled, bool)

        # Cleanup releases handles
        await adapter.cleanup(tid)


@pytest.mark.asyncio
async def test_hermes_extended_session_lifecycle(event_bus):
    """Verifies persistent session methods (attach, resume, pause, disconnect, reconnect)."""
    hermes = HermesAdapter(event_bus=event_bus)
    session_id = "test_hermes_sess"
    hermes._active_sessions[session_id] = {"status": "INITIALIZED", "attached": True}

    assert await hermes.attach(session_id) is True
    assert await hermes.pause(session_id) is True
    assert hermes._active_sessions[session_id]["status"] == "PAUSED"
    assert await hermes.resume(session_id) is True
    assert hermes._active_sessions[session_id]["status"] == "RUNNING"
    assert await hermes.disconnect(session_id) is True
    assert hermes._active_sessions[session_id]["attached"] is False
    assert await hermes.reconnect(session_id) is True
    assert hermes._active_sessions[session_id]["attached"] is True


@pytest.mark.asyncio
async def test_digitalocean_provider_and_action_gateway():
    """Verifies DigitalOcean provider descriptor and Action Gateway security enforcement."""
    do_provider = DigitalOceanProvider()
    desc = await do_provider.get_descriptor()
    assert desc.provider_id == "digitalocean"
    assert "action_gateway" in desc.capabilities
    assert desc.action_gateway_support is True

    # Test Action Gateway safety check: safe tool
    safe_call = await do_provider.govern_tool_call(
        tool_name="git_status",
        arguments={"dir": "."},
        agent_id="hermes",
        workspace="."
    )
    assert safe_call.is_safe is True
    assert safe_call.requires_approval is False

    # Test Action Gateway safety check: dangerous tool
    dangerous_call = await do_provider.govern_tool_call(
        tool_name="delete_files",
        arguments={"target": "src/*"},
        agent_id="hermes",
        workspace="."
    )
    assert dangerous_call.is_safe is False
    assert dangerous_call.requires_approval is True

    # Test Action Gateway safety check: path traversal
    traversal_call = await do_provider.govern_tool_call(
        tool_name="read_file",
        arguments={"path": "../../../etc/passwd"},
        agent_id="hermes",
        workspace="."
    )
    assert traversal_call.is_safe is False


@pytest.mark.asyncio
async def test_gemma_reasoner_decomposition():
    """Verifies Gemma 4 planning & goal decomposition."""
    gemma = GemmaReasoner()
    out = await gemma.decompose_goal("Fix authentication session refresh bug")
    assert out.goal_summary == "Fix authentication session refresh bug"
    assert len(out.suggested_steps) >= 3
    assert out.suggested_agent in ("claude_code", "codex", "hermes")
    assert "Gemma 4" in out.model_provenance


@pytest.mark.asyncio
async def test_nebius_dynamic_catalog():
    """Verifies Nebius Token Factory dynamic model discovery."""
    nebius = NebiusNemotronProvider()
    models = await nebius.query_models()
    assert len(models) >= 4
    model_ids = [m["model_id"] for m in models]
    assert any("nemotron" in mid.lower() for mid in model_ids)
    assert any("hermes" in mid.lower() for mid in model_ids)
