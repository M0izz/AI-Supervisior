from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.events.schema import Event, EventType, EventSeverity


class TimelineItem(BaseModel):
    id: str
    timestamp: str
    actor: str  # WORKER, TEST, SUPERVISOR, NEMOTRON, REVIEWER, MEMORY, VERIFIER, OPERATOR
    title: str
    detail: Optional[str] = None
    severity: str = "info"  # info, warning, critical, success
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SupervisorTimelineBuilder:
    """
    Transforms raw chronological event streams into a rich, narrative Control Room timeline.
    Highlights supervisor interventions, model reasoning, diagnostics, memory, and verifications.
    """

    @staticmethod
    def build_narrative_timeline(events: List[Event]) -> List[TimelineItem]:
        timeline: List[TimelineItem] = []

        for e in events:
            time_str = e.timestamp.strftime("%H:%M:%S")
            actor = "SUPERVISOR"
            title = e.type.value
            detail = None
            severity = "info"

            # Parse Worker tool calls
            if e.type in (EventType.TOOL_CALL, EventType.TOOL_CALLED):
                actor = "WORKER"
                tool_name = e.payload.get("tool", "unknown_tool")
                title = f"{tool_name}()"
                target = e.payload.get("target") or e.payload.get("arguments", {}).get("path")
                detail = f"Target: {target}" if target else None

            # Parse Test execution results
            elif e.type in (EventType.TEST_RESULT, EventType.TEST_COMPLETED, EventType.TEST_FAILED):
                actor = "TEST"
                passed = e.payload.get("passed", 0)
                failed = e.payload.get("failed", 0)
                title = f"{passed} passed / {failed} failed"
                if failed > 0:
                    severity = "warning"
                    sig = e.payload.get("error_signature")
                    detail = f"Error: {sig}" if sig else "Tests failed"
                else:
                    severity = "success"
                    detail = "All test assertions succeeded"

            # Parse Tool completed / failed
            elif e.type == EventType.TOOL_COMPLETED:
                actor = "WORKER"
                tool_name = e.payload.get("tool", "tool")
                title = f"{tool_name} completed"
                severity = "info"
            elif e.type == EventType.TOOL_FAILED:
                actor = "WORKER"
                tool_name = e.payload.get("tool", "tool")
                title = f"{tool_name} failed"
                detail = e.payload.get("error")
                severity = "warning"

            # Parse Supervisor Anomaly & Loop Detection
            elif e.type in (EventType.SUPERVISOR_ALERT, EventType.SUPERVISOR_ANOMALY_DETECTED):
                actor = "SUPERVISOR"
                anomaly = e.payload.get("anomaly_type") or e.payload.get("rule_name", "ANOMALY")
                title = anomaly.replace("_", " ")
                detail = e.payload.get("description")
                severity = "warning" if anomaly != "DANGEROUS_ACTION" else "critical"

            # Parse Worker paused / resumed
            elif e.type == EventType.AGENT_PAUSED:
                actor = "SUPERVISOR"
                title = f"Worker {e.agent_id} paused"
                detail = "Paused by supervisor for anomaly intervention"
                severity = "warning"
            elif e.type == EventType.AGENT_RESUMED:
                actor = "WORKER"
                title = "Resumed with recovery context"
                detail = "New operational strategy injected"
                severity = "info"

            # Parse Nemotron Reasoning
            elif e.type == EventType.SUPERVISOR_REASONING_STARTED:
                actor = "NEMOTRON"
                title = "Analyzing anomaly context..."
                detail = f"Anomaly: {e.payload.get('anomaly_type')}"
            elif e.type in (EventType.SUPERVISOR_DECISION, EventType.SUPERVISOR_REASONING_COMPLETED):
                actor = "NEMOTRON"
                decision = e.payload.get("decision") or e.payload.get("action", "DECIDE")
                target = e.payload.get("target_agent", "")
                confidence = e.payload.get("confidence")
                conf_pct = f" ({int(confidence * 100)}%)" if confidence else ""
                title = f"{decision} → {target}{conf_pct}" if target else f"{decision}{conf_pct}"
                detail = e.payload.get("reason")
                severity = "warning" if decision != "CONTINUE" else "info"

            # Parse Reviewer Diagnosis
            elif e.type == EventType.AGENT_ACTION and e.payload.get("role") == "reviewer":
                actor = "REVIEWER"
                title = "Diagnosis completed"
                detail = e.payload.get("description")
                severity = "info"
            elif e.agent_id and "reviewer" in e.agent_id and e.type == EventType.AGENT_COMPLETED:
                actor = "REVIEWER"
                title = "Diagnosis recorded"
                detail = e.payload.get("description")

            # Parse Memory Updated
            elif e.type == EventType.MEMORY_UPDATED:
                actor = "MEMORY"
                status = e.payload.get("status", "RECORDED")
                fact = e.payload.get("fact") or e.payload.get("content", "Fact recorded")
                title = f"Fact recorded ({status})"
                detail = fact[:120] if fact else None

            # Parse Verification
            elif e.type == EventType.VERIFICATION_STARTED:
                actor = "VERIFIER"
                title = "Independent verification started"
                detail = "Running full test suite in clean sandbox"
            elif e.type == EventType.VERIFICATION_RESULT:
                actor = "VERIFIER"
                passed = e.payload.get("passed", 0)
                failed = e.payload.get("failed", 0)
                if failed == 0:
                    title = f"{passed}/{passed} tests passed"
                    detail = "Verification verified and confirmed"
                    severity = "success"
                else:
                    title = f"Verification failed ({failed} failing)"
                    detail = e.payload.get("error_signature")
                    severity = "critical"
            elif e.type == EventType.VERIFICATION_FAILED:
                actor = "SUPERVISOR"
                title = "Worker claim rejected"
                detail = "Verifier found failing tests; task reopened"
                severity = "critical"

            # Parse Human Approval & Operator Take Control
            elif e.type == EventType.APPROVAL_REQUESTED:
                actor = "SUPERVISOR"
                title = "HUMAN APPROVAL REQUIRED"
                detail = e.payload.get("reason")
                severity = "critical"
            elif e.type == EventType.APPROVAL_RESOLVED:
                actor = "OPERATOR"
                act = e.payload.get("action", "RESOLVED")
                title = f"Approval resolved: {act}"
                detail = f"By {e.payload.get('operator')}: {e.payload.get('feedback', '')}"
                severity = "info"
            elif e.type == EventType.OPERATOR_TAKE_CONTROL:
                actor = "OPERATOR"
                title = "Operator took manual control"
                detail = e.payload.get("reason")
                severity = "warning"

            # Parse Danger & Contention
            elif e.type == EventType.DANGER_DETECTED:
                actor = "SUPERVISOR"
                title = "DANGER DETECTED"
                detail = e.payload.get("error") or "Dangerous command blocked"
                severity = "critical"
            elif e.type == EventType.FILE_CONTENTION_DETECTED:
                actor = "SUPERVISOR"
                title = "FILE CONTENTION BLOCKED"
                detail = f"{e.payload.get('requesting_agent')} blocked from editing {e.payload.get('file_path')} (held by {e.payload.get('current_holder')})"
                severity = "warning"

            # Parse Task Reopened
            elif e.type == EventType.TASK_REOPENED:
                actor = "SUPERVISOR"
                title = f"Task {e.task_id} Reopened"
                detail = e.payload.get("reason")
                severity = "warning"

            timeline.append(
                TimelineItem(
                    id=e.id,
                    timestamp=time_str,
                    actor=actor,
                    title=title,
                    detail=detail,
                    severity=severity,
                    task_id=e.task_id,
                    metadata=e.payload
                )
            )

        return timeline
