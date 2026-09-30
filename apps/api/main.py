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


# --- Health ---
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Work Supervisor",
        "subsystems": {
            "event_bus": "operational",
            "event_store": "operational",
            "missions": len(await app_state.mission_manager.list_missions()),
        }
    }


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


@app.post("/api/missions/{mission_id}/start")
async def start_mission(mission_id: str):
    mission = await app_state.mission_manager.start_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "started", "mission": mission}


@app.post("/api/missions/{mission_id}/pause")
async def pause_mission(mission_id: str, req: PauseMissionRequest):
    mission = await app_state.mission_manager.pause_mission(mission_id, reason=req.reason)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "paused", "mission": mission}


@app.post("/api/missions/{mission_id}/resume")
async def resume_mission(mission_id: str):
    mission = await app_state.mission_manager.resume_mission(mission_id)
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
    mission = await app_state.mission_manager.cancel_mission(mission_id, reason=reason)
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


# --- Agent Registry ---
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
@app.get("/api/approvals")
async def list_approvals(mission_id: Optional[str] = None):
    reqs = await app_state.approval_manager.list_requests(mission_id=mission_id)
    return {"approvals": [r.model_dump() for r in reqs], "count": len(reqs)}


@app.post("/api/approvals/{approval_id}/resolve")
async def resolve_approval(approval_id: str, payload: Dict[str, Any]):
    from supervisor.approvals import ResolveApprovalPayload, ApprovalResolutionAction
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
    except WebSocketDisconnect:
        await ws_hub.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        await ws_hub.disconnect(websocket)
