"""
AI Supervisor Agent Adapters Package.
Establishes the universal adapter boundary between AI Supervisor
and external agent runtimes (Claude Code, OpenAI Codex, Gemini CLI, etc.).
"""

from adapters.models import (
    AdapterIdentity,
    AdapterCapability,
    AdapterAvailability,
    AdapterAvailabilityStatus,
    AdapterProcessStatus,
    AdapterExecutionResult,
)
from adapters.base import AgentAdapter
from adapters.registry import AdapterRegistry
from adapters.claude_code import ClaudeCodeAdapter
from adapters.codex import CodexAdapter

__all__ = [
    "AdapterIdentity",
    "AdapterCapability",
    "AdapterAvailability",
    "AdapterAvailabilityStatus",
    "AdapterProcessStatus",
    "AdapterExecutionResult",
    "AgentAdapter",
    "AdapterRegistry",
    "ClaudeCodeAdapter",
    "CodexAdapter",
]

