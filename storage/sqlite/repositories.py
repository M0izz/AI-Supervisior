import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from storage.sqlite.db import DatabaseManager

logger = logging.getLogger("supervisor.storage.repositories")


def _to_json(val: Any) -> str:
    if val is None:
        return "{}"
    if isinstance(val, (dict, list)):
        return json.dumps(val, default=str)
    if hasattr(val, "model_dump"):
        return json.dumps(val.model_dump(), default=str)
    if hasattr(val, "dict"):
        return json.dumps(val.dict(), default=str)
    return json.dumps(val, default=str)



def _from_json(val: Optional[str], default: Any = None) -> Any:
    if not val:
        return default if default is not None else {}
    try:
        return json.loads(val)
    except Exception:
        return default if default is not None else {}


class MissionRepository:
    """Repository for Mission lifecycle persistence."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save(self, mission_data: Union[Dict[str, Any], Any]) -> None:
        """Insert or update a mission."""
        conn = await self.db.get_connection()
        try:
            if hasattr(mission_data, "model_dump"):
                d = mission_data.model_dump()
            elif hasattr(mission_data, "dict"):
                d = mission_data.dict()
            else:
                d = dict(mission_data)

            mission_id = d.get("id") or d.get("mission_id")
            title = d.get("title", "Untitled Mission")
            goal = d.get("goal", "")
            repository_path = d.get("repository_path", ".")
            status = d.get("status", "CREATED")
            if hasattr(status, "value"):
                status = status.value

            assigned_agents = _to_json(d.get("assigned_agents", []))
            active_agent_id = d.get("active_agent_id")
            constraints = _to_json(d.get("constraints", {}))
            metrics = _to_json(d.get("metrics", {}))

            created_at = d.get("created_at")
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            elif not created_at:
                created_at = datetime.now(timezone.utc).isoformat()

            updated_at = d.get("updated_at")
            if isinstance(updated_at, datetime):
                updated_at = updated_at.isoformat()
            elif not updated_at:
                updated_at = datetime.now(timezone.utc).isoformat()

            query = """
            INSERT INTO missions (
                mission_id, title, goal, repository_path, status,
                assigned_agents, active_agent_id, constraints, metrics,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mission_id) DO UPDATE SET
                title = excluded.title,
                goal = excluded.goal,
                repository_path = excluded.repository_path,
                status = excluded.status,
                assigned_agents = excluded.assigned_agents,
                active_agent_id = excluded.active_agent_id,
                constraints = excluded.constraints,
                metrics = excluded.metrics,
                updated_at = excluded.updated_at;
            """
            await conn.execute(
                query,
                (
                    mission_id, title, goal, repository_path, str(status),
                    assigned_agents, active_agent_id, constraints, metrics,
                    str(created_at), str(updated_at)
                )
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get(self, mission_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a mission by ID."""
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM missions WHERE mission_id = ?;", (mission_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["id"] = res["mission_id"]
            res["assigned_agents"] = _from_json(res.get("assigned_agents"), [])
            res["constraints"] = _from_json(res.get("constraints"), {})
            res["metrics"] = _from_json(res.get("metrics"), {})
            return res
        finally:
            await conn.close()

    async def list_all(self) -> List[Dict[str, Any]]:
        """List all missions ordered by creation time descending."""
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute("SELECT * FROM missions ORDER BY created_at DESC;")
            rows = await cursor.fetchall()
            missions = []
            for row in rows:
                m = dict(row)
                m["id"] = m["mission_id"]
                m["assigned_agents"] = _from_json(m.get("assigned_agents"), [])
                m["constraints"] = _from_json(m.get("constraints"), {})
                m["metrics"] = _from_json(m.get("metrics"), {})
                missions.append(m)
            return missions
        finally:
            await conn.close()


class TaskRepository:
    """Repository for Task entities and state."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save(self, task_data: Union[Dict[str, Any], Any]) -> None:
        """Insert or update a task."""
        conn = await self.db.get_connection()
        try:
            if hasattr(task_data, "model_dump"):
                d = task_data.model_dump()
            elif hasattr(task_data, "dict"):
                d = task_data.dict()
            else:
                d = dict(task_data)

            task_id = d.get("id") or d.get("task_id")
            mission_id = d.get("mission_id")
            title = d.get("title", "Untitled Task")
            description = d.get("description", "")
            status = d.get("status", "PENDING")
            if hasattr(status, "value"):
                status = status.value

            assigned_agent = d.get("assigned_agent") or d.get("assigned_agent_id")
            dependencies = _to_json(d.get("dependencies", []))
            expected_files = _to_json(d.get("expected_files", []))
            order_idx = d.get("order") if d.get("order") is not None else d.get("order_idx", 0)
            retry_count = d.get("retry_count", 0)
            result = _to_json(d.get("result", {}))

            created_at = d.get("created_at")
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            elif not created_at:
                created_at = datetime.now(timezone.utc).isoformat()

            updated_at = d.get("updated_at")
            if isinstance(updated_at, datetime):
                updated_at = updated_at.isoformat()
            elif not updated_at:
                updated_at = datetime.now(timezone.utc).isoformat()

            query = """
            INSERT INTO tasks (
                task_id, mission_id, title, description, status,
                assigned_agent, dependencies, expected_files, order_idx,
                retry_count, result, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                status = excluded.status,
                assigned_agent = excluded.assigned_agent,
                dependencies = excluded.dependencies,
                expected_files = excluded.expected_files,
                order_idx = excluded.order_idx,
                retry_count = excluded.retry_count,
                result = excluded.result,
                updated_at = excluded.updated_at;
            """
            await conn.execute(
                query,
                (
                    task_id, mission_id, title, description, str(status),
                    assigned_agent, dependencies, expected_files, order_idx,
                    retry_count, result, str(created_at), str(updated_at)
                )
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a task by ID."""
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute("SELECT * FROM tasks WHERE task_id = ?;", (task_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            t = dict(row)
            t["id"] = t["task_id"]
            t["assigned_agent_id"] = t.get("assigned_agent")
            t["order"] = t.get("order_idx", 0)
            t["dependencies"] = _from_json(t.get("dependencies"), [])
            t["expected_files"] = _from_json(t.get("expected_files"), [])
            t["result"] = _from_json(t.get("result"), {})
            return t
        finally:
            await conn.close()

    async def list_by_mission(self, mission_id: str) -> List[Dict[str, Any]]:
        """List all tasks belonging to a mission ordered by order_idx."""
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM tasks WHERE mission_id = ? ORDER BY order_idx ASC, created_at ASC;",
                (mission_id,)
            )
            rows = await cursor.fetchall()
            tasks = []
            for row in rows:
                t = dict(row)
                t["id"] = t["task_id"]
                t["assigned_agent_id"] = t.get("assigned_agent")
                t["order"] = t.get("order_idx", 0)
                t["dependencies"] = _from_json(t.get("dependencies"), [])
                t["expected_files"] = _from_json(t.get("expected_files"), [])
                t["result"] = _from_json(t.get("result"), {})
                tasks.append(t)
            return tasks
        finally:
            await conn.close()


class AgentRepository:
    """Repository for Agent status and metrics persistence."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save(self, agent_data: Union[Dict[str, Any], Any]) -> None:
        """Insert or update an agent record."""
        conn = await self.db.get_connection()
        try:
            if hasattr(agent_data, "model_dump"):
                d = agent_data.model_dump()
            elif hasattr(agent_data, "dict"):
                d = agent_data.dict()
            else:
                d = dict(agent_data)

            agent_id = d.get("agent_id")
            agent_type = d.get("agent_type") or d.get("type", "WORKER")
            model = d.get("model", "nemotron")
            status = d.get("status", "IDLE")
            if hasattr(status, "value"):
                status = status.value

            current_task_id = d.get("current_task") or d.get("current_task_id") or d.get("task_id")
            mission_id = d.get("mission_id")
            iterations = d.get("iterations", 0)
            tool_calls = d.get("tool_calls", 0)
            interventions = d.get("interventions", 0)

            last_activity = d.get("last_activity")
            if isinstance(last_activity, datetime):
                last_activity = last_activity.isoformat()
            elif not last_activity:
                last_activity = datetime.now(timezone.utc).isoformat()

            metadata = _to_json(d.get("metadata", {}))

            query = """
            INSERT INTO agents (
                agent_id, agent_type, model, status, current_task_id,
                mission_id, iterations, tool_calls, interventions,
                last_activity, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                agent_type = excluded.agent_type,
                model = excluded.model,
                status = excluded.status,
                current_task_id = excluded.current_task_id,
                mission_id = excluded.mission_id,
                iterations = excluded.iterations,
                tool_calls = excluded.tool_calls,
                interventions = excluded.interventions,
                last_activity = excluded.last_activity,
                metadata = excluded.metadata;
            """
            await conn.execute(
                query,
                (
                    agent_id, str(agent_type), model, str(status),
                    current_task_id, mission_id, iterations, tool_calls,
                    interventions, str(last_activity), metadata
                )
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute("SELECT * FROM agents WHERE agent_id = ?;", (agent_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["metadata"] = _from_json(res.get("metadata"), {})
            return res
        finally:
            await conn.close()

    async def list_all(self) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute("SELECT * FROM agents;")
            rows = await cursor.fetchall()
            agents = []
            for row in rows:
                a = dict(row)
                a["metadata"] = _from_json(a.get("metadata"), {})
                agents.append(a)
            return agents
        finally:
            await conn.close()


class EventRepository:
    """
    Append-Only Event Store.
    Persists events across missions, tasks, and agents without relying on UI state.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def append(self, event_data: Union[Dict[str, Any], Any]) -> str:
        """Appends a new event to the durable event log."""
        conn = await self.db.get_connection()
        try:
            if hasattr(event_data, "model_dump"):
                d = event_data.model_dump()
            elif hasattr(event_data, "dict"):
                d = event_data.dict()
            else:
                d = dict(event_data)

            event_id = d.get("event_id") or d.get("id") or f"evt_{uuid.uuid4().hex[:12]}"
            mission_id = d.get("mission_id", "default")
            task_id = d.get("task_id")
            agent_id = d.get("agent_id")
            provider = d.get("provider", "internal")

            event_type = d.get("event_type") or d.get("type", "generic.event")
            if hasattr(event_type, "value"):
                event_type = event_type.value

            schema_version = d.get("schema_version", "1.0.0")
            severity = d.get("severity", "info")
            if hasattr(severity, "value"):
                severity = severity.value

            timestamp = d.get("timestamp")
            if isinstance(timestamp, datetime):
                timestamp = timestamp.isoformat()
            elif not timestamp:
                timestamp = datetime.now(timezone.utc).isoformat()

            action = _to_json(d.get("action"))
            telemetry = _to_json(d.get("telemetry"))
            payload = _to_json(d.get("payload", {}))

            query = """
            INSERT INTO events (
                event_id, mission_id, task_id, agent_id, provider,
                event_type, schema_version, severity, timestamp,
                action, telemetry, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            await conn.execute(
                query,
                (
                    event_id, mission_id, task_id, agent_id, provider,
                    str(event_type), schema_version, str(severity), str(timestamp),
                    action, telemetry, payload
                )
            )
            await conn.commit()
            return event_id
        finally:
            await conn.close()

    async def get_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute("SELECT * FROM events WHERE event_id = ?;", (event_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["action"] = _from_json(res.get("action"))
            res["telemetry"] = _from_json(res.get("telemetry"))
            res["payload"] = _from_json(res.get("payload"))
            return res
        finally:
            await conn.close()

    async def list_by_mission(self, mission_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM events WHERE mission_id = ? ORDER BY timestamp ASC LIMIT ?;",
                (mission_id, limit)
            )
            rows = await cursor.fetchall()
            events = []
            for row in rows:
                e = dict(row)
                e["action"] = _from_json(e.get("action"))
                e["telemetry"] = _from_json(e.get("telemetry"))
                e["payload"] = _from_json(e.get("payload"))
                events.append(e)
            return events
        finally:
            await conn.close()

    async def count_events(self, mission_id: Optional[str] = None) -> int:
        conn = await self.db.get_connection()
        try:
            if mission_id:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM events WHERE mission_id = ?;", (mission_id,)
                )
            else:
                cursor = await conn.execute("SELECT COUNT(*) FROM events;")
            row = await cursor.fetchone()
            return int(row[0]) if row else 0
        finally:
            await conn.close()


class MemoryRepository:
    """Repository for storing persistent memory snippets, proven facts, and learned patterns."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save(
        self,
        mission_id: str,
        category: str,
        content: str,
        task_id: Optional[str] = None,
        project_id: str = "",
        memory_type: str = "FACT",
        status: str = "OBSERVED",
        confidence: float = 1.0,
        source: str = "system",
        source_id: str = "",
        created_by: str = "system",
        superseded_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        record_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> str:
        conn = await self.db.get_connection()
        try:
            rid = record_id or f"mem_{uuid.uuid4().hex[:12]}"
            now_iso = datetime.now(timezone.utc).isoformat()
            c_at = created_at or now_iso
            u_at = updated_at or now_iso
            meta_json = _to_json(metadata or {})
            mid = str(mission_id).strip() if (mission_id and str(mission_id).strip()) else None

            query = """
            INSERT INTO memory_records (
                record_id, project_id, mission_id, task_id, category, content,
                memory_type, status, confidence, source, source_id, created_by,
                superseded_by, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                project_id = excluded.project_id,
                task_id = excluded.task_id,
                category = excluded.category,
                content = excluded.content,
                memory_type = excluded.memory_type,
                status = excluded.status,
                confidence = excluded.confidence,
                source = excluded.source,
                source_id = excluded.source_id,
                created_by = excluded.created_by,
                superseded_by = excluded.superseded_by,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at;
            """
            await conn.execute(
                query,
                (
                    rid, project_id, mid, task_id, category, content,
                    memory_type, status, confidence, source, source_id, created_by,
                    superseded_by, meta_json, c_at, u_at
                )
            )
            await conn.commit()
            return rid
        finally:
            await conn.close()

    async def get(self, record_id: str) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM memory_records WHERE record_id = ?;",
                (record_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            r = dict(row)
            r["metadata"] = _from_json(r.get("metadata"))
            return r
        finally:
            await conn.close()

    async def list_by_mission(
        self,
        mission_id: str,
        status: Optional[str] = None,
        memory_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            conditions = ["mission_id = ?"]
            params: List[Any] = [mission_id]

            if status:
                conditions.append("status = ?")
                params.append(status)
            if memory_type:
                conditions.append("memory_type = ?")
                params.append(memory_type)

            query = f"SELECT * FROM memory_records WHERE {' AND '.join(conditions)} ORDER BY created_at ASC;"
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                r = dict(row)
                r["metadata"] = _from_json(r.get("metadata"))
                records.append(r)
            return records
        finally:
            await conn.close()

    async def list_by_project(
        self,
        project_id: str,
        status: Optional[str] = None,
        memory_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            conditions = ["project_id = ?"]
            params: List[Any] = [project_id]

            if status:
                conditions.append("status = ?")
                params.append(status)
            if memory_type:
                conditions.append("memory_type = ?")
                params.append(memory_type)

            query = f"SELECT * FROM memory_records WHERE {' AND '.join(conditions)} ORDER BY created_at ASC;"
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                r = dict(row)
                r["metadata"] = _from_json(r.get("metadata"))
                records.append(r)
            return records
        finally:
            await conn.close()

    async def delete(self, record_id: str) -> bool:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "DELETE FROM memory_records WHERE record_id = ?;",
                (record_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()


class ApprovalRepository:
    """Repository for human-in-the-loop approvals."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def create(
        self,
        mission_id: str,
        action_type: str,
        description: str,
        task_id: Optional[str] = None,
        approval_id: Optional[str] = None
    ) -> Dict[str, Any]:
        conn = await self.db.get_connection()
        try:
            aid = approval_id or f"appr_{uuid.uuid4().hex[:12]}"
            requested_at = datetime.now(timezone.utc).isoformat()
            query = """
            INSERT INTO approvals (
                approval_id, mission_id, task_id, action_type, description,
                status, requested_at
            ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?);
            """
            await conn.execute(
                query,
                (aid, mission_id, task_id, action_type, description, requested_at)
            )
            await conn.commit()
            return {
                "approval_id": aid,
                "mission_id": mission_id,
                "task_id": task_id,
                "action_type": action_type,
                "description": description,
                "status": "PENDING",
                "requested_at": requested_at,
            }
        finally:
            await conn.close()

    async def resolve(
        self,
        approval_id: str,
        status: str,
        resolved_by: str = "human_operator"
    ) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            resolved_at = datetime.now(timezone.utc).isoformat()
            query = """
            UPDATE approvals
            SET status = ?, resolved_at = ?, resolved_by = ?
            WHERE approval_id = ?;
            """
            await conn.execute(query, (status, resolved_at, resolved_by, approval_id))
            await conn.commit()
            cursor = await conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?;", (approval_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await conn.close()

    async def get(self, approval_id: str) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?;", (approval_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await conn.close()

    async def list_by_mission(self, mission_id: str) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM approvals WHERE mission_id = ? ORDER BY requested_at ASC;",
                (mission_id,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()


class VerificationRepository:
    """Repository for independent verification outcomes."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save(
        self,
        mission_id: str,
        verification_type: str,
        status: str,
        task_id: Optional[str] = None,
        command: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        verification_id: Optional[str] = None
    ) -> Dict[str, Any]:
        conn = await self.db.get_connection()
        try:
            vid = verification_id or f"ver_{uuid.uuid4().hex[:12]}"
            created_at = datetime.now(timezone.utc).isoformat()
            details_json = _to_json(details or {})

            query = """
            INSERT INTO verifications (
                verification_id, mission_id, task_id, verification_type,
                status, command, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(verification_id) DO UPDATE SET
                status = excluded.status,
                details = excluded.details;
            """
            await conn.execute(
                query,
                (vid, mission_id, task_id, verification_type, status, command, details_json, created_at)
            )
            await conn.commit()
            return {
                "verification_id": vid,
                "mission_id": mission_id,
                "task_id": task_id,
                "verification_type": verification_type,
                "status": status,
                "command": command,
                "details": details or {},
                "created_at": created_at,
            }
        finally:
            await conn.close()

    async def get(self, verification_id: str) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM verifications WHERE verification_id = ?;", (verification_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["details"] = _from_json(res.get("details"))
            return res
        finally:
            await conn.close()

    async def list_by_mission(self, mission_id: str) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM verifications WHERE mission_id = ? ORDER BY created_at ASC;",
                (mission_id,)
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                v = dict(row)
                v["details"] = _from_json(v.get("details"))
                records.append(v)
            return records
        finally:
            await conn.close()

    async def list_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM verifications WHERE task_id = ? ORDER BY created_at ASC;",
                (task_id,)
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                v = dict(row)
                v["details"] = _from_json(v.get("details"))
                records.append(v)
            return records
        finally:
            await conn.close()

    async def list_all(self) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute("SELECT * FROM verifications ORDER BY created_at ASC;")
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                v = dict(row)
                v["details"] = _from_json(v.get("details"))
                records.append(v)
            return records
        finally:
            await conn.close()


class HandoffRepository:
    """Repository for task handoff records and context packages."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save(
        self,
        mission_id: str,
        task_id: str,
        source_agent_id: str,
        target_agent_id: str,
        trigger: str,
        status: str,
        reason: str = "",
        context_package: Optional[Dict[str, Any]] = None,
        handoff_id: Optional[str] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = await self.db.get_connection()
        try:
            hid = handoff_id or f"hnd_{uuid.uuid4().hex[:12]}"
            created_at = datetime.now(timezone.utc).isoformat()
            ctx_json = _to_json(context_package or {})

            query = """
            INSERT INTO handoffs (
                handoff_id, mission_id, task_id, source_agent_id, target_agent_id,
                trigger, status, reason, context_package, created_at, result, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(handoff_id) DO UPDATE SET
                status = excluded.status,
                completed_at = CASE WHEN excluded.status IN ('COMPLETED', 'FAILED', 'REJECTED') THEN excluded.created_at ELSE handoffs.completed_at END,
                result = excluded.result,
                error = excluded.error,
                context_package = excluded.context_package;
            """
            await conn.execute(
                query,
                (hid, mission_id, task_id, source_agent_id, target_agent_id, trigger, status, reason, ctx_json, created_at, result, error)
            )
            await conn.commit()
            return {
                "handoff_id": hid,
                "mission_id": mission_id,
                "task_id": task_id,
                "source_agent_id": source_agent_id,
                "target_agent_id": target_agent_id,
                "trigger": trigger,
                "status": status,
                "reason": reason,
                "context_package": context_package or {},
                "created_at": created_at,
                "result": result,
                "error": error,
            }
        finally:
            await conn.close()

    async def get(self, handoff_id: Any) -> Optional[Dict[str, Any]]:
        hid = handoff_id.get("handoff_id") if isinstance(handoff_id, dict) else handoff_id
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM handoffs WHERE handoff_id = ?;", (hid,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["context_package"] = _from_json(res.get("context_package"))
            return res
        finally:
            await conn.close()

    async def list_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM handoffs WHERE task_id = ? ORDER BY created_at ASC;",
                (task_id,)
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                h = dict(row)
                h["context_package"] = _from_json(h.get("context_package"))
                records.append(h)
            return records
        finally:
            await conn.close()

    async def list_by_mission(self, mission_id: str) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM handoffs WHERE mission_id = ? ORDER BY created_at ASC;",
                (mission_id,)
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                h = dict(row)
                h["context_package"] = _from_json(h.get("context_package"))
                records.append(h)
            return records
        finally:
            await conn.close()


class RoutingRepository:
    """Repository for persisting and querying routing decisions in SQLite WAL."""
    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save(
        self,
        mission_id: str,
        task_id: str,
        decision: str,
        decision_reason: str,
        selected_agent_id: Optional[str] = None,
        selected_adapter_id: Optional[str] = None,
        score: float = 0.0,
        candidates: Optional[List[Dict[str, Any]]] = None,
        requirements: Optional[Dict[str, Any]] = None,
        routing_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = await self.db.get_connection()
        try:
            rid = routing_id or f"rtg_{uuid.uuid4().hex[:12]}"
            created_at = datetime.now(timezone.utc).isoformat()
            cands_json = _to_json(candidates or [])
            reqs_json = _to_json(requirements or {})

            query = """
            INSERT INTO routing_decisions (
                routing_id, mission_id, task_id, selected_agent_id, selected_adapter_id,
                decision, score, decision_reason, candidates, requirements, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(routing_id) DO UPDATE SET
                selected_agent_id = excluded.selected_agent_id,
                selected_adapter_id = excluded.selected_adapter_id,
                decision = excluded.decision,
                score = excluded.score,
                decision_reason = excluded.decision_reason,
                candidates = excluded.candidates,
                requirements = excluded.requirements;
            """
            await conn.execute(
                query,
                (rid, mission_id, task_id, selected_agent_id, selected_adapter_id, decision, score, decision_reason, cands_json, reqs_json, created_at)
            )
            await conn.commit()
            return {
                "routing_id": rid,
                "mission_id": mission_id,
                "task_id": task_id,
                "selected_agent_id": selected_agent_id,
                "selected_adapter_id": selected_adapter_id,
                "decision": decision,
                "score": score,
                "decision_reason": decision_reason,
                "candidates": candidates or [],
                "requirements": requirements or {},
                "created_at": created_at,
            }
        finally:
            await conn.close()

    async def get(self, routing_id: Any) -> Optional[Dict[str, Any]]:
        rid = routing_id.get("routing_id") if isinstance(routing_id, dict) else routing_id
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM routing_decisions WHERE routing_id = ?;", (rid,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["candidates"] = _from_json(res.get("candidates"))
            res["requirements"] = _from_json(res.get("requirements"))
            return res
        finally:
            await conn.close()

    async def list_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM routing_decisions WHERE task_id = ? ORDER BY created_at ASC;",
                (task_id,)
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                r = dict(row)
                r["candidates"] = _from_json(r.get("candidates"))
                r["requirements"] = _from_json(r.get("requirements"))
                records.append(r)
            return records
        finally:
            await conn.close()

    async def list_by_mission(self, mission_id: str) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM routing_decisions WHERE mission_id = ? ORDER BY created_at ASC;",
                (mission_id,)
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                r = dict(row)
                r["candidates"] = _from_json(r.get("candidates"))
                r["requirements"] = _from_json(r.get("requirements"))
                records.append(r)
            return records
        finally:
            await conn.close()




class AbsenceRepository:
    """Repository for Absence Mode sessions, immutable policy snapshots, and auditable decisions."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        conn = await self.db.get_connection()
        try:
            aid = session.get("absence_id") or f"abs_{uuid.uuid4().hex[:12]}"
            mission_id = session.get("mission_id")
            status = session.get("status", "ARMED")
            policy_snapshot = _to_json(session.get("policy_snapshot", {}))
            started_at = session.get("started_at")
            expires_at = session.get("expires_at")
            created_by = session.get("created_by", "user")
            tasks_completed = session.get("tasks_completed", 0)
            retries_count = session.get("retries_count", 0)
            handoffs_count = session.get("handoffs_count", 0)
            paused_reason = session.get("paused_reason")
            created_at = session.get("created_at") or datetime.now(timezone.utc).isoformat()
            updated_at = session.get("updated_at") or created_at

            query = """
            INSERT INTO absence_sessions (
                absence_id, mission_id, status, policy_snapshot, started_at, expires_at,
                created_by, tasks_completed, retries_count, handoffs_count, paused_reason,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(absence_id) DO UPDATE SET
                status = excluded.status,
                policy_snapshot = excluded.policy_snapshot,
                started_at = excluded.started_at,
                expires_at = excluded.expires_at,
                tasks_completed = excluded.tasks_completed,
                retries_count = excluded.retries_count,
                handoffs_count = excluded.handoffs_count,
                paused_reason = excluded.paused_reason,
                updated_at = excluded.updated_at;
            """
            await conn.execute(
                query,
                (
                    aid, mission_id, status, policy_snapshot, started_at, expires_at,
                    created_by, tasks_completed, retries_count, handoffs_count, paused_reason,
                    created_at, updated_at
                )
            )
            await conn.commit()
            return await self.get_session(aid) # type: ignore
        finally:
            await conn.close()

    async def get_session(self, absence_id: str) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM absence_sessions WHERE absence_id = ?;",
                (absence_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["policy_snapshot"] = _from_json(res.get("policy_snapshot"))
            return res
        finally:
            await conn.close()

    async def get_active_session(self, mission_id: str) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM absence_sessions WHERE mission_id = ? AND status IN ('ARMED', 'ACTIVE', 'PAUSED') ORDER BY created_at DESC LIMIT 1;",
                (mission_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["policy_snapshot"] = _from_json(res.get("policy_snapshot"))
            return res
        finally:
            await conn.close()

    async def list_sessions_by_mission(self, mission_id: str) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM absence_sessions WHERE mission_id = ? ORDER BY created_at DESC;",
                (mission_id,)
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                r = dict(row)
                r["policy_snapshot"] = _from_json(r.get("policy_snapshot"))
                records.append(r)
            return records
        finally:
            await conn.close()

    async def list_active_sessions(self) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM absence_sessions WHERE status IN ('ARMED', 'ACTIVE') ORDER BY created_at DESC;"
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                r = dict(row)
                r["policy_snapshot"] = _from_json(r.get("policy_snapshot"))
                records.append(r)
            return records
        finally:
            await conn.close()

    async def update_session(self, absence_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            fields = []
            params = []
            for k, v in updates.items():
                if k == "policy_snapshot":
                    fields.append(f"{k} = ?")
                    params.append(_to_json(v))
                elif k != "absence_id":
                    fields.append(f"{k} = ?")
                    params.append(v)
            if not fields:
                return await self.get_session(absence_id)

            fields.append("updated_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())
            params.append(absence_id)

            query = f"UPDATE absence_sessions SET {', '.join(fields)} WHERE absence_id = ?;"
            await conn.execute(query, tuple(params))
            await conn.commit()
            return await self.get_session(absence_id)
        finally:
            await conn.close()

    async def save_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        conn = await self.db.get_connection()
        try:
            did = decision.get("decision_id") or f"dec_{uuid.uuid4().hex[:12]}"
            absence_id = decision.get("absence_id")
            mission_id = decision.get("mission_id")
            task_id = decision.get("task_id")
            agent_id = decision.get("agent_id")
            dec_type = decision.get("decision", "DENY")
            rule_id = decision.get("rule_id", "default")
            reason = decision.get("reason", "")
            action = decision.get("action", "")
            metadata = _to_json(decision.get("metadata", {}))
            timestamp = decision.get("timestamp") or datetime.now(timezone.utc).isoformat()

            query = """
            INSERT INTO absence_decisions (
                decision_id, absence_id, mission_id, task_id, agent_id,
                decision, rule_id, reason, action, metadata, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            await conn.execute(
                query,
                (did, absence_id, mission_id, task_id, agent_id, dec_type, rule_id, reason, action, metadata, timestamp)
            )
            await conn.commit()
            return {
                "decision_id": did,
                "absence_id": absence_id,
                "mission_id": mission_id,
                "task_id": task_id,
                "agent_id": agent_id,
                "decision": dec_type,
                "rule_id": rule_id,
                "reason": reason,
                "action": action,
                "metadata": decision.get("metadata", {}),
                "timestamp": timestamp
            }
        finally:
            await conn.close()

    async def list_decisions(self, absence_id: str) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM absence_decisions WHERE absence_id = ? ORDER BY timestamp ASC;",
                (absence_id,)
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                r = dict(row)
                r["metadata"] = _from_json(r.get("metadata"))
                records.append(r)
            return records
        finally:
            await conn.close()


async def attach_sqlite_persistence(event_bus: Any, db: DatabaseManager) -> EventRepository:
    """
    Attaches an SQLite WAL event store subscriber to the provided EventBus.
    Every event emitted to EventBus is automatically persisted to SQLite.
    """
    repo = EventRepository(db)

    async def _sqlite_event_sink(event: Any) -> None:
        try:
            await repo.append(event)
        except Exception as e:
            logger.warning(f"Error persisting event {getattr(event, 'event_id', 'unknown')} to SQLite: {e}")

    if hasattr(event_bus, "subscribe"):
        await event_bus.subscribe(_sqlite_event_sink)
    elif hasattr(event_bus, "subscribe_sync"):
        event_bus.subscribe_sync(_sqlite_event_sink)

    return repo

