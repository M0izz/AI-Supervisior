import asyncio
import logging
from typing import Dict, List, Optional

from adapters.base import AgentAdapter
from adapters.models import (
    AdapterIdentity,
    AdapterAvailability,
    ProviderDescriptor,
    ModelDescriptor,
    RuntimeType,
    ExecutionMode,
)

logger = logging.getLogger("supervisor.adapters.registry")


class AdapterRegistry:
    """
    Registry for external Agent Adapters, Infrastructure Providers, and Model Catalogs.
    Allows discovery, capability queries, and lifecycle invocation across
    diverse agent backends (Claude Code, OpenAI Codex, Gemini CLI, Hermes, Nebius, Qwen, etc.).
    """

    def __init__(self):
        self._adapters: Dict[str, AgentAdapter] = {}
        self._providers: Dict[str, ProviderDescriptor] = {}
        self._models: Dict[str, ModelDescriptor] = {}
        self._lock = asyncio.Lock()

    def register_adapter(self, adapter: AgentAdapter) -> None:
        """Registers an adapter instance."""
        adapter_id = adapter.identity.adapter_id
        self._adapters[adapter_id] = adapter
        logger.info(f"[ADAPTER_REGISTRY] Registered adapter '{adapter_id}' ({adapter.identity.display_name})")

    def get_adapter(self, adapter_id: str) -> Optional[AgentAdapter]:
        """Retrieves an adapter by ID."""
        return self._adapters.get(adapter_id)

    def list_adapters(self) -> List[AdapterIdentity]:
        """Returns identity descriptors for all registered adapters."""
        return [adapter.identity for adapter in self._adapters.values()]

    def find_by_capability(self, capability: str) -> List[AgentAdapter]:
        """Returns all adapters that declare support for the given capability."""
        cap_lower = capability.lower()
        return [
            adapter for adapter in self._adapters.values()
            if any(c.lower() == cap_lower for c in adapter.capabilities)
        ]

    def find_by_runtime_type(self, runtime_type: RuntimeType) -> List[AgentAdapter]:
        """Filters adapters by RuntimeType (agent_runtime, model, infrastructure)."""
        return [
            adapter for adapter in self._adapters.values()
            if adapter.identity.runtime_type == runtime_type
        ]

    def find_by_execution_mode(self, mode: ExecutionMode) -> List[AgentAdapter]:
        """Filters adapters by ExecutionMode (local_process, remote_managed, serverless_inference)."""
        return [
            adapter for adapter in self._adapters.values()
            if adapter.identity.execution_mode == mode
        ]

    def find_by_infrastructure(self, provider_name: str) -> List[AgentAdapter]:
        """Filters adapters by backing infrastructure (local, nebius, render)."""
        p_lower = provider_name.lower()
        return [
            adapter for adapter in self._adapters.values()
            if adapter.identity.infrastructure_provider.lower() == p_lower
        ]

    def register_provider_descriptor(self, descriptor: ProviderDescriptor) -> None:
        """Registers an infrastructure or inference provider descriptor."""
        self._providers[descriptor.provider_id] = descriptor

    def list_provider_descriptors(self) -> List[ProviderDescriptor]:
        """Returns all registered infrastructure providers."""
        return list(self._providers.values())

    def register_model_descriptor(self, descriptor: ModelDescriptor) -> None:
        """Registers an LLM model descriptor."""
        self._models[descriptor.model_id] = descriptor

    def list_model_descriptors(self) -> List[ModelDescriptor]:
        """Returns all registered models."""
        return list(self._models.values())

    async def check_all_availabilities(self) -> Dict[str, AdapterAvailability]:
        """Runs availability probes across all registered adapters concurrently."""
        results: Dict[str, AdapterAvailability] = {}
        for adapter_id, adapter in self._adapters.items():
            try:
                results[adapter_id] = await adapter.check_availability()
            except Exception as e:
                logger.warning(f"Error checking availability for adapter '{adapter_id}': {e}")
        return results
