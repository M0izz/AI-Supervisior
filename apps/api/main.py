import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.events.schema import Event, EventType, EventSeverity
from core.missions.models import Mission, MissionStatus, MissionConstraints
from core.tasks.models import Task, TaskStatus
from core.policies.models import PolicyConfig
from agents.registry import AgentStatus, AgentHealth
from supervisor.approvals import ResolveApprovalPayload, ApprovalResolutionAction
from apps.api.state import app_state
from apps.api.websocket import ws_hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("supervisor.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Hook WebSocket broadcaster directly to the EventBus
    await app_state.event_bus.subscribe(ws_hub.broadcast_event)
    logger.info("EventBus -> WebSocket Hub pipeline established.")
    yield
    logger.info("Shutting down API server.")


app = FastAPI(
    title="AI Work Supervisor API",
    description="The Control Room & Supervisory Nervous System for Autonomous AI Agents",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request schemas
class CreateMissionRequest(BaseModel):
    title: str
    goal: str
    repository_path: Optional[str] = "./demo/sample-project"
    constraints: Optional[MissionConstraints] = None


class PauseMissionRequest(BaseModel):
    reason: str = "Operator paused via Control Room"


class UpdateMissionStatusRequest(BaseModel):
    status: str
    reason: Optional[str] = "Status updated via Control Plane API"


class RegisterAgentRequest(BaseModel):
    agent_id: str
    agent_type: str = "WORKER"
    model: str = "nemotron"
    mission_id: Optional[str] = None
    task_id: Optional[str] = None
    status: str = "IDLE"
    metadata: Optional[Dict[str, Any]] = None


class UpdateAgentStateRequest(BaseModel):
    status: Optional[str] = None
    health: Optional[str] = None
    task_id: Optional[str] = None
    model: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class CreateTaskRequest(BaseModel):
    id: Optional[str] = None
    title: str
    dependencies: List[str] = []
    expected_files: List[str] = []
    order: Optional[int] = None


class UpdateTaskStatusRequest(BaseModel):
    status: str  # IN_PROGRESS, COMPLETED, FAILED, PENDING, VERIFIED
    agent_id: Optional[str] = None
    summary: Optional[str] = None
    error_signature: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class CreateApprovalRequest(BaseModel):
    mission_id: str
    agent_id: str
    action_type: str
    target: str
    reason: str
    risk_level: str = "high"
    task_id: Optional[str] = None


# --- Health & Readiness Probes ---
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Work Supervisor",
        "version": "1.0.0",
        "subsystems": {
            "event_bus": "operational",
            "event_store": "operational",
            "missions": len(await app_state.mission_manager.list_missions()),
            "agents": len(await app_state.agent_registry.list_agents()),
            "supervisor_engine": "watching"
        }
    }


@app.get("/ready")
async def readiness_probe():
    """
    Kubernetes / Cloud Readiness probe checking:
    1. Model / Reasoning Provider (Nebius Nemotron / local fallback)
    2. Execution Backend (Docker / local process sandbox)
    3. CI Verification (Jenkins HTTP / mock)
    4. Supervisor Engine Core
    """
    model_health = await app_state.reasoner.check_health()
    execution_health = await app_state.execution_manager.check_health()
    jenkins_health = await app_state.jenkins_client.check_health()

    is_ready = (
        model_health.get("status") in ("healthy", "degraded") and
        execution_health.get("status") == "healthy" and
        jenkins_health.get("status") in ("healthy", "degraded", "offline")
    )

    result = {
        "status": "ready" if is_ready else "not_ready",
        "service": "AI Work Supervisor",
        "model_provider": model_health,
        "execution_backend": execution_health,
        "jenkins_ci": jenkins_health,
        "supervisor": {
            "status": "watching",
            "active_missions": len(await app_state.mission_manager.list_missions()),
            "active_agents": len(await app_state.agent_registry.list_agents())
        }
    }

    if not is_ready:
        raise HTTPException(status_code=503, detail=result)
    return result


@app.get("/health/model")
async def model_health_check():
    """Detailed health check for NVIDIA Nemotron / Nebius inference provider."""
    return await app_state.reasoner.check_health()


@app.get("/health/jenkins")
async def jenkins_health_check():
    """Detailed health check for Jenkins CI integration."""
    return await app_state.jenkins_client.check_health()


@app.get("/health/execution")
async def execution_health_check():
    """Detailed health check for execution backends (Docker & local)."""
    return await app_state.execution_manager.check_health()


# --- Missions ---
@app.post("/api/missions", response_model=Mission)
async def create_mission(req: CreateMissionRequest):
    mission = await app_state.mission_manager.create_mission(
        title=req.title,
        goal=req.goal,
        repository_path=req.repository_path or "./demo/sample-project",
        constraints=req.constraints
    )
    return mission


@app.get("/api/missions", response_model=List[Mission])
async def list_missions():
    return await app_state.mission_manager.list_missions()


@app.get("/api/missions/{mission_id}", response_model=Mission)
async def get_mission(mission_id: str):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    return mission


@app.get("/api/missions/{mission_id}/state")
async def get_mission_state(mission_id: str):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    sm = app_state.supervisor_engine.get_state_machine(mission_id)
    telem = await app_state.telemetry.get_mission_telemetry(mission_id)
    agents = await app_state.agent_registry.list_agents(mission_id=mission_id)
    graph = await app_state.task_manager.get_graph(mission_id)
    total_tasks = len(graph.tasks) if graph else 0
    completed_tasks = telem.execution.completed_tasks

    return {
        "mission_id": mission.id,
        "title": mission.title,
        "status": mission.status.value,
        "supervisor_state": sm.current_state.value,
        "goal": mission.goal,
        "repository_path": mission.repository_path,
        "assigned_agents": [a.agent_id for a in agents],
        "active_agent_id": mission.active_agent_id,
        "current_task_id": mission.current_task_id,
        "tasks_count": total_tasks,
        "completed_tasks": completed_tasks,
        "constraints": mission.constraints.model_dump(),
        "metrics": mission.metrics.model_dump(),
        "telemetry": telem.model_dump(),
        "created_at": mission.created_at.isoformat(),
        "updated_at": mission.updated_at.isoformat()
    }


@app.post("/api/missions/{mission_id}/status")
@app.put("/api/missions/{mission_id}/state")
async def update_mission_state(mission_id: str, req: UpdateMissionStatusRequest):
    try:
        new_status = MissionStatus(req.status.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mission status '{req.status}'")
    mission = await app_state.mission_manager.update_status(mission_id, new_status, reason=req.reason)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "updated", "mission": mission}


@app.post("/api/missions/{mission_id}/start")
async def start_mission(mission_id: str):
    mission = await app_state.mission_manager.start_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "started", "mission": mission}


@app.post("/api/missions/{mission_id}/pause")
async def pause_mission(mission_id: str, req: Optional[PauseMissionRequest] = None):
    reason = req.reason if req else "Operator paused via Control Room"
    await app_state.supervisor_engine.pause(mission_id, reason=reason)
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "paused", "mission": mission}


@app.post("/api/missions/{mission_id}/resume")
async def resume_mission(mission_id: str):
    await app_state.supervisor_engine.resume(mission_id)
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "resumed", "mission": mission}


@app.post("/api/missions/{mission_id}/recover")
async def recover_mission(mission_id: str, reason: str = "Initiating supervisory recovery"):
    mission = await app_state.mission_manager.recover_mission(mission_id, reason=reason)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "recovering", "mission": mission}


@app.post("/api/missions/{mission_id}/verify")
async def verify_mission(mission_id: str):
    mission = await app_state.mission_manager.verify_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "verifying", "mission": mission}


@app.post("/api/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str, reason: str = "Cancelled by operator"):
    await app_state.supervisor_engine.cancel(mission_id, reason=reason)
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "cancelled", "mission": mission}


# --- Control Room & Telemetry ---
@app.get("/api/control-room/overview")
async def get_control_room_overview():
    missions = await app_state.mission_manager.list_missions()
    agents = await app_state.agent_registry.list_agents()
    active_missions = [m for m in missions if m.status in (MissionStatus.RUNNING, MissionStatus.RECOVERING, MissionStatus.VERIFYING)]

    telemetry_overview = await app_state.telemetry.get_global_overview(
        active_missions_count=len(active_missions),
        total_agents_count=len(agents)
    )

    # Build rich mission summary cards
    mission_cards = []
    for m in missions:
        m_telem = await app_state.telemetry.get_mission_telemetry(m.id)
        graph = await app_state.task_manager.get_graph(m.id)
        total_tasks = len(graph.tasks) if graph else 0
        completed_tasks = m_telem.execution.completed_tasks
        progress = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0

        mission_cards.append({
            "id": m.id,
            "title": m.title,
            "status": m.status.value,
            "current_task": m_telem.execution.current_task or m.current_task_id or "Planning",
            "progress_percentage": progress,
            "agents_count": len([a for a in agents if a.mission_id == m.id]),
            "tool_calls": m_telem.execution.tool_calls,
            "interventions": m_telem.reliability.interventions,
            "runtime_seconds": m_telem.execution.runtime_seconds,
            "created_at": m.created_at.isoformat()
        })

    return {
        "overview": telemetry_overview.model_dump(),
        "missions": mission_cards
    }


@app.get("/api/missions/{mission_id}/telemetry")
async def get_mission_telemetry(mission_id: str):
    telem = await app_state.telemetry.get_mission_telemetry(mission_id)
    return telem.model_dump()


# --- Tasks & Task Graph ---
@app.get("/api/missions/{mission_id}/tasks")
async def get_mission_tasks(mission_id: str):
    graph = await app_state.task_manager.get_graph(mission_id)
    if not graph:
        return {"tasks": [], "graph": {"nodes": [], "edges": []}}
    return {
        "tasks": list(graph.tasks.values()),
        "graph": graph.to_graph_data()
    }


@app.post("/api/missions/{mission_id}/tasks")
async def create_mission_task(mission_id: str, req: CreateTaskRequest):
    graph = await app_state.task_manager.get_graph(mission_id)
    task_id = req.id or (f"TASK-{len(graph.tasks) + 1:03d}" if graph else "TASK-001")
    task = Task(
        id=task_id,
        mission_id=mission_id,
        title=req.title,
        dependencies=req.dependencies,
        expected_files=req.expected_files,
        order=req.order or (len(graph.tasks) + 1 if graph else 1)
    )
    if not graph:
        await app_state.task_manager.initialize_mission_tasks(mission_id, [task])
    else:
        graph.add_task(task)
        await app_state.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task.id,
                type=EventType.TASK_CREATED,
                payload={
                    "task_id": task.id,
                    "title": task.title,
                    "dependencies": task.dependencies,
                    "expected_files": task.expected_files,
                    "order": task.order,
                }
            )
        )
    return {"status": "created", "task": task.model_dump()}


@app.get("/api/missions/{mission_id}/tasks/{task_id}")
async def get_task_endpoint(mission_id: str, task_id: str):
    task = await app_state.task_manager.get_task(mission_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found in mission {mission_id}")
    return task.model_dump()


@app.post("/api/missions/{mission_id}/tasks/{task_id}/status")
async def update_task_status(mission_id: str, task_id: str, req: UpdateTaskStatusRequest):
    st = req.status.upper()
    if st in ("IN_PROGRESS", "RUNNING"):
        task = await app_state.task_manager.start_task(mission_id, task_id, req.agent_id or "worker_01")
    elif st == "COMPLETED":
        task = await app_state.task_manager.complete_task(mission_id, task_id, summary=req.summary)
    elif st == "FAILED":
        task = await app_state.task_manager.fail_task(mission_id, task_id, error_signature=req.error_signature)
    elif st == "VERIFIED":
        caller_role = (req.agent_id or "WORKER").upper()
        meta = req.metadata or {}
        ci_passed = bool(meta.get("ci_passed", False))
        tests_passed = bool(meta.get("tests_passed", False))
        try:
            task = await app_state.task_manager.verify_task(
                mission_id=mission_id,
                task_id=task_id,
                caller_role=caller_role,
                ci_passed=ci_passed,
                tests_passed=tests_passed,
                evidence=meta
            )
        except PermissionError as pe:
            raise HTTPException(status_code=403, detail=str(pe))
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
    else:
        task = await app_state.task_manager.get_task(mission_id, task_id)
        if task:
            task.status = TaskStatus(st)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {"status": "updated", "task": task.model_dump()}


# --- Events, Timeline & Narrative ---
@app.get("/api/missions/{mission_id}/events")
async def get_mission_events(
    mission_id: str,
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    events = await app_state.event_store.query(mission_id=mission_id, limit=limit, offset=offset)
    return {"events": events, "count": len(events)}


@app.get("/api/missions/{mission_id}/timeline")
async def get_mission_timeline(mission_id: str):
    timeline = await app_state.event_store.get_mission_timeline(mission_id)
    return {"timeline": timeline}


@app.get("/api/missions/{mission_id}/supervisor-timeline")
async def get_supervisor_narrative_timeline(mission_id: str):
    from supervisor.timeline import SupervisorTimelineBuilder
    events = await app_state.event_store.query(mission_id=mission_id, limit=300)
    narrative = SupervisorTimelineBuilder.build_narrative_timeline(events)
    return {
        "mission_id": mission_id,
        "timeline": [item.model_dump() for item in narrative],
        "total_items": len(narrative)
    }


@app.get("/api/missions/{mission_id}/decisions")
async def get_supervisor_decisions(mission_id: str):
    events = await app_state.event_store.query(mission_id=mission_id, limit=300)
    decisions = [
        e.payload for e in events
        if e.type in (EventType.SUPERVISOR_DECISION, EventType.SUPERVISOR_INTERVENTION)
    ]
    return {"mission_id": mission_id, "decisions": decisions}


@app.get("/api/supervisor/events")
async def query_supervisor_events(
    mission_id: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    ev_type = None
    if event_type:
        try:
            ev_type = EventType(event_type)
        except ValueError:
            pass
    ev_sev = None
    if severity:
        try:
            ev_sev = EventSeverity(severity)
        except ValueError:
            pass

    events = await app_state.event_store.query(
        mission_id=mission_id,
        event_types=[ev_type] if ev_type else None,
        limit=limit,
        offset=offset
    )
    if ev_sev:
        events = [e for e in events if e.severity == ev_sev]
    return {"events": events, "count": len(events)}


@app.get("/api/supervisor/decisions")
async def list_all_supervisor_decisions(limit: int = 100):
    events = await app_state.event_store.query(limit=limit)
    decisions = [
        e.payload for e in events
        if e.type in (EventType.SUPERVISOR_DECISION, EventType.SUPERVISOR_INTERVENTION)
    ]
    return {"decisions": decisions, "count": len(decisions)}


# --- Agent Registry ---
@app.post("/api/agents")
async def register_agent_endpoint(req: RegisterAgentRequest):
    status_enum = AgentStatus.IDLE
    try:
        status_enum = AgentStatus(req.status.upper())
    except ValueError:
        pass
    record = await app_state.agent_registry.register_agent(
        agent_id=req.agent_id,
        agent_type=req.agent_type,
        model=req.model,
        mission_id=req.mission_id,
        status=status_enum,
        task_id=req.task_id,
        metadata=req.metadata
    )
    if req.mission_id:
        await app_state.mission_manager.assign_agent(req.mission_id, req.agent_id)
    return {"status": "registered", "agent": record.model_dump()}


@app.get("/api/agents")
async def list_agents(
    mission_id: Optional[str] = None,
    agent_type: Optional[str] = None,
    status: Optional[str] = None
):
    agents = await app_state.agent_registry.list_agents(
        mission_id=mission_id,
        agent_type=agent_type,
        status=status
    )
    return {"agents": [a.model_dump() for a in agents], "count": len(agents)}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = await app_state.agent_registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent.model_dump()


@app.get("/api/agents/{agent_id}/state")
async def get_agent_state(agent_id: str):
    agent = await app_state.agent_registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {
        "agent_id": agent.agent_id,
        "agent_type": agent.agent_type,
        "model": agent.model,
        "status": agent.status.value,
        "health": agent.health.value,
        "current_task": agent.current_task,
        "task_id": agent.task_id,
        "mission_id": agent.mission_id,
        "iterations": agent.iterations,
        "tool_calls": agent.tool_calls,
        "interventions": agent.interventions,
        "last_activity": agent.last_activity.isoformat(),
        "active_files": agent.active_files,
        "metadata": agent.metadata
    }


@app.put("/api/agents/{agent_id}/state")
async def update_agent_state(agent_id: str, req: UpdateAgentStateRequest):
    st_enum = None
    if req.status:
        try:
            st_enum = AgentStatus(req.status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid agent status '{req.status}'")
    hl_enum = None
    if req.health:
        try:
            hl_enum = AgentHealth(req.health.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid agent health '{req.health}'")

    updated = await app_state.agent_registry.update_agent(
        agent_id=agent_id,
        status=st_enum,
        health=hl_enum,
        task_id=req.task_id,
        model=req.model,
        metadata=req.metadata
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "updated", "agent": updated.model_dump()}


@app.post("/api/agents/{agent_id}/pause")
async def pause_agent(agent_id: str):
    success = await app_state.agent_registry.pause_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "paused", "agent_id": agent_id}


@app.post("/api/agents/{agent_id}/resume")
async def resume_agent(agent_id: str):
    success = await app_state.agent_registry.resume_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "resumed", "agent_id": agent_id}


# --- Human Approvals & Operator Control ---
@app.post("/api/approvals")
async def create_approval_endpoint(req: CreateApprovalRequest):
    req_obj = await app_state.approval_manager.create_request(
        mission_id=req.mission_id,
        agent_id=req.agent_id,
        action_type=req.action_type,
        target=req.target,
        reason=req.reason,
        risk_level=req.risk_level,
        task_id=req.task_id
    )
    return {"status": "created", "approval": req_obj.model_dump()}


@app.get("/api/approvals")
async def list_approvals(mission_id: Optional[str] = None):
    reqs = await app_state.approval_manager.list_requests(mission_id=mission_id)
    return {"approvals": [r.model_dump() for r in reqs], "count": len(reqs)}


@app.get("/api/approvals/{approval_id}")
async def get_approval_endpoint(approval_id: str):
    req = await app_state.approval_manager.get_request(approval_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Approval request {approval_id} not found")
    return req.model_dump()


@app.post("/api/approvals/{approval_id}/resolve")
async def resolve_approval(approval_id: str, payload: Dict[str, Any]):
    action_str = payload.get("action", "DENY")
    try:
        act = ApprovalResolutionAction(action_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action '{action_str}'")

    res = await app_state.approval_manager.resolve_request(
        approval_id,
        ResolveApprovalPayload(
            action=act,
            operator=payload.get("operator", "human_operator"),
            feedback=payload.get("feedback")
        )
    )
    if not res:
        raise HTTPException(status_code=404, detail=f"Approval request {approval_id} not found")
    return {"status": "resolved", "approval": res.model_dump()}


@app.post("/api/approvals/{approval_id}/cancel")
async def cancel_approval_endpoint(approval_id: str, payload: Optional[Dict[str, Any]] = None):
    operator = (payload or {}).get("operator", "human_operator")
    reason = (payload or {}).get("reason", "Cancelled by operator")
    res = await app_state.approval_manager.cancel_request(approval_id, operator=operator, reason=reason)
    if not res:
        raise HTTPException(status_code=404, detail=f"Approval request {approval_id} not found")
    return {"status": "cancelled", "approval": res.model_dump()}


@app.post("/api/missions/{mission_id}/take-control")
async def take_control(mission_id: str, operator: str = "human_operator", reason: str = "Operator taking manual control"):
    mission = await app_state.mission_manager.pause_mission(mission_id, reason=f"Manual control taken by {operator}: {reason}")
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")

    await app_state.event_bus.publish(
        Event(
            mission_id=mission_id,
            agent_id=operator,
            type=EventType.OPERATOR_TAKE_CONTROL,
            severity=EventSeverity.WARNING,
            payload={"operator": operator, "reason": reason}
        )
    )
    return {"status": "operator_in_control", "mission": mission}


# --- Policies ---
@app.get("/api/policies", response_model=PolicyConfig)
async def get_policies():
    return app_state.policy_config


@app.post("/api/policies", response_model=PolicyConfig)
async def update_policies(new_policy: PolicyConfig):
    app_state.policy_config = new_policy
    return app_state.policy_config


# --- Project Memory ---
class AddMemoryRecordRequest(BaseModel):
    fact: str
    source: str
    created_by: str = "agent"
    status: str = "OBSERVED"  # OBSERVED, INFERRED, DECIDED, VERIFIED, REJECTED
    confidence: float = 1.0
    category: str = "fact"
    details: Optional[str] = None


@app.get("/api/missions/{mission_id}/memory")
async def get_mission_memory(mission_id: str):
    summary = await app_state.memory_store.get_structured_summary(mission_id)
    all_recs = await app_state.memory_store.get_by_mission(mission_id)
    return {
        "mission_id": mission_id,
        "summary": summary,
        "records": [r.model_dump() for r in all_recs],
        "count": len(all_recs)
    }


@app.post("/api/missions/{mission_id}/memory")
async def add_mission_memory(mission_id: str, req: AddMemoryRecordRequest):
    from memory.provenance import FactStatus
    try:
        st = FactStatus(req.status.upper())
    except ValueError:
        st = FactStatus.OBSERVED

    record = await app_state.memory_store.add_record(
        mission_id=mission_id,
        fact=req.fact,
        source=req.source,
        created_by=req.created_by,
        status=st,
        confidence=req.confidence,
        category=req.category,
        details=req.details
    )
    return {"status": "created", "record": record.model_dump()}


@app.get("/api/memory")
async def list_all_memory(mission_id: Optional[str] = None, category: Optional[str] = None):
    if mission_id:
        recs = await app_state.memory_store.get_by_mission(mission_id, category=category)
    else:
        async with app_state.memory_store._lock:
            recs = list(app_state.memory_store._records.values())
            if category:
                recs = [r for r in recs if r.category == category]
    return {"records": [r.model_dump() for r in recs], "count": len(recs)}


# --- Seed Demo Mission Helper ---
@app.post("/api/missions/seed-demo")
async def seed_demo_mission():
    """
    Seeds the standard 'Add CSV Import' demo mission with the 6 DAG tasks
    ready for execution and visualization in the Control Room.
    """
    mission = await app_state.mission_manager.create_mission(
        title="Add CSV Import Validation",
        goal="Implement robust CSV parser and import validation without modifying database schema",
        repository_path="./demo/sample-project"
    )

    tasks = [
        Task(id="TASK-001", mission_id=mission.id, title="Inspect existing data model", order=1, expected_files=["src/models.py"]),
        Task(id="TASK-002", mission_id=mission.id, title="Design CSV parser", dependencies=["TASK-001"], order=2, expected_files=["src/parser.py"]),
        Task(id="TASK-003", mission_id=mission.id, title="Implement importer", dependencies=["TASK-002"], order=3, expected_files=["src/importer.py"]),
        Task(id="TASK-004", mission_id=mission.id, title="Add validation", dependencies=["TASK-003"], order=4, expected_files=["src/validator.py"]),
        Task(id="TASK-005", mission_id=mission.id, title="Run tests", dependencies=["TASK-004"], order=5, expected_files=["tests/test_parser.py"]),
        Task(id="TASK-006", mission_id=mission.id, title="Verify integration", dependencies=["TASK-005"], order=6, expected_files=["src/main.py"]),
    ]

    await app_state.task_manager.initialize_mission_tasks(mission.id, tasks)

    # Seed active agent records
    await app_state.agent_registry.register_agent("planner_01", "PLANNER", mission_id=mission.id)
    await app_state.agent_registry.register_agent("worker_01", "WORKER", mission_id=mission.id, task_id="TASK-001")
    await app_state.agent_registry.register_agent("reviewer_01", "REVIEWER", mission_id=mission.id)
    await app_state.agent_registry.register_agent("verifier_01", "VERIFIER", mission_id=mission.id)

    # Seed initial project memory records
    from memory.provenance import FactStatus
    await app_state.memory_store.add_record(
        mission_id=mission.id,
        fact="CSV parser must support UTF-8 BOM encoding without raising UnicodeDecodeError",
        source="jenkins_build_481",
        created_by="reviewer_01",
        status=FactStatus.VERIFIED,
        confidence=1.0,
        category="verified_fact",
        details="Empirical proof: pytest test_parser.py 47/47 passed"
    )
    await app_state.memory_store.add_record(
        mission_id=mission.id,
        fact="Naive string slicing without stripping BOM character causes header mismatch",
        source="test_parse_failure_log",
        created_by="reviewer_01",
        status=FactStatus.REJECTED,
        confidence=0.95,
        category="rejected_approach",
        details="Disproven in attempt 1 & 2; repeated application blocked by Supervisor"
    )
    await app_state.memory_store.add_record(
        mission_id=mission.id,
        fact="Database schema in schema.sql is strictly immutable for this mission",
        source="MissionConstraints",
        created_by="supervisor",
        status=FactStatus.DECIDED,
        confidence=1.0,
        category="decision",
        details="Enforced via policy.prevent_modifications_outside_task_scope"
    )

    return {
        "status": "seeded",
        "mission_id": mission.id,
        "tasks_count": len(tasks),
        "mission": mission
    }


# --- WebSocket Stream ---
@app.websocket("/ws/events")
async def websocket_event_stream(websocket: WebSocket):
    await ws_hub.connect(websocket)
    try:
        while True:
            # Keep alive and listen for client commands
            data = await websocket.receive_text()
            logger.debug(f"Received client message over WS: {data}")
            if "ping" in data.lower():
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await ws_hub.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        await ws_hub.disconnect(websocket)
