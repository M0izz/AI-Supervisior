"""
FalkorDB Property Graph Schema Definitions.
Defines canonical node labels, relationship types, indices, and validation rules.
"""

from enum import Enum
import logging
from typing import Any, List

logger = logging.getLogger("supervisor.storage.graph.schema")


class NodeLabel(str, Enum):
    MISSION = "Mission"
    REQUIREMENT = "Requirement"
    TASK = "Task"
    AGENT = "Agent"
    EXECUTION = "Execution"
    EXECUTION_EVENT = "ExecutionEvent"
    FAILURE = "Failure"
    DECISION = "Decision"
    HANDOFF = "Handoff"
    ARTIFACT = "Artifact"
    EVIDENCE = "Evidence"
    VERIFICATION = "Verification"


class RelType(str, Enum):
    HAS_REQUIREMENT = "HAS_REQUIREMENT"
    CONTAINS_TASK = "CONTAINS_TASK"
    HAS_TASK = "HAS_TASK"
    DEPENDS_ON = "DEPENDS_ON"
    ASSIGNED_TO = "ASSIGNED_TO"
    HAS_ATTEMPT = "HAS_ATTEMPT"
    FOR_TASK = "FOR_TASK"
    EXECUTES = "EXECUTES"
    EMITS = "EMITS"
    PRODUCES = "PRODUCES"
    PRODUCED = "PRODUCED"
    FAILS_WITH = "FAILS_WITH"
    FAILED_WITH = "FAILED_WITH"
    HAS_RESULT = "HAS_RESULT"
    EVALUATES = "EVALUATES"
    EVALUATES_EXECUTION = "EVALUATES_EXECUTION"
    SUPPORTED_BY = "SUPPORTED_BY"
    RESPONDS_TO = "RESPONDS_TO"
    SELECTS = "SELECTS"
    GOVERNS = "GOVERNS"
    HAS_DECISION = "HAS_DECISION"
    TRANSFERS_CONTEXT = "TRANSFERS_CONTEXT"
    FROM_AGENT = "FROM_AGENT"
    TO_AGENT = "TO_AGENT"


INDEXED_FIELDS = [
    (NodeLabel.MISSION.value, "id"),
    (NodeLabel.TASK.value, "id"),
    (NodeLabel.TASK.value, "mission_id"),
    (NodeLabel.AGENT.value, "id"),
    (NodeLabel.EXECUTION.value, "id"),
    (NodeLabel.EXECUTION.value, "task_id"),
    (NodeLabel.FAILURE.value, "id"),
    (NodeLabel.FAILURE.value, "execution_id"),
    (NodeLabel.DECISION.value, "id"),
    (NodeLabel.DECISION.value, "mission_id"),
    (NodeLabel.HANDOFF.value, "id"),
    (NodeLabel.HANDOFF.value, "task_id"),
    (NodeLabel.VERIFICATION.value, "id"),
    (NodeLabel.VERIFICATION.value, "task_id"),
    (NodeLabel.ARTIFACT.value, "id"),
    (NodeLabel.EVIDENCE.value, "id"),
]


def ensure_indices(graph: Any) -> List[str]:
    """
    Idempotently creates range indices on essential entity identifiers.
    Returns list of successfully created/verified indices.
    """
    created: List[str] = []
    for label, prop in INDEXED_FIELDS:
        try:
            if hasattr(graph, "create_node_range_index"):
                graph.create_node_range_index(label, prop)
            else:
                graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
            created.append(f"{label}.{prop}")
        except Exception as e:
            # Index might already exist
            err_msg = str(e).lower()
            if "already exists" in err_msg or "index exists" in err_msg:
                created.append(f"{label}.{prop} (existing)")
            else:
                logger.debug(f"[FalkorDB] Index on {label}.{prop} notice: {e}")
    return created
