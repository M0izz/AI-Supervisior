import asyncio
import logging
from typing import Dict, List, Optional

from adapters.base import AgentAdapter
from adapters.models import AdapterIdentity, AdapterAvailability

logger = logging.getLogger("supervisor.adapters.registry")


class AdapterRegistry:
    """
    Registry for external Agent Adapters.
    Allows discovery, capability queries, and lifecycle invocation across
    diverse agent backends (Claude Code, future Codex, Gemini, local models).
    """

    def __init__(self):
        self._adapters: Dict[str, AgentAdapter] = {}
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

    async def check_all_availabilities(self) -> Dict[str, AdapterAvailability]:
        """Runs availability probes across all registered adapters concurrently."""
        results: Dict[str, AdapterAvailability] = {}
        for adapter_id, adapter in self._adapters.items():
            try:
                results[adapter_id] = await adapter.check_availability()
            except Exception as e:
                logger.warning(f"Error checking availability for adapter '{adapter_id}': {e}")
        return results
