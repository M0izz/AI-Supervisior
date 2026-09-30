from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class AutonomyLevel(str, Enum):
    OBSERVE_ONLY = "OBSERVE_ONLY"
    ASSISTED = "ASSISTED"
    SUPERVISED = "SUPERVISED"
    AUTONOMOUS = "AUTONOMOUS"


class PolicyConfig(BaseModel):
    autonomy_level: AutonomyLevel = AutonomyLevel.SUPERVISED

    # Guardrails
    require_approval_for_destructive_commands: bool = True
    require_approval_for_database_changes: bool = True
    pause_after_repeated_failures: int = 3
    verify_before_completion: bool = True
    prevent_modifications_outside_task_scope: bool = True

    # Budgets
    max_turns_per_task: int = 12
    max_mission_budget_usd: float = 10.0
    max_tokens_per_mission: int = 250_000

    # Dangerous patterns
    dangerous_command_patterns: List[str] = Field(default_factory=lambda: [
        "rm -rf", "drop table", "drop database", "format ", "mkfs",
        "dd if=", "chmod 777", "chmod -R 777", "kill -9", "shutdown",
        ":(){ :|:& };:"
    ])

    # Protected paths
    protected_paths: List[str] = Field(default_factory=lambda: [
        ".git", ".env", "secrets", "database/migrations", "migrations/", "schema.sql"
    ])

    def is_command_dangerous(self, command: str) -> bool:
        cmd_lower = command.lower()
        return any(pattern.lower() in cmd_lower for pattern in self.dangerous_command_patterns)

    def is_path_protected(self, path: str) -> bool:
        norm = path.replace("\\", "/").lower()
        return any(prot.lower() in norm for prot in self.protected_paths)
