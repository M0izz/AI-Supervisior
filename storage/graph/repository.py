"""
FalkorDB Graph Repository.
Implements the authoritative property graph persistence, idempotent writes,
parameterized queries, and graph traversal queries for AI Supervisor.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from storage.graph.client import FalkorDBClient
from storage.graph.schema import NodeLabel, RelType, ensure_indices

logger = logging.getLogger("supervisor.storage.graph.repo")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FalkorDBGraphRepository:
    """
    Authoritative Graph Repository backed by FalkorDB.
    Maintains graph-backed mission memory, task dependencies, execution attempts,
    failure chains, handoffs, and verification provenance.
    """

    def __init__(self, client: FalkorDBClient):
        self.client = client
        self._indices_initialized = False

    def initialize_schema(self) -> None:
        """Ensures graph indices exist upon initialization."""
        try:
            graph = self.client.get_graph()
            ensure_indices(graph)
            self._indices_initialized = True
        except Exception as e:
            logger.warning(f"[FalkorDB] Schema initialization deferred: {e}")

    # ==========================================
    # 1. Mission & Requirements Management
    # ==========================================

    async def save_mission(
        self,
        mission_id: str,
        title: str,
        goal: str,
        repository_path: Optional[str] = None,
        status: str = "AWAITING_APPROVAL",
        requirements: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Idempotently persists Mission node and associated Requirement nodes.
        """
        now = _now_iso()
        cypher = """
        MERGE (m:Mission {id: $mission_id})
        ON CREATE SET
            m.title = $title,
            m.goal = $goal,
            m.repository_path = $repository_path,
            m.status = $status,
            m.created_at = $now,
            m.updated_at = $now
        ON MATCH SET
            m.title = $title,
            m.goal = $goal,
            m.repository_path = $repository_path,
            m.status = $status,
            m.updated_at = $now
        RETURN m.id AS id, m.status AS status
        """
        params = {
            "mission_id": mission_id,
            "title": title,
            "goal": goal,
            "repository_path": repository_path or "",
            "status": status,
            "now": now,
        }
        res = self.client.query(cypher, params)

        # Save requirements and link with HAS_REQUIREMENT
        if requirements:
            for i, req in enumerate(requirements):
                if isinstance(req, str):
                    req_id = f"{mission_id}_req_{i+1}"
                    req_desc = req
                    req_cat = "in_scope"
                else:
                    req_id = req.get("id") or f"{mission_id}_req_{i+1}"
                    req_desc = req.get("description") or str(req)
                    req_cat = req.get("category", "in_scope")
                req_cypher = """
                MATCH (m:Mission {id: $mission_id})
                MERGE (r:Requirement {id: $req_id})
                ON CREATE SET
                    r.mission_id = $mission_id,
                    r.description = $description,
                    r.category = $category,
                    r.created_at = $now
                ON MATCH SET
                    r.description = $description,
                    r.category = $category
                MERGE (m)-[:HAS_REQUIREMENT]->(r)
                """
                self.client.query(
                    req_cypher,
                    {
                        "mission_id": mission_id,
                        "req_id": req_id,
                        "description": req_desc,
                        "category": req_cat,
                        "now": now,
                    },
                )

        return {"mission_id": mission_id, "status": status}

    async def update_mission_status(
        self,
        mission_id: str,
        status: str,
        summary: Optional[str] = None,
    ) -> None:
        """Updates status of a Mission node."""
        now = _now_iso()
        cypher = """
        MATCH (m:Mission {id: $mission_id})
        SET m.status = $status, m.updated_at = $now
        """
        params: Dict[str, Any] = {"mission_id": mission_id, "status": status, "now": now}
        if summary:
            cypher = """
            MATCH (m:Mission {id: $mission_id})
            SET m.status = $status, m.summary = $summary, m.updated_at = $now
            """
            params["summary"] = summary
        self.client.query(cypher, params)

    # ==========================================
    # 2. Task DAG & Dependencies Management
    # ==========================================

    async def save_task_dag(
        self,
        mission_id: str,
        tasks: List[Dict[str, Any]],
    ) -> None:
        """
        Persists Task nodes, connects them to Mission with CONTAINS_TASK,
        and establishes explicit DEPENDS_ON relationships.
        """
        now = _now_iso()

        # Step 1: Create all Task nodes
        for t in tasks:
            task_id = t["id"]
            title = t.get("title", "")
            order = int(t.get("order", 1))
            status = t.get("status", "PENDING")
            expected_files = json.dumps(t.get("expected_files", []))

            cypher = """
            MATCH (m:Mission {id: $mission_id})
            MERGE (task:Task {id: $task_id})
            ON CREATE SET
                task.mission_id = $mission_id,
                task.title = $title,
                task.order = $order,
                task.status = $status,
                task.expected_files = $expected_files,
                task.created_at = $now,
                task.updated_at = $now
            ON MATCH SET
                task.title = $title,
                task.order = $order,
                task.expected_files = $expected_files,
                task.updated_at = $now
            MERGE (m)-[:CONTAINS_TASK]->(task)
            """
            self.client.query(
                cypher,
                {
                    "mission_id": mission_id,
                    "task_id": task_id,
                    "title": title,
                    "order": order,
                    "status": status,
                    "expected_files": expected_files,
                    "now": now,
                },
            )

        # Step 2: Establish DEPENDS_ON relationships
        for t in tasks:
            task_id = t["id"]
            deps = t.get("dependencies", [])
            for dep_id in deps:
                dep_cypher = """
                MATCH (task:Task {id: $task_id})
                MATCH (dep:Task {id: $dep_id})
                MERGE (task)-[:DEPENDS_ON]->(dep)
                """
                self.client.query(dep_cypher, {"task_id": task_id, "dep_id": dep_id})

    # ==========================================
    # 3. Agent & Execution Lifecycle
    # ==========================================

    async def register_agent(
        self,
        agent_id: str,
        agent_type: str = "WORKER",
        model: str = "nemotron",
        display_name: Optional[str] = None,
        status: str = "IDLE",
    ) -> None:
        """Persists or updates an Agent node in FalkorDB."""
        now = _now_iso()
        cypher = """
        MERGE (a:Agent {id: $agent_id})
        ON CREATE SET
            a.agent_type = $agent_type,
            a.model = $model,
            a.display_name = $display_name,
            a.status = $status,
            a.created_at = $now,
            a.updated_at = $now
        ON MATCH SET
            a.agent_type = $agent_type,
            a.model = $model,
            a.display_name = $display_name,
            a.status = $status,
            a.updated_at = $now
        """
        self.client.query(
            cypher,
            {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "model": model,
                "display_name": display_name or agent_id,
                "status": status,
                "now": now,
            },
        )

    async def record_execution_start(
        self,
        execution_id: str,
        task_id: str,
        mission_id: str,
        agent_id: str,
        attempt_number: int = 1,
    ) -> Dict[str, Any]:
        """
        Records the start of a distinct Execution attempt.
        Crucial: Retries are modeled as separate Execution nodes linked to the same task,
        preserving complete historical context.
        """
        now = _now_iso()
        cypher = """
        MATCH (task:Task {id: $task_id})
        MERGE (a:Agent {id: $agent_id})
        ON CREATE SET
            a.agent_type = 'WORKER',
            a.model = 'unknown',
            a.display_name = $agent_id,
            a.status = 'BUSY',
            a.created_at = $now,
            a.updated_at = $now
        MERGE (e:Execution {id: $execution_id})
        ON CREATE SET
            e.task_id = $task_id,
            e.mission_id = $mission_id,
            e.agent_id = $agent_id,
            e.attempt_number = $attempt_number,
            e.status = 'IN_PROGRESS',
            e.started_at = $now
        ON MATCH SET
            e.status = 'IN_PROGRESS',
            e.agent_id = $agent_id
        MERGE (a)-[:EXECUTES]->(e)
        MERGE (e)-[:FOR_TASK]->(task)
        SET task.status = 'IN_PROGRESS'
        RETURN e.id AS id, e.attempt_number AS attempt
        """
        params = {
            "execution_id": execution_id,
            "task_id": task_id,
            "mission_id": mission_id,
            "agent_id": agent_id,
            "attempt_number": int(attempt_number),
            "now": now,
        }
        res = self.client.query(cypher, params)
        return {"execution_id": execution_id, "attempt_number": attempt_number}

    async def record_execution_event(
        self,
        execution_id: str,
        event_id: str,
        event_type: str,
        severity: str = "INFO",
        payload: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Emits an ExecutionEvent node and links it to Execution with EMITS.
        """
        now = timestamp or _now_iso()
        payload_str = json.dumps(payload or {})
        cypher = """
        MATCH (e:Execution {id: $execution_id})
        MERGE (evt:ExecutionEvent {id: $event_id})
        ON CREATE SET
            evt.execution_id = $execution_id,
            evt.event_type = $event_type,
            evt.severity = $severity,
            evt.payload_json = $payload_str,
            evt.timestamp = $now
        MERGE (e)-[:EMITS]->(evt)
        """
        self.client.query(
            cypher,
            {
                "execution_id": execution_id,
                "event_id": event_id,
                "event_type": event_type,
                "severity": severity,
                "payload_str": payload_str,
                "now": now,
            },
        )

    async def record_execution_failure(
        self,
        execution_id: str,
        error_signature: str,
        reason: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        """
        Marks an execution attempt as FAILED, links it to the causal event with FAILS_WITH.
        """
        now = _now_iso()
        cypher = """
        MATCH (e:Execution {id: $execution_id})
        SET
            e.status = 'FAILED',
            e.error_signature = $error_signature,
            e.reason = $reason,
            e.completed_at = $now
        """
        self.client.query(
            cypher,
            {
                "execution_id": execution_id,
                "error_signature": error_signature,
                "reason": reason or "",
                "now": now,
            },
        )

        if event_id:
            link_cypher = """
            MATCH (e:Execution {id: $execution_id})
            MERGE (evt:ExecutionEvent {id: $event_id})
            ON CREATE SET
                evt.execution_id = $execution_id,
                evt.event_type = 'CAUSAL_FAILURE_EVENT',
                evt.severity = 'ERROR',
                evt.payload_json = $payload_str,
                evt.timestamp = $now
            MERGE (e)-[:FAILS_WITH]->(evt)
            """
            self.client.query(
                link_cypher,
                {
                    "execution_id": execution_id,
                    "event_id": event_id,
                    "payload_str": json.dumps({"error_signature": error_signature, "reason": reason or ""}),
                    "now": now,
                },
            )

    async def record_execution_success(
        self,
        execution_id: str,
        summary: Optional[str] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Marks execution attempt as COMPLETED and links produced Artifacts.
        """
        now = _now_iso()
        cypher = """
        MATCH (e:Execution {id: $execution_id})
        SET
            e.status = 'COMPLETED',
            e.summary = $summary,
            e.completed_at = $now
        WITH e
        MATCH (e)-[:FOR_TASK]->(t:Task)
        SET t.status = 'COMPLETED'
        """
        self.client.query(
            cypher,
            {"execution_id": execution_id, "summary": summary or "", "now": now},
        )

        if artifacts:
            for art in artifacts:
                art_id = art.get("id") or f"art_{uuid.uuid4().hex[:10]}"
                art_path = art.get("path") or art.get("file_path", "")
                art_type = art.get("type", "file")
                art_hash = art.get("hash", "")

                art_cypher = """
                MATCH (e:Execution {id: $execution_id})
                MERGE (a:Artifact {id: $art_id})
                ON CREATE SET
                    a.file_path = $art_path,
                    a.artifact_type = $art_type,
                    a.hash = $art_hash,
                    a.created_at = $now
                MERGE (e)-[:PRODUCES]->(a)
                """
                self.client.query(
                    art_cypher,
                    {
                        "execution_id": execution_id,
                        "art_id": art_id,
                        "art_path": art_path,
                        "art_type": art_type,
                        "art_hash": art_hash,
                        "now": now,
                    },
                )

    # ==========================================
    # 4. Decisions, Recovery, & Handoffs
    # ==========================================

    async def record_decision(
        self,
        decision_id: str,
        mission_id: str,
        task_id: str,
        decision_type: str,
        action: str,
        reason: str,
        responding_to_event_id: Optional[str] = None,
        selected_agent_id: Optional[str] = None,
    ) -> None:
        """
        Records a supervisory or recovery decision.
        Explicitly links:
        - (Decision)-[:RESPONDS_TO]->(ExecutionEvent)
        - (Decision)-[:SELECTS]->(Agent)
        """
        now = _now_iso()
        cypher = """
        MERGE (d:Decision {id: $decision_id})
        ON CREATE SET
            d.mission_id = $mission_id,
            d.task_id = $task_id,
            d.decision_type = $decision_type,
            d.action = $action,
            d.reason = $reason,
            d.timestamp = $now
        ON MATCH SET
            d.action = $action,
            d.reason = $reason,
            d.updated_at = $now
        """
        self.client.query(
            cypher,
            {
                "decision_id": decision_id,
                "mission_id": mission_id,
                "task_id": task_id,
                "decision_type": decision_type,
                "action": action,
                "reason": reason,
                "now": now,
            },
        )

        if responding_to_event_id:
            link_event = """
            MATCH (d:Decision {id: $decision_id})
            MATCH (evt:ExecutionEvent {id: $event_id})
            MERGE (d)-[:RESPONDS_TO]->(evt)
            """
            self.client.query(link_event, {"decision_id": decision_id, "event_id": responding_to_event_id})

        if selected_agent_id:
            link_agent = """
            MATCH (d:Decision {id: $decision_id})
            MERGE (a:Agent {id: $agent_id})
            ON CREATE SET a.display_name = $agent_id
            MERGE (d)-[:SELECTS]->(a)
            """
            self.client.query(link_agent, {"decision_id": decision_id, "agent_id": selected_agent_id})

    async def record_handoff(
        self,
        handoff_id: str,
        task_id: str,
        source_agent: str,
        target_agent: str,
        trigger: str,
        status: str = "COMPLETED",
        context_summary: Optional[str] = None,
    ) -> None:
        """
        Records a handoff between two agents for a task:
        (Handoff)-[:TRANSFERS_CONTEXT]->(Task)
        """
        now = _now_iso()
        cypher = """
        MATCH (task:Task {id: $task_id})
        MERGE (h:Handoff {id: $handoff_id})
        ON CREATE SET
            h.task_id = $task_id,
            h.source_agent = $source_agent,
            h.target_agent = $target_agent,
            h.trigger = $trigger,
            h.status = $status,
            h.context_summary = $context_summary,
            h.timestamp = $now
        ON MATCH SET
            h.status = $status,
            h.context_summary = $context_summary
        MERGE (h)-[:TRANSFERS_CONTEXT]->(task)
        """
        self.client.query(
            cypher,
            {
                "handoff_id": handoff_id,
                "task_id": task_id,
                "source_agent": source_agent,
                "target_agent": target_agent,
                "trigger": trigger,
                "status": status,
                "context_summary": context_summary or "",
                "now": now,
            },
        )

    # ==========================================
    # 5. Verification & Evidence Traceability
    # ==========================================

    async def record_verification(
        self,
        verification_id: str,
        task_id: str,
        mission_id: str,
        decision: str,
        summary: str,
        evidence_items: Optional[List[Dict[str, Any]]] = None,
        execution_id: Optional[str] = None,
    ) -> None:
        """
        Records independent verification results.
        Links:
        - (Verification)-[:EVALUATES]->(Task)
        - (Verification)-[:EVALUATES_EXECUTION]->(Execution)  <-- Exact execution attempt evaluated
        - (Verification)-[:SUPPORTED_BY]->(Evidence)
        """
        now = _now_iso()
        cypher = """
        MATCH (task:Task {id: $task_id})
        MERGE (v:Verification {id: $verification_id})
        ON CREATE SET
            v.task_id = $task_id,
            v.mission_id = $mission_id,
            v.execution_id = $execution_id,
            v.decision = $decision,
            v.summary = $summary,
            v.verified_at = $now
        ON MATCH SET
            v.execution_id = $execution_id,
            v.decision = $decision,
            v.summary = $summary,
            v.verified_at = $now
        MERGE (v)-[:EVALUATES]->(task)
        """
        self.client.query(
            cypher,
            {
                "verification_id": verification_id,
                "task_id": task_id,
                "mission_id": mission_id,
                "execution_id": execution_id or "",
                "decision": decision,
                "summary": summary,
                "now": now,
            },
        )

        if execution_id:
            link_exec = """
            MATCH (v:Verification {id: $verification_id})
            MATCH (e:Execution {id: $execution_id})
            MERGE (v)-[:EVALUATES_EXECUTION]->(e)
            """
            self.client.query(link_exec, {"verification_id": verification_id, "execution_id": execution_id})

        if evidence_items:
            for item in evidence_items:
                ev_id = item.get("id") or f"ev_{uuid.uuid4().hex[:10]}"
                ev_type = item.get("type", "empirical_test")
                ev_desc = item.get("description", "")
                ev_passed = bool(item.get("passed", False))
                ev_data = json.dumps(item.get("data", {}))

                ev_cypher = """
                MATCH (v:Verification {id: $verification_id})
                MERGE (ev:Evidence {id: $ev_id})
                ON CREATE SET
                    ev.evidence_type = $ev_type,
                    ev.description = $ev_desc,
                    ev.passed = $ev_passed,
                    ev.empirical_data = $ev_data,
                    ev.created_at = $now
                MERGE (v)-[:SUPPORTED_BY]->(ev)
                """
                self.client.query(
                    ev_cypher,
                    {
                        "verification_id": verification_id,
                        "ev_id": ev_id,
                        "ev_type": ev_type,
                        "ev_desc": ev_desc,
                        "ev_passed": ev_passed,
                        "ev_data": ev_data,
                        "now": now,
                    },
                )

    # ==========================================
    # 6. Graph Queries & Context Traversals
    # ==========================================

    async def get_task_graph_context(self, mission_id: str, task_id: str) -> Dict[str, Any]:
        """
        Traverses FalkorDB graph to build a bounded, dependency-aware context package
        before task dispatch or retry.
        Includes:
        - Task details & dependencies
        - Prior execution attempts & statuses
        - Known error signatures and failure events
        - Prior decisions & handoff records
        - Verification history
        """
        # Dependencies query with empirical verification check
        dep_query = """
        MATCH (t:Task {id: $task_id})-[:DEPENDS_ON]->(dep:Task)
        OPTIONAL MATCH (v:Verification {decision: 'ACCEPT'})-[:EVALUATES]->(dep)
        RETURN
            dep.id AS id,
            dep.title AS title,
            dep.status AS status,
            dep.order AS order,
            (v IS NOT NULL OR dep.status = 'VERIFIED') AS is_verified
        ORDER BY dep.order ASC
        """
        dep_res = self.client.query(dep_query, {"task_id": task_id})
        dependencies = [
            {
                "id": row[0],
                "title": row[1],
                "status": row[2],
                "order": row[3],
                "is_verified": bool(row[4]),
            }
            for row in (dep_res.result_set or [])
        ]

        # Prior executions query
        exec_query = """
        MATCH (e:Execution)-[:FOR_TASK]->(t:Task {id: $task_id})
        RETURN
            e.id AS id,
            e.attempt_number AS attempt,
            e.status AS status,
            e.agent_id AS agent_id,
            e.error_signature AS error_signature,
            e.summary AS summary,
            e.started_at AS started_at,
            e.completed_at AS completed_at
        ORDER BY e.attempt_number ASC
        """
        exec_res = self.client.query(exec_query, {"task_id": task_id})
        executions = [
            {
                "id": row[0],
                "execution_id": row[0],
                "attempt_number": row[1],
                "status": row[2],
                "agent_id": row[3],
                "error_signature": row[4],
                "summary": row[5],
                "started_at": row[6],
                "completed_at": row[7],
            }
            for row in (exec_res.result_set or [])
        ]

        # Failures & Causal Events
        fail_query = """
        MATCH (e:Execution)-[:FOR_TASK]->(t:Task {id: $task_id})
        MATCH (e)-[:FAILS_WITH]->(evt:ExecutionEvent)
        RETURN
            e.id AS exec_id,
            e.attempt_number AS attempt,
            evt.id AS event_id,
            evt.event_type AS event_type,
            evt.payload_json AS payload
        """
        fail_res = self.client.query(fail_query, {"task_id": task_id})
        failures = [
            {
                "execution_id": row[0],
                "attempt_number": row[1],
                "event_id": row[2],
                "event_type": row[3],
                "payload": json.loads(row[4]) if row[4] else {},
            }
            for row in (fail_res.result_set or [])
        ]

        # Decisions query
        dec_query = """
        MATCH (d:Decision {task_id: $task_id})
        OPTIONAL MATCH (d)-[:RESPONDS_TO]->(evt:ExecutionEvent)
        OPTIONAL MATCH (d)-[:SELECTS]->(a:Agent)
        RETURN
            d.id AS id,
            d.decision_type AS type,
            d.action AS action,
            d.reason AS reason,
            d.timestamp AS timestamp,
            evt.id AS responding_to_event_id,
            a.id AS selected_agent
        ORDER BY d.timestamp ASC
        """
        dec_res = self.client.query(dec_query, {"task_id": task_id})
        decisions = [
            {
                "id": row[0],
                "decision_id": row[0],
                "decision_type": row[1],
                "action": row[2],
                "reason": row[3],
                "timestamp": row[4],
                "responding_to_event_id": row[5],
                "selected_agent": row[6],
            }
            for row in (dec_res.result_set or [])
        ]

        # Handoff query
        handoff_query = """
        MATCH (h:Handoff)-[:TRANSFERS_CONTEXT]->(t:Task {id: $task_id})
        RETURN
            h.id AS id,
            h.source_agent AS source_agent,
            h.target_agent AS target_agent,
            h.trigger AS trigger,
            h.status AS status,
            h.context_summary AS context_summary,
            h.timestamp AS timestamp
        ORDER BY h.timestamp ASC
        """
        ho_res = self.client.query(handoff_query, {"task_id": task_id})
        handoffs = [
            {
                "id": row[0],
                "handoff_id": row[0],
                "source_agent": row[1],
                "target_agent": row[2],
                "trigger": row[3],
                "status": row[4],
                "context_summary": row[5],
                "timestamp": row[6],
            }
            for row in (ho_res.result_set or [])
        ]

        # Verification query
        ver_query = """
        MATCH (v:Verification)-[:EVALUATES]->(t:Task {id: $task_id})
        RETURN v.id, v.decision, v.summary, v.verified_at
        """
        ver_res = self.client.query(ver_query, {"task_id": task_id})
        verifications = [
            {"id": row[0], "decision": row[1], "summary": row[2], "verified_at": row[3]}
            for row in (ver_res.result_set or [])
        ]

        # Prerequisite tasks must be empirically verified, not merely claiming success
        dependencies_met = all(bool(d.get("is_verified")) for d in dependencies)

        return {
            "mission_id": mission_id,
            "task_id": task_id,
            "dependencies": dependencies,
            "dependencies_met": dependencies_met,
            "total_attempts": len(executions),
            "prior_executions": executions,
            "prior_attempts": executions,
            "prior_failures": failures,
            "decisions": decisions,
            "handoffs": handoffs,
            "verifications": verifications,
        }

    async def get_prior_failure_history(
        self,
        mission_id: str,
        task_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns complete failure history and causal paths for a task or mission.
        """
        if task_id:
            cypher = """
            MATCH (e:Execution {task_id: $task_id, status: 'FAILED'})
            OPTIONAL MATCH (e)-[:FAILS_WITH]->(evt:ExecutionEvent)
            OPTIONAL MATCH (d:Decision)-[:RESPONDS_TO]->(evt)
            RETURN
                e.id AS exec_id,
                e.attempt_number AS attempt,
                e.agent_id AS agent_id,
                e.error_signature AS error_signature,
                e.reason AS reason,
                evt.id AS event_id,
                evt.event_type AS event_type,
                d.id AS decision_id,
                d.action AS decision_action,
                d.reason AS decision_reason
            ORDER BY e.attempt_number ASC
            """
            params = {"task_id": task_id}
        else:
            cypher = """
            MATCH (e:Execution {mission_id: $mission_id, status: 'FAILED'})
            OPTIONAL MATCH (e)-[:FAILS_WITH]->(evt:ExecutionEvent)
            OPTIONAL MATCH (d:Decision)-[:RESPONDS_TO]->(evt)
            RETURN
                e.id AS exec_id,
                e.attempt_number AS attempt,
                e.agent_id AS agent_id,
                e.error_signature AS error_signature,
                e.reason AS reason,
                evt.id AS event_id,
                evt.event_type AS event_type,
                d.id AS decision_id,
                d.action AS decision_action,
                d.reason AS decision_reason
            ORDER BY e.started_at ASC
            """
            params = {"mission_id": mission_id}

        res = self.client.query(cypher, params)
        records = []
        for row in (res.result_set or []):
            records.append({
                "execution_id": row[0],
                "attempt_number": row[1],
                "agent_id": row[2],
                "error_signature": row[3],
                "reason": row[4],
                "event_id": row[5],
                "causal_event_id": row[5],
                "event_type": row[6],
                "decision_id": row[7],
                "decision_action": row[8],
                "decision_reason": row[9],
            })
        return records

    async def get_decision_lineage(self, mission_id: str) -> List[Dict[str, Any]]:
        """
        Explains every routing or recovery decision by returning its supporting graph path:
        Decision -> RESPONDS_TO -> ExecutionEvent
        Decision -> SELECTS -> Agent
        """
        cypher = """
        MATCH (d:Decision {mission_id: $mission_id})
        OPTIONAL MATCH (d)-[:RESPONDS_TO]->(evt:ExecutionEvent)
        OPTIONAL MATCH (d)-[:SELECTS]->(a:Agent)
        RETURN
            d.id AS decision_id,
            d.task_id AS task_id,
            d.decision_type AS decision_type,
            d.action AS action,
            d.reason AS reason,
            d.timestamp AS timestamp,
            evt.id AS event_id,
            evt.event_type AS event_type,
            evt.payload_json AS event_payload,
            a.id AS agent_id,
            a.display_name AS agent_name
        ORDER BY d.timestamp ASC
        """
        res = self.client.query(cypher, {"mission_id": mission_id})
        lineage = []
        for row in (res.result_set or []):
            lineage.append({
                "id": row[0],
                "decision_id": row[0],
                "task_id": row[1],
                "decision_type": row[2],
                "action": row[3],
                "reason": row[4],
                "timestamp": row[5],
                "responding_to_event_id": row[6],
                "selected_agent_id": row[9],
                "causal_event": {
                    "id": row[6],
                    "event_type": row[7],
                    "payload": json.loads(row[8]) if row[8] else None,
                } if row[6] else None,
                "selected_agent": {
                    "id": row[9],
                    "display_name": row[10],
                } if row[9] else None,
            })
        return lineage

    async def get_verification_trace(self, task_id: str) -> Dict[str, Any]:
        """
        Returns full traceability from Verification outcome to objective empirical Evidence.
        Verification -> EVALUATES -> Task
        Verification -> SUPPORTED_BY -> Evidence
        """
        cypher = """
        MATCH (v:Verification {task_id: $task_id})
        MATCH (v)-[:EVALUATES]->(t:Task)
        OPTIONAL MATCH (v)-[:SUPPORTED_BY]->(ev:Evidence)
        RETURN
            v.id AS verification_id,
            v.decision AS decision,
            v.summary AS summary,
            v.verified_at AS verified_at,
            t.id AS task_id,
            t.title AS task_title,
            collect({
                id: ev.id,
                type: ev.evidence_type,
                description: ev.description,
                passed: ev.passed,
                empirical_data: ev.empirical_data
            }) AS evidence_list
        """
        res = self.client.query(cypher, {"task_id": task_id})
        if not res.result_set:
            return {"task_id": task_id, "verified": False, "trace": None}

        row = res.result_set[0]
        evidence_list = []
        raw_evidence = row[6] if len(row) > 6 else []
        if isinstance(raw_evidence, list):
            for item in raw_evidence:
                if isinstance(item, dict) and item.get("id"):
                    evidence_list.append(item)

        return {
            "task_id": task_id,
            "verified": True,
            "verification_id": row[0],
            "decision": row[1],
            "summary": row[2],
            "verified_at": row[3],
            "task_title": row[5],
            "evidence": evidence_list,
        }

    async def get_mission_subgraph(self, mission_id: str) -> Dict[str, Any]:
        """
        Returns all nodes and relationships connected to the mission for graph visualization / API inspection.
        """
        cypher = """
        MATCH (m:Mission {id: $mission_id})
        OPTIONAL MATCH (m)-[:HAS_REQUIREMENT]->(r:Requirement)
        OPTIONAL MATCH (m)-[:CONTAINS_TASK]->(t:Task)
        OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:Task)
        OPTIONAL MATCH (e:Execution)-[:FOR_TASK]->(t)
        OPTIONAL MATCH (a:Agent)-[:EXECUTES]->(e)
        OPTIONAL MATCH (e)-[:EMITS]->(evt:ExecutionEvent)
        OPTIONAL MATCH (e)-[:FAILS_WITH]->(fevt:ExecutionEvent)
        OPTIONAL MATCH (e)-[:PRODUCES]->(art:Artifact)
        OPTIONAL MATCH (d:Decision {mission_id: $mission_id})
        OPTIONAL MATCH (d)-[:RESPONDS_TO]->(devt:ExecutionEvent)
        OPTIONAL MATCH (d)-[:SELECTS]->(da:Agent)
        OPTIONAL MATCH (h:Handoff)-[:TRANSFERS_CONTEXT]->(t)
        OPTIONAL MATCH (v:Verification)-[:EVALUATES]->(t)
        OPTIONAL MATCH (v)-[:SUPPORTED_BY]->(ev:Evidence)
        RETURN
            m,
            collect(DISTINCT r) AS requirements,
            collect(DISTINCT t) AS tasks,
            collect(DISTINCT e) AS executions,
            collect(DISTINCT a) AS agents,
            collect(DISTINCT evt) AS events,
            collect(DISTINCT d) AS decisions,
            collect(DISTINCT h) AS handoffs,
            collect(DISTINCT v) AS verifications,
            collect(DISTINCT ev) AS evidence,
            collect(DISTINCT art) AS artifacts
        """
        res = self.client.query(cypher, {"mission_id": mission_id})
        nodes: List[Dict[str, Any]] = []
        seen_node_ids = set()

        def add_node(item: Any, default_label: str):
            if not item:
                return
            props = getattr(item, "properties", None)
            if props is None and isinstance(item, dict):
                props = item
            if not props:
                return
            node_id = props.get("id") or str(props)
            if node_id in seen_node_ids:
                return
            seen_node_ids.add(node_id)
            labels = getattr(item, "labels", None) or [default_label]
            label = labels[0] if isinstance(labels, list) and labels else default_label
            nodes.append({"id": node_id, "label": label, "properties": props})

        if res.result_set:
            row = res.result_set[0]
            add_node(row[0], "Mission")
            for cat_list, lbl in [
                (row[1], "Requirement"),
                (row[2], "Task"),
                (row[3], "Execution"),
                (row[4], "Agent"),
                (row[5], "ExecutionEvent"),
                (row[6], "Decision"),
                (row[7], "Handoff"),
                (row[8], "Verification"),
                (row[9], "Evidence"),
                (row[10], "Artifact"),
            ]:
                if isinstance(cat_list, list):
                    for elem in cat_list:
                        add_node(elem, lbl)

        # Retrieve all explicit relationships between these discovered nodes
        edges_query = """
        MATCH (n)-[r]->(m)
        WHERE n.id IN $node_ids AND m.id IN $node_ids
        RETURN n.id AS source, type(r) AS type, m.id AS target
        """
        edges_res = self.client.query(edges_query, {"node_ids": list(seen_node_ids)})
        edges = [
            {"source": erow[0], "type": erow[1], "target": erow[2]}
            for erow in (edges_res.result_set or [])
        ]

        return {
            "mission_id": mission_id,
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }
