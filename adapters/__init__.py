"""
AI Supervisor Agent Adapters Package.
Establishes the universal adapter boundary between AI Supervisor
and external agent runtimes (Claude Code, OpenAI Codex, Gemini CLI, Hermes, Qwen, OpenCode, Kimi, etc.).
"""

from adapters.models import (
    AdapterIdentity,
    AdapterCapability,
    AdapterAvailability,
    AdapterAvailabilityStatus,
    AdapterProcessStatus,
    AdapterExecutionResult,
    RuntimeType,
    ExecutionMode,
    ProviderDescriptor,
    ModelDescriptor,
)
from adapters.base import AgentAdapter
from adapters.registry import AdapterRegistry
from adapters.claude_code import ClaudeCodeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter
from adapters.qwen import QwenAdapter
from adapters.opencode import OpenCodeAdapter
from adapters.kimi import KimiAdapter
from adapters.hermes import HermesAdapter
from adapters.goose import GooseAdapter
from adapters.cline import ClineAdapter
from adapters.custom import CustomAgentAdapter, CustomAgentRegistration

__all__ = [
    "AdapterIdentity",
    "AdapterCapability",
    "AdapterAvailability",
    "AdapterAvailabilityStatus",
    "AdapterProcessStatus",
    "AdapterExecutionResult",
    "RuntimeType",
    "ExecutionMode",
    "ProviderDescriptor",
    "ModelDescriptor",
    "AgentAdapter",
    "AdapterRegistry",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "GeminiAdapter",
    "QwenAdapter",
    "OpenCodeAdapter",
    "KimiAdapter",
    "HermesAdapter",
    "GooseAdapter",
    "ClineAdapter",
    "CustomAgentAdapter",
    "CustomAgentRegistration",
]
