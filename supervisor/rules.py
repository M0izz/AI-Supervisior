import re
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
    Runs prior to LLM reasoning to catch loops, no-progress, scope violations, danger, and budget overflow.
    """

    def __init__(self, policy: Optional[PolicyConfig] = None):
        self.policy = policy or PolicyConfig()

    def normalize_signature(self, sig: Optional[str]) -> str:
        """Normalizes error signatures to detect equivalent failures regardless of line numbers or memory addresses."""
        if not sig:
            return "UNKNOWN_ERROR"
        # Strip memory addresses (0x...) and exact line numbers
        cleaned = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", sig)
        cleaned = re.sub(r":\d+", ":LINE", cleaned)
        return cleaned.strip()

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
        threshold = self.policy.pause_after_repeated_failures
        if len(recent_test_events) < threshold:
            return None

        recent = recent_test_events[-threshold:]
        normalized_sigs = [
            self.normalize_signature(e.payload.get("error_signature"))
            for e in recent
            if e.payload.get("failed", 0) > 0
        ]

        if len(normalized_sigs) == threshold and len(set(normalized_sigs)) == 1:
            sig = normalized_sigs[0]
            return AnomalyReport(
                anomaly_type="LOOP_DETECTED",
                description=f"Worker encountered the identical test failure {len(normalized_sigs)} times: '{sig}'",
                evidence={
                    "error_signature": sig,
                    "consecutive_failures": len(normalized_sigs),
                    "attempts": task.attempts
                },
                recommended_action=SupervisorAction.DELEGATE
            )

        return None

    def evaluate_no_progress(self, task: Task, recent_test_events: List[Event]) -> Optional[AnomalyReport]:
        """
        Detect cases where agent acts, tests fail, agent acts again,
        and test pass/fail counts remain unimproved across multiple attempts.
        """
        threshold = self.policy.pause_after_repeated_failures
        if len(recent_test_events) < threshold:
            return None

        recent = recent_test_events[-threshold:]
        passed_counts = [e.payload.get("passed", 0) for e in recent]
        failed_counts = [e.payload.get("failed", 0) for e in recent]

        # If failures > 0 and neither passed nor failed count has improved
        if all(f > 0 for f in failed_counts):
            if len(set(passed_counts)) == 1 and len(set(failed_counts)) == 1:
                return AnomalyReport(
                    anomaly_type="NO_PROGRESS",
                    description=f"No measurable progress across {threshold} attempts ({failed_counts[0]} failing tests consistently).",
                    evidence={
                        "passed_counts": passed_counts,
                        "failed_counts": failed_counts,
                        "attempts": task.attempts
                    },
                    recommended_action=SupervisorAction.CHANGE_STRATEGY
                )

        return None

    def evaluate_budget(self, iterations: int, tool_calls_count: int, elapsed_seconds: float) -> Optional[AnomalyReport]:
        """Check if execution approaches budget ceilings."""
        if iterations >= self.policy.max_turns_per_task:
            return AnomalyReport(
                anomaly_type="BUDGET_WARNING",
                description=f"Task exceeded configured turn budget ({iterations}/{self.policy.max_turns_per_task} turns).",
                evidence={"iterations": iterations, "limit": self.policy.max_turns_per_task},
                recommended_action=SupervisorAction.PAUSE
            )

        if elapsed_seconds > 600:  # 10 minutes
            return AnomalyReport(
                anomaly_type="BUDGET_WARNING",
                description=f"Task duration exceeded time budget ({elapsed_seconds:.0f}s).",
                evidence={"elapsed_seconds": elapsed_seconds},
                recommended_action=SupervisorAction.PAUSE
            )

        return None
