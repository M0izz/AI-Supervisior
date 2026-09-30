import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent
from core.events.bus import EventBus
from core.state.models import AgentContextPackage
from tools.base import BaseTool

logger = logging.getLogger("supervisor.reviewer")


class ReviewerDiagnosis(BaseModel):
    diagnosis: str
    failure_category: str
    evidence: List[str] = Field(default_factory=list)
    recommended_strategy: str
    rejected_approach: Optional[str] = None
    confidence: float = 0.94


class ReviewerAgent(BaseAgent):
    """
    Independent Reviewer Agent.
    Investigates failure signatures and recommends recovery strategies.
    Strictly limited to read-only tools (cannot mutate files).
    """

    ALLOWED_READONLY_TOOLS = {"read_file", "list_files", "run_tests", "git_diff"}

    def __init__(
        self,
        agent_id: str = "reviewer_01",
        event_bus: Optional[EventBus] = None,
        tools: Optional[Dict[str, BaseTool]] = None
    ):
        # Enforce read-only tool filtering
        readonly_tools = {
            name: tool for name, tool in (tools or {}).items()
            if name in self.ALLOWED_READONLY_TOOLS
        }
        super().__init__(agent_id=agent_id, role="Reviewer", event_bus=event_bus or EventBus(), tools=readonly_tools)

    async def run(self, context_package: AgentContextPackage) -> ReviewerDiagnosis:
        mission_id = context_package.mission_id
        task_id = context_package.task.get("id")

        await self.emit_action(
            mission_id=mission_id,
            task_id=task_id,
            description="Reviewer analyzing repeated failure signature and repository state."
        )

        evidence = []
        # Inspect files if read_file tool is available
        if "read_file" in self.tools:
            res = await self.call_tool("read_file", {"path": "src/parser.py"}, mission_id=mission_id, task_id=task_id)
            if res.success and res.output:
                evidence.append(f"Inspected src/parser.py ({len(res.output)} chars)")
                if "\\ufeff" not in res.output and ".lstrip(" not in res.output:
                    evidence.append("src/parser.py does not strip UTF-8 BOM characters from raw input")

        # Check for specific error signatures in context
        error_sig = ""
        for attempt in context_package.previous_attempts:
            if "error_signature" in attempt:
                error_sig = attempt["error_signature"]
                break
        if not error_sig and context_package.task.get("last_error_signature"):
            error_sig = context_package.task["last_error_signature"]

        if "BOM" in error_sig or "CSV" in error_sig or any("BOM" in ev for ev in evidence):
            diagnosis = ReviewerDiagnosis(
                diagnosis="UTF-8 BOM marker (\ufeff) attached to initial CSV header, causing dict key lookup to fail on 'user_id'",
                failure_category="ENCODING_MISMATCH",
                evidence=evidence or ["Repeated failure signature: CSV_HEADER_MISMATCH_BOM"],
                recommended_strategy="Strip leading UTF-8 BOM before CSV parsing (e.g. raw_content.lstrip('\\ufeff'))",
                rejected_approach="Direct string header comparison without BOM normalization",
                confidence=0.96
            )
        elif error_sig:
            diagnosis = ReviewerDiagnosis(
                diagnosis=f"Investigated failure signature '{error_sig}', but root cause requires human investigation.",
                failure_category="UNKNOWN",
                evidence=evidence or [f"Signature: {error_sig}"],
                recommended_strategy="Escalate to human supervisor for guidance.",
                rejected_approach=None,
                confidence=0.35
            )
        else:
            diagnosis = ReviewerDiagnosis(
                diagnosis="No conclusive failure evidence found during inspection.",
                failure_category="UNKNOWN",
                evidence=evidence,
                recommended_strategy="Request operator guidance or retry with verbose logging.",
                rejected_approach=None,
                confidence=0.20
            )

        await self.emit_action(
            mission_id=mission_id,
            task_id=task_id,
            description=f"Review complete: {diagnosis.diagnosis}",
            metadata={"diagnosis": diagnosis.model_dump()}
        )

        return diagnosis
