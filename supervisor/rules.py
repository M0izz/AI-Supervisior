from typing import Any, Dict, List, Optional
from core.events.schema import Event, EventType
from core.policies.models import PolicyConfig
from core.tasks.models import Task
from supervisor.decisions import SupervisorAction, SupervisorDecision


class AnomalyReport:
    def __init__(self, anomaly_type: str, description: str, evidence: Dict[str, Any], recommended_action: SupervisorAction):
        self.anomaly_type = anomaly_type
        self.description = description
        self.evidence = evidence
        self.recommended_action = recommended_action


class DeterministicRuleEngine:
    """
    Layer A: Fast, deterministic rules.
    Runs prior to LLM reasoning to catch obvious loops, danger, and drift instantly.
    """

    def __init__(self, policy: Optional[PolicyConfig] = None):
        self.policy = policy or PolicyConfig()

    def evaluate_tool_call(self, tool_name: str, arguments: Dict[str, Any], task: Optional[Task] = None) -> Optional[AnomalyReport]:
        """Check for dangerous commands or out-of-scope edits before execution."""
        # 1. Dangerous shell commands
        if tool_name == "run_command":
            cmd = arguments.get("command", "")
            if self.policy.is_command_dangerous(cmd):
                return AnomalyReport(
                    anomaly_type="DANGEROUS_ACTION",
                    description=f"Command '{cmd}' matches dangerous pattern.",
                    evidence={"command": cmd},
                    recommended_action=SupervisorAction.REQUEST_APPROVAL
                )

        # 2. Scope violations on file writes
        if tool_name in ("write_file", "edit_file"):
            target_path = arguments.get("path", "")
            # Check protected paths
            if self.policy.is_path_protected(target_path):
                return AnomalyReport(
                    anomaly_type="SCOPE_VIOLATION",
                    description=f"Target path '{target_path}' is protected by policy.",
                    evidence={"path": target_path},
                    recommended_action=SupervisorAction.REQUEST_APPROVAL
                )

            # Check task expected files if strict scope enforcement is enabled
            if task and task.expected_files and self.policy.prevent_modifications_outside_task_scope:
                norm_target = target_path.replace("\\", "/").strip("./")
                is_expected = any(norm_target.endswith(exp.strip("./")) for exp in task.expected_files)
                if not is_expected:
                    return AnomalyReport(
                        anomaly_type="SCOPE_VIOLATION",
                        description=f"Modification to '{target_path}' is outside expected task scope: {task.expected_files}",
                        evidence={"modified": target_path, "expected": task.expected_files},
                        recommended_action=SupervisorAction.PAUSE
                    )

        return None

    def evaluate_test_history(self, task: Task, recent_test_events: List[Event]) -> Optional[AnomalyReport]:
        """Check for repeated test failure loops."""
        if len(recent_test_events) < self.policy.pause_after_repeated_failures:
            return None

        # Look at the last N test events
        recent = recent_test_events[-self.policy.pause_after_repeated_failures:]
        error_signatures = [
            e.payload.get("error_signature")
            for e in recent
            if e.payload.get("failed", 0) > 0
        ]

        if len(error_signatures) == self.policy.pause_after_repeated_failures and len(set(error_signatures)) == 1:
            sig = error_signatures[0] or "UNKNOWN_ERROR"
            return AnomalyReport(
                anomaly_type="LOOP_DETECTED",
                description=f"Worker encountered the identical test failure {len(error_signatures)} times: '{sig}'",
                evidence={
                    "error_signature": sig,
                    "consecutive_failures": len(error_signatures),
                    "attempts": task.attempts
                },
                recommended_action=SupervisorAction.DELEGATE
            )

        return None
