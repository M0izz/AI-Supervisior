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


# --- Events & Timeline ---
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
