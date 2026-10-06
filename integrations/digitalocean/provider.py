import logging
import re
from typing import Any, Dict, List, Optional
from adapters.models import (
    ProviderDescriptor,
    ModelDescriptor,
    AdapterAvailabilityStatus,
)
from integrations.digitalocean.client import DigitalOceanClient
from integrations.digitalocean.models import DigitalOceanStatus, GovernedToolCall

logger = logging.getLogger("supervisor.integrations.digitalocean.provider")


class DigitalOceanProvider:
    """
    DigitalOcean First-Class Ecosystem Provider.
    Coordinates:
      1. DigitalOcean Infrastructure Status (MicroVMs, Droplets, Harness Runtime)
      2. Serverless Inference & Model Catalog (Gemma 4, Hermes 4, etc.)
      3. Action Gateway Governed MCP Tool Access (Supervisor Security Perimeter)
    """

    def __init__(self, client: Optional[DigitalOceanClient] = None):
        self.client = client or DigitalOceanClient()

        # Action Gateway Governed Tool Safety Policies (Section 10)
        self.dangerous_tools = {
            "delete_files", "drop_table", "force_push", "kill_process", "modify_system_env"
        }
        self.protected_paths = [
            ".git", "node_modules", ".env", "supervisor.db", "secrets"
        ]

    async def get_descriptor(self) -> ProviderDescriptor:
        """Returns standard operational descriptor for DigitalOcean."""
        health = await self.client.check_health()
        status_val = health.get("status", DigitalOceanStatus.NOT_CONFIGURED.value)

        # Map to AdapterAvailabilityStatus
        if status_val == DigitalOceanStatus.CONNECTED.value:
            avail_status = AdapterAvailabilityStatus.CONNECTED
            is_avail = True
        elif status_val == DigitalOceanStatus.AUTHENTICATION_REQUIRED.value:
            avail_status = AdapterAvailabilityStatus.UNAUTHORIZED
            is_avail = False
        elif status_val == DigitalOceanStatus.NOT_CONFIGURED.value:
            avail_status = AdapterAvailabilityStatus.NOT_CONFIGURED
            is_avail = False
        else:
            avail_status = AdapterAvailabilityStatus.UNAVAILABLE
            is_avail = False

        models = await self.client.list_models()

        return ProviderDescriptor(
            provider_id="digitalocean",
            name="DigitalOcean",
            status=avail_status,
            available=is_avail,
            message=health.get("message", "DigitalOcean infrastructure layer"),
            capabilities=[
                "managed_agents",
                "harness_runtime",
                "hermes_support",
                "action_gateway",
                "serverless_inference",
                "microvm_isolation"
            ],
            inference_endpoint=self.client.config.inference_base_url,
            managed_agents_support=True,
            action_gateway_support=True,
            supported_models=[m["model_id"] for m in models]
        )

    async def get_models(self) -> List[ModelDescriptor]:
        """Returns all models exposed by DigitalOcean Inference."""
        raw_models = await self.client.list_models()
        return [
            ModelDescriptor(
                model_id=m["model_id"],
                name=m["name"],
                developer=m["developer"],
                infrastructure_provider="digitalocean",
                parameter_size=m.get("parameter_size"),
                specialties=m.get("specialties", []),
                available=bool(m.get("available", False)),
                context_window=32768
            )
            for m in raw_models
        ]

    async def govern_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: str,
        workspace: str
    ) -> GovernedToolCall:
        """
        DigitalOcean Action Gateway Security Gatekeeper (Section 10).
        Governs MCP tool access by enforcing AI Supervisor safety boundaries:
          - Tool availability does not equal authorization.
          - Enforces protected path boundaries and dangerous action approval gates.
        """
        tool_clean = tool_name.strip().lower()
        args_str = str(arguments).lower()

        # 1. Dangerous tool check
        if any(d in tool_clean for d in self.dangerous_tools):
            return GovernedToolCall(
                tool_name=tool_name,
                arguments=arguments,
                requester_agent=agent_id,
                target_workspace=workspace,
                is_safe=False,
                requires_approval=True,
                policy_violation_reason=f"Action Gateway flagged high-risk operation: '{tool_name}' requires operator approval."
            )

        # 2. Protected paths check
        for p in self.protected_paths:
            if p in args_str:
                return GovernedToolCall(
                    tool_name=tool_name,
                    arguments=arguments,
                    requester_agent=agent_id,
                    target_workspace=workspace,
                    is_safe=False,
                    requires_approval=True,
                    policy_violation_reason=f"Action Gateway: Access to protected path '{p}' requires explicit approval."
                )

        # 3. Path traversal check
        if "../" in args_str or "..\\" in args_str:
            return GovernedToolCall(
                tool_name=tool_name,
                arguments=arguments,
                requester_agent=agent_id,
                target_workspace=workspace,
                is_safe=False,
                requires_approval=False,
                policy_violation_reason="Action Gateway: Directory traversal outside assigned worktree blocked by Supervisor."
            )

        # Safe and authorized under current policy
        return GovernedToolCall(
            tool_name=tool_name,
            arguments=arguments,
            requester_agent=agent_id,
            target_workspace=workspace,
            is_safe=True,
            requires_approval=False,
            policy_violation_reason=None
        )
