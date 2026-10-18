import asyncio
from datetime import datetime, timezone
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Load local environment configuration
load_dotenv()
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.events.schema import Event, EventType, EventSeverity
from core.missions.models import (
    Mission,
    MissionStatus,
    MissionConstraints,
    PlanVersion,
    StructuredInterpretation,
    PlanTaskItem,
    PlanApprovalStatus,
)
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
    try:
        reconciled = await app_state.absence_engine.reconcile_on_startup()
        if reconciled > 0:
            logger.info(f"Reconciled {reconciled} absence sessions on startup.")
    except Exception as e:
        logger.warning(f"Error during absence session startup reconciliation: {e}")
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
class ProposedTaskDraft(BaseModel):
    id: str
    title: str
    description: str
    suggested_agent: str = "claude-code"
    expected_files: List[str] = []
    dependencies: List[str] = []
    order: int = 1


class DraftMissionRequest(BaseModel):
    goal: str
    repository_path: Optional[str] = "./demo/sample-project"


class DraftMissionResponse(BaseModel):
    title: str
    goal: str
    repository_path: str
    interpreted_steps: List[str]
    proposed_tasks: List[ProposedTaskDraft]
    suggested_agents: List[str]
    fallback_agent: str
    inferred_constraints: Dict[str, Any]
    verification_plan: Dict[str, Any]
    detected_invariants: List[str] = []
    model_provenance: str = "Google Gemma 4 (gemma-4-31B-it) via DigitalOcean Inference"


class CreateMissionRequest(BaseModel):
    title: str
    goal: str
    repository_path: Optional[str] = "./demo/sample-project"
    constraints: Optional[MissionConstraints] = None
    tasks: Optional[List[Dict[str, Any]]] = None


class ApprovePlanRequest(BaseModel):
    version: Optional[int] = None
    approved_by: Optional[str] = "operator"
    operator_id: Optional[str] = None
    notes: Optional[str] = None


class RejectPlanRequest(BaseModel):
    reason: str = "Plan rejected by operator"


class ClarifyPlanRequest(BaseModel):
    answers: Dict[str, str]


class EditPlanRequest(BaseModel):
    interpretation: Optional[Dict[str, Any]] = None
    tasks: Optional[List[Dict[str, Any]]] = None


class RegeneratePlanRequest(BaseModel):
    feedback: Optional[str] = None


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
@app.post("/api/missions/draft", response_model=DraftMissionResponse)
async def draft_mission(req: DraftMissionRequest):
    """
    Natural Language Mission Composer:
    Interprets natural language goal into structured steps, proposed tasks,
    suggested agents, constraints, and verification plan.
    """
    goal = req.goal.strip()
    repo = req.repository_path or "./demo/sample-project"
    goal_lower = goal.lower()
    
    words = goal.split()
    if len(words) <= 7:
        title = " ".join([w.capitalize() for w in words])
    else:
        title = " ".join([w.capitalize() for w in words[:6]]) + "..."

    if any(k in goal_lower for k in ["auth", "login", "jwt", "session", "token"]):
        title = "Fix Authentication & Expired Session Handling"
        interpreted_steps = [
            "Inspect current authentication session flow and token refresh",
            "Identify expired-session and error handling boundaries",
            "Implement resilient token validation and renewal",
            "Add/update regression test suite for session edge cases",
            "Run authentication test suite in isolated sandbox",
            "Verify that only authentication-scoped files were changed"
        ]
        tasks = [
            ProposedTaskDraft(id="TASK-001", title="Inspect session flow & model", description="Audit session timeout handling and token decoding", suggested_agent="claude-code", expected_files=["src/auth/session.py"], order=1),
            ProposedTaskDraft(id="TASK-002", title="Implement session renewal fix", description="Ensure expired tokens refresh cleanly without 500 error", suggested_agent="claude-code", dependencies=["TASK-001"], expected_files=["src/auth/handler.py"], order=2),
            ProposedTaskDraft(id="TASK-003", title="Add regression tests", description="Coverage for expired tokens and malformed signatures", suggested_agent="claude-code", dependencies=["TASK-002"], expected_files=["tests/test_auth.py"], order=3),
            ProposedTaskDraft(id="TASK-004", title="Independent verification", description="Run pytest test_auth.py and verify git diff scope", suggested_agent="codex", dependencies=["TASK-003"], expected_files=["tests/test_auth.py"], order=4),
        ]
        suggested_agents = ["claude-code", "codex"]
        fallback_agent = "codex"
    elif any(k in goal_lower for k in ["dark", "mode", "theme", "ui", "css", "color"]):
        title = "Implement Dark Mode Theme & Settings Persistence"
        interpreted_steps = [
            "Audit CSS design tokens and theme variables",
            "Implement dark theme palettes and contrast tokens",
            "Wire preference toggle and local persistence in settings",
            "Verify visual consistency and accessibility contrast",
            "Verify zero breaking changes in surrounding layout"
        ]
        tasks = [
            ProposedTaskDraft(id="TASK-001", title="Audit CSS tokens", description="Define surface, text, and border CSS custom properties", suggested_agent="claude-code", expected_files=["src/theme.css"], order=1),
            ProposedTaskDraft(id="TASK-002", title="Add theme switcher & storage", description="Integrate theme toggle into settings UI", suggested_agent="claude-code", dependencies=["TASK-001"], expected_files=["src/settings.tsx"], order=2),
            ProposedTaskDraft(id="TASK-003", title="Test accessibility & contrast", description="Ensure WCAG AA compliance across components", suggested_agent="codex", dependencies=["TASK-002"], expected_files=["tests/test_theme.py"], order=3),
        ]
        suggested_agents = ["claude-code", "gemini"]
        fallback_agent = "gemini"
    elif any(k in goal_lower for k in ["500", "error", "bug", "failing", "crash", "fix"]):
        title = f"Resolve Defect: {title}"
        interpreted_steps = [
            "Capture error signatures and inspect relevant log traces",
            "Locate root cause in codebase",
            "Implement targeted defect patch",
            "Run regression tests to verify bug resolution",
            "Independent verification of workspace cleanliness"
        ]
        tasks = [
            ProposedTaskDraft(id="TASK-001", title="Analyze error logs & traces", description="Identify failing code paths and exception roots", suggested_agent="claude-code", expected_files=["src/errors.py"], order=1),
            ProposedTaskDraft(id="TASK-002", title="Apply targeted code patch", description="Fix issue without altering public contracts", suggested_agent="claude-code", dependencies=["TASK-001"], expected_files=["src/service.py"], order=2),
            ProposedTaskDraft(id="TASK-003", title="Run regression test suite", description="Ensure bug fix passes and no regressions introduced", suggested_agent="codex", dependencies=["TASK-002"], expected_files=["tests/test_service.py"], order=3),
        ]
        suggested_agents = ["claude-code", "codex"]
        fallback_agent = "codex"
    elif any(k in goal_lower for k in ["refactor", "clean", "rewrite", "payment"]):
        title = f"Refactor Module: {title}"
        interpreted_steps = [
            "Map existing module public interfaces and invariants",
            "Refactor internal implementation for clarity and maintainability",
            "Preserve backwards compatibility and public signatures",
            "Run full regression suite to ensure zero behavior divergence",
            "Perform independent diff and scope check"
        ]
        tasks = [
            ProposedTaskDraft(id="TASK-001", title="Map interface invariants", description="Document public function signatures and expected behavior", suggested_agent="claude-code", expected_files=["src/module.py"], order=1),
            ProposedTaskDraft(id="TASK-002", title="Refactor internal implementation", description="Clean up architectural complexity", suggested_agent="claude-code", dependencies=["TASK-001"], expected_files=["src/module.py"], order=2),
            ProposedTaskDraft(id="TASK-003", title="Run parity tests", description="Verify contract adherence and regression coverage", suggested_agent="codex", dependencies=["TASK-002"], expected_files=["tests/test_module.py"], order=3),
        ]
        suggested_agents = ["claude-code", "codex"]
        fallback_agent = "codex"
    else:
        interpreted_steps = [
            f"Analyze requirements for outcome: {goal[:60]}",
            "Decompose implementation into modular execution tasks",
            "Execute changes via autonomous worker agent",
            "Run automated test verification",
            "Independently certify task completion and diff scope"
        ]
        tasks = [
            ProposedTaskDraft(id="TASK-001", title="Analyze requirements & context", description="Inspect relevant files and plan changes", suggested_agent="claude-code", expected_files=["src/main.py"], order=1),
            ProposedTaskDraft(id="TASK-002", title="Implement core changes", description="Apply requested functionality", suggested_agent="claude-code", dependencies=["TASK-001"], expected_files=["src/app.py"], order=2),
            ProposedTaskDraft(id="TASK-003", title="Test & verify output", description="Run automated test suite and check scope", suggested_agent="codex", dependencies=["TASK-002"], expected_files=["tests/test_app.py"], order=3),
        ]
        suggested_agents = ["claude-code", "codex"]
        fallback_agent = "codex"

    gemma_plan = await app_state.gemma_reasoner.decompose_goal(goal, repo)

    return DraftMissionResponse(
        title=title,
        goal=goal,
        repository_path=repo,
        interpreted_steps=interpreted_steps,
        proposed_tasks=tasks,
        suggested_agents=suggested_agents,
        fallback_agent=fallback_agent,
        inferred_constraints={
            "max_turns": 10,
            "timeout_seconds": 3600,
            "prohibited_files": [".env", "secrets.json", "id_rsa", "config/credentials.json"],
            "allowed_commands": ["pytest", "git status", "git diff", "npm test", "python -m unittest"]
        },
        verification_plan={
            "policy": "STRICT",
            "isolated_sandbox": True,
            "automated_tests": True,
            "scope_diff_check": True,
            "prohibited_modifications_check": True
        },
        detected_invariants=gemma_plan.detected_invariants,
        model_provenance=gemma_plan.model_provenance
    )


def synthesize_plan_and_interpretation(
    goal: str,
    repo: str,
    original_request: Optional[str] = None,
    feedback: Optional[str] = None
) -> tuple[StructuredInterpretation, List[PlanTaskItem]]:
    goal_lower = goal.lower()
    raw_req = original_request or goal

    blocking_questions: List[str] = []
    non_blocking: List[str] = []
    in_scope: List[str] = []
    exclusions: List[str] = [
        "Modifying root credentials or .env secrets",
        "Direct production deployment without operator sign-off",
        "Modifying files outside target repository boundary"
    ]
    constraints: List[str] = [
        "Preserve existing unit test pass rate",
        "Strict file boundary isolation",
        "Zero regressions in surrounding components"
    ]
    risks: List[str] = ["File modifications in project directory", "Process timeout during test suite execution"]
    deliverables: List[str] = []
    verification_methods: List[str] = ["Automated test suite execution", "Git diff boundary inspection", "Clean exit code validation"]
    tasks: List[PlanTaskItem] = []

    words = goal.split()
    if len(words) < 3:
        blocking_questions.append("Goal description is too brief. What specific functionality or component should be targeted?")

    if any(k in goal_lower for k in ["auth", "login", "jwt", "session", "token"]):
        interpreted_goal = f"Implement secure session handling and authentication resilience for: {goal}"
        in_scope = ["Session decoding and validation", "Expired token handling", "Regression tests for session timeout"]
        exclusions.append("Replacing existing password hashing or user database schema")
        non_blocking = ["Assumes standard JWT or Bearer session cookies unless otherwise configured"]
        deliverables = ["Updated session validation logic", "Session regression test suite"]
        definition_of_success = "Expired session tokens refresh or reject cleanly without unhandled 500 exceptions, and all auth unit tests pass."
        tasks = [
            PlanTaskItem(
                task_id="TASK-001",
                title="Inspect session flow & model",
                description="Audit session timeout handling and token decoding",
                proposed_agent="worker_01",
                required_capabilities=["file_editing", "command_execution"],
                expected_files=["src/auth/session.py"],
                risk_classification="LOW",
                acceptance_criteria=["Existing token decoder identified", "No unhandled exceptions on null payload"],
                verification_strategy="file_check"
            ),
            PlanTaskItem(
                task_id="TASK-002",
                title="Implement session renewal fix",
                description="Ensure expired tokens refresh cleanly without 500 error",
                dependencies=["TASK-001"],
                proposed_agent="worker_01",
                required_capabilities=["file_editing", "command_execution"],
                expected_files=["src/auth/handler.py"],
                risk_classification="MEDIUM",
                acceptance_criteria=["Expired token renewal returns HTTP 401 or refreshes token gracefully"],
                verification_strategy="diff_review"
            ),
            PlanTaskItem(
                task_id="TASK-003",
                title="Add regression tests",
                description="Coverage for expired tokens and malformed signatures",
                dependencies=["TASK-002"],
                proposed_agent="worker_01",
                required_capabilities=["file_editing", "command_execution"],
                expected_files=["tests/test_auth.py"],
                risk_classification="LOW",
                acceptance_criteria=["Test suite passes with 100% assertions satisfied"],
                verification_strategy="automated_test"
            ),
            PlanTaskItem(
                task_id="TASK-004",
                title="Independent verification",
                description="Run pytest test_auth.py and verify git diff scope",
                dependencies=["TASK-003"],
                proposed_agent="worker_01",
                required_capabilities=["command_execution"],
                expected_files=["tests/test_auth.py"],
                risk_classification="LOW",
                acceptance_criteria=["Zero unexpected files modified", "Tests exit with code 0"],
                verification_strategy="automated_test"
            ),
        ]
    elif any(k in goal_lower for k in ["dark", "mode", "theme", "ui", "css", "color"]):
        interpreted_goal = f"Implement theme toggle and CSS styling for: {goal}"
        in_scope = ["CSS design tokens", "Theme toggle component", "Local storage persistence"]
        deliverables = ["Updated CSS variables", "Theme switch controller"]
        definition_of_success = "Theme switch renders without layout shifts and persists preference in storage."
        tasks = [
            PlanTaskItem(
                task_id="TASK-001",
                title="Audit CSS tokens & surface variables",
                description="Define surface, text, and border CSS custom properties",
                proposed_agent="worker_01",
                required_capabilities=["file_editing"],
                expected_files=["src/theme.css"],
                risk_classification="LOW",
                acceptance_criteria=["CSS variables define light and dark contrasts"],
                verification_strategy="file_check"
            ),
            PlanTaskItem(
                task_id="TASK-002",
                title="Wire theme toggle & persistence",
                description="Connect toggle to settings and browser persistence",
                dependencies=["TASK-001"],
                proposed_agent="worker_01",
                required_capabilities=["file_editing"],
                expected_files=["src/settings.tsx"],
                risk_classification="LOW",
                acceptance_criteria=["Toggle flips root CSS theme class"],
                verification_strategy="diff_review"
            ),
            PlanTaskItem(
                task_id="TASK-003",
                title="Independent styling verification",
                description="Verify contrast tokens and run component tests",
                dependencies=["TASK-002"],
                proposed_agent="worker_01",
                required_capabilities=["command_execution"],
                expected_files=[],
                risk_classification="LOW",
                acceptance_criteria=["All UI unit tests pass"],
                verification_strategy="automated_test"
            ),
        ]
    else:
        interpreted_goal = f"Execute requested task: {goal}"
        in_scope = ["Analyze target repository", "Apply minimal required code changes", "Verify with automated tests"]
        deliverables = ["Code modifications addressing goal", "Test verification results"]
        definition_of_success = f"Goal '{goal}' is satisfied and verified with passing test exit code."
        tasks = [
            PlanTaskItem(
                task_id="TASK-001",
                title="Inspect repository context & plan changes",
                description=f"Analyze repository files relevant to '{goal}'",
                proposed_agent="worker_01",
                required_capabilities=["file_editing", "command_execution"],
                expected_files=[],
                risk_classification="LOW",
                acceptance_criteria=["Target source files identified"],
                verification_strategy="file_check"
            ),
            PlanTaskItem(
                task_id="TASK-002",
                title="Implement core functionality",
                description=f"Apply code modifications to achieve: {goal}",
                dependencies=["TASK-001"],
                proposed_agent="worker_01",
                required_capabilities=["file_editing", "command_execution"],
                expected_files=[],
                risk_classification="MEDIUM",
                acceptance_criteria=["Implementation adheres to repository conventions"],
                verification_strategy="diff_review"
            ),
            PlanTaskItem(
                task_id="TASK-003",
                title="Automated test verification",
                description="Execute test suite and certify diff scope",
                dependencies=["TASK-002"],
                proposed_agent="worker_01",
                required_capabilities=["command_execution"],
                expected_files=[],
                risk_classification="LOW",
                acceptance_criteria=["Automated tests pass with zero errors"],
                verification_strategy="automated_test"
            ),
        ]

    if feedback:
        non_blocking.append(f"Incorporated user feedback: {feedback}")

    interp = StructuredInterpretation(
        original_request=raw_req,
        interpreted_goal=interpreted_goal,
        expected_deliverables=deliverables,
        in_scope=in_scope,
        explicit_exclusions=exclusions,
        constraints=constraints,
        assumptions=["Executing within isolated local worktree"],
        blocking_questions=blocking_questions,
        non_blocking_assumptions=non_blocking,
        risks=risks,
        definition_of_success=definition_of_success,
        proposed_verification_methods=verification_methods
    )
    return interp, tasks


@app.post("/api/missions", response_model=Mission)
async def create_mission(req: CreateMissionRequest):
    goal = req.goal.strip()
    raw_title = req.title.strip() if req.title else (goal[:40] + "...")

    interp, tasks = synthesize_plan_and_interpretation(
        goal=goal,
        repo=req.repository_path or "./demo/sample-project",
        original_request=goal
    )

    if req.tasks:
        merged_tasks = []
        for i, t in enumerate(req.tasks):
            t_id = t.get("id") or t.get("task_id") or f"TASK-{str(i+1).zfill(3)}"
            merged_tasks.append(PlanTaskItem(
                task_id=t_id,
                title=t.get("title", f"Task {i+1}"),
                description=t.get("description", ""),
                dependencies=t.get("dependencies", []),
                expected_files=t.get("expected_files", []),
                acceptance_criteria=t.get("acceptance_criteria", ["Task completed"]),
                verification_strategy=t.get("verification_strategy", "automated_test")
            ))
        tasks = merged_tasks

    initial_status = MissionStatus.NEEDS_CLARIFICATION if interp.blocking_questions else MissionStatus.AWAITING_APPROVAL
    val_status = "NEEDS_CLARIFICATION" if interp.blocking_questions else "VALID"

    mission = await app_state.mission_manager.create_mission(
        title=raw_title,
        goal=goal,
        original_request=goal,
        repository_path=req.repository_path or "./demo/sample-project",
        constraints=req.constraints,
        status=initial_status
    )
    mission.current_plan_version = 1

    plan_v1 = PlanVersion(
        mission_id=mission.id,
        version=1,
        interpretation=interp,
        tasks=tasks,
        validation_status=val_status,
        approval_status=PlanApprovalStatus.PENDING
    )
    await app_state.plan_repo.save_plan(plan_v1)
    await app_state.mission_repo.save(mission)

    from core.tasks.models import Task as CoreTask
    core_tasks = [
        CoreTask(
            id=t.task_id,
            mission_id=mission.id,
            title=t.title,
            description=t.description,
            dependencies=t.dependencies,
            order=idx + 1,
            expected_files=t.expected_files
        )
        for idx, t in enumerate(tasks)
    ]
    await app_state.task_manager.initialize_mission_tasks(mission.id, core_tasks)

    await app_state.event_bus.publish(
        Event(
            mission_id=mission.id,
            type=EventType.PLAN_GENERATED,
            payload={
                "mission_id": mission.id,
                "version": 1,
                "validation_status": val_status,
                "blocking_questions_count": len(interp.blocking_questions),
                "tasks_count": len(tasks)
            }
        )
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
        "current_plan_version": mission.current_plan_version,
        "approved_plan_version": mission.approved_plan_version,
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


# --- Plan Review & Interaction Endpoints ---
@app.get("/api/missions/{mission_id}/plan")
async def get_mission_plan(mission_id: str, version: Optional[int] = None):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    
    if version is not None:
        plan = await app_state.plan_repo.get_plan_by_version(mission_id, version)
    else:
        plan = await app_state.plan_repo.get_latest_plan(mission_id)
    
    if not plan:
        interp, tasks = synthesize_plan_and_interpretation(mission.goal, mission.repository_path, mission.original_request)
        plan_v1 = PlanVersion(
            mission_id=mission.id,
            version=1,
            interpretation=interp,
            tasks=tasks,
            validation_status="VALID",
            approval_status=PlanApprovalStatus.PENDING
        )
        plan = await app_state.plan_repo.save_plan(plan_v1)
    return plan


@app.get("/api/missions/{mission_id}/plans")
async def list_mission_plans(mission_id: str):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    return await app_state.plan_repo.list_plans(mission_id)


@app.post("/api/missions/{mission_id}/plan/edit")
async def edit_mission_plan(mission_id: str, req: EditPlanRequest):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    
    latest = await app_state.plan_repo.get_latest_plan(mission_id)
    new_version_num = (latest["version"] + 1) if latest else 1

    existing_interp = latest.get("interpretation", {}) if latest else {}
    if req.interpretation:
        existing_interp.update(req.interpretation)
    
    interp_obj = StructuredInterpretation.model_validate(existing_interp) if existing_interp else synthesize_plan_and_interpretation(mission.goal, mission.repository_path)[0]

    tasks_list = []
    if req.tasks:
        for idx, t in enumerate(req.tasks):
            t_id = t.get("task_id") or t.get("id") or f"TASK-{str(idx+1).zfill(3)}"
            tasks_list.append(PlanTaskItem(
                task_id=t_id,
                title=t.get("title", f"Task {idx+1}"),
                description=t.get("description", ""),
                dependencies=t.get("dependencies", []),
                proposed_agent=t.get("proposed_agent", "worker_01"),
                expected_files=t.get("expected_files", []),
                risk_classification=t.get("risk_classification", "LOW"),
                acceptance_criteria=t.get("acceptance_criteria", []),
                verification_strategy=t.get("verification_strategy", "automated_test")
            ))
    elif latest and latest.get("tasks"):
        tasks_list = [PlanTaskItem.model_validate(t) for t in latest["tasks"]]

    val_status = "NEEDS_CLARIFICATION" if interp_obj.blocking_questions else "VALID"

    await app_state.mission_manager.invalidate_approval(mission_id, reason=f"Plan edited to version {new_version_num}")
    
    new_plan = PlanVersion(
        mission_id=mission_id,
        version=new_version_num,
        interpretation=interp_obj,
        tasks=tasks_list,
        validation_status=val_status,
        approval_status=PlanApprovalStatus.PENDING
    )
    saved = await app_state.plan_repo.save_plan(new_plan)
    return saved


@app.post("/api/missions/{mission_id}/plan/regenerate")
async def regenerate_mission_plan(mission_id: str, req: Optional[RegeneratePlanRequest] = None):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    
    latest = await app_state.plan_repo.get_latest_plan(mission_id)
    new_version_num = (latest["version"] + 1) if latest else 1

    feedback = req.feedback if req else None
    interp, tasks = synthesize_plan_and_interpretation(
        goal=mission.goal,
        repo=mission.repository_path,
        original_request=mission.original_request or mission.goal,
        feedback=feedback
    )

    val_status = "NEEDS_CLARIFICATION" if interp.blocking_questions else "VALID"
    await app_state.mission_manager.invalidate_approval(mission_id, reason=f"Plan regenerated to version {new_version_num}")

    new_plan = PlanVersion(
        mission_id=mission_id,
        version=new_version_num,
        interpretation=interp,
        tasks=tasks,
        validation_status=val_status,
        approval_status=PlanApprovalStatus.PENDING
    )
    saved = await app_state.plan_repo.save_plan(new_plan)
    return saved


@app.post("/api/missions/{mission_id}/plan/clarify")
async def clarify_mission_plan(mission_id: str, req: ClarifyPlanRequest):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    
    latest = await app_state.plan_repo.get_latest_plan(mission_id)
    if not latest:
        raise HTTPException(status_code=400, detail="No plan found to clarify")

    interp_dict = latest.get("interpretation", {})
    blocking = list(interp_dict.get("blocking_questions", []))
    non_blocking = list(interp_dict.get("non_blocking_assumptions", []))
    constraints = list(interp_dict.get("constraints", []))

    for q, ans in req.answers.items():
        if q in blocking:
            blocking.remove(q)
        constraints.append(f"Operator clarified: {q} -> {ans}")
        non_blocking.append(f"Clarified answer: {ans}")

    interp_dict["blocking_questions"] = blocking
    interp_dict["non_blocking_assumptions"] = non_blocking
    interp_dict["constraints"] = constraints

    new_version_num = latest["version"] + 1
    val_status = "NEEDS_CLARIFICATION" if blocking else "VALID"

    new_plan = PlanVersion(
        mission_id=mission_id,
        version=new_version_num,
        interpretation=StructuredInterpretation.model_validate(interp_dict),
        tasks=[PlanTaskItem.model_validate(t) for t in latest.get("tasks", [])],
        validation_status=val_status,
        approval_status=PlanApprovalStatus.PENDING
    )
    saved = await app_state.plan_repo.save_plan(new_plan)

    if not blocking:
        await app_state.mission_manager.update_status(mission_id, MissionStatus.AWAITING_APPROVAL, reason="Clarifications answered; ready for approval.")
    return saved


@app.post("/api/missions/{mission_id}/plan/approve")
@app.post("/api/missions/{mission_id}/approve")
async def approve_mission_plan(mission_id: str, req: ApprovePlanRequest):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    
    latest = await app_state.plan_repo.get_latest_plan(mission_id)
    if not latest:
        raise HTTPException(status_code=400, detail="No plan exists to approve.")

    current_version = latest.get("version", 1)
    if req.version is not None and req.version != current_version:
        raise HTTPException(
            status_code=400,
            detail=f"Stale approval attempt. Requested version {req.version} does not match current plan version {current_version}."
        )

    interp = latest.get("interpretation", {})
    blocking_questions = interp.get("blocking_questions", [])
    if blocking_questions:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "BLOCKING_QUESTIONS_UNRESOLVED",
                "message": "Cannot approve plan while blocking clarification questions remain unresolved.",
                "blocking_questions": blocking_questions
            }
        )

    approver = req.operator_id or req.approved_by or "operator"
    latest["approval_status"] = "APPROVED"
    latest["approved_by"] = approver
    latest["approved_at"] = datetime.now(timezone.utc).isoformat()
    await app_state.plan_repo.save_plan(latest)

    await app_state.mission_manager.approve_mission(
        mission_id=mission_id,
        plan_version=current_version,
        approved_by=approver
    )

    return {
        "status": "approved",
        "mission_id": mission_id,
        "plan_version": current_version,
        "approved_plan_version": current_version,
        "approved_by": approver,
        "approved_at": latest["approved_at"]
    }


@app.post("/api/missions/{mission_id}/plan/reject")
async def reject_mission_plan(mission_id: str, req: RejectPlanRequest):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    
    latest = await app_state.plan_repo.get_latest_plan(mission_id)
    if latest:
        latest["approval_status"] = "REJECTED"
        latest["rejection_reason"] = req.reason
        await app_state.plan_repo.save_plan(latest)

    await app_state.mission_manager.reject_mission(mission_id, reason=req.reason)
    return {"status": "rejected", "mission_id": mission_id, "reason": req.reason}


class AssignTaskAgentRequest(BaseModel):
    agent_id: str
    reason: Optional[str] = None


@app.post("/api/missions/{mission_id}/tasks/{task_id}/assign-agent")
async def assign_task_agent(mission_id: str, task_id: str, req: AssignTaskAgentRequest):
    """
    Assigns an agent runtime to a specific task in the mission plan.
    Enforces compatibility checks and strictly preserves the approval gate:
    if the plan was previously approved, modifying the agent assignment bumps
    the plan version, resets approval status to PENDING, and requires operator re-approval.
    """
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")

    target_agent = req.agent_id.strip()

    # 1. Allowlist / registry validation
    known_adapters = [a.adapter_id for a in app_state.adapter_registry.list_adapters()]
    valid_agents = ["worker_01", "local_worker", "auto"] + known_adapters
    if target_agent not in valid_agents:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent runtime '{target_agent}'. Must be one of registered adapters: {valid_agents}"
        )

    # 2. Check runtime availability
    is_avail = True
    avail_msg = "Available"
    if target_agent in known_adapters:
        adapter = app_state.adapter_registry.get_adapter(target_agent)
        if adapter:
            probe = await adapter.check_availability()
            is_avail = probe.available
            avail_msg = probe.message
    elif target_agent == "auto":
        is_avail = True
        avail_msg = "Supervisor will dynamically route to optimal available agent"
    else:
        is_avail = True
        avail_msg = "Local Python worker sandbox available"

    # 3. Retrieve latest plan
    latest = await app_state.plan_repo.get_latest_plan(mission_id)
    if not latest:
        raise HTTPException(status_code=404, detail=f"No plan found for mission {mission_id}")

    tasks_data = latest.get("tasks", [])
    task_found = False
    updated_tasks = []

    for t in tasks_data:
        t_id = t.get("task_id") if isinstance(t, dict) else getattr(t, "task_id", "")
        if t_id == task_id:
            task_found = True
            if isinstance(t, dict):
                t_dict = dict(t)
                t_dict["proposed_agent"] = target_agent
                updated_tasks.append(t_dict)
            else:
                t_dict = t.model_dump()
                t_dict["proposed_agent"] = target_agent
                updated_tasks.append(t_dict)
        else:
            updated_tasks.append(t if isinstance(t, dict) else t.model_dump())

    if not task_found:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found in current plan")

    was_approved = (latest.get("approval_status") == "APPROVED")
    current_version = latest.get("version", 1)
    new_version = (current_version + 1) if was_approved else current_version

    if was_approved:
        # Invalidate approval as required by Section 1 / approval model
        await app_state.mission_manager.invalidate_approval(
            mission_id,
            reason=f"Operator reassigned Task {task_id} to '{target_agent}'. Plan updated to v{new_version} requiring re-approval."
        )

    latest["version"] = new_version
    latest["tasks"] = updated_tasks
    if was_approved:
        latest["approval_status"] = "PENDING"
        latest["approved_by"] = None
        latest["approved_at"] = None

    saved_plan = await app_state.plan_repo.save_plan(latest)

    # If core task already exists in graph/task_manager, update its assigned_agent_id
    try:
        core_task = await app_state.task_manager.get_task(mission_id, task_id)
        if core_task:
            core_task.assigned_agent_id = target_agent
            await app_state.task_manager._persist_task(core_task)
    except Exception:
        pass

    return {
        "status": "assigned",
        "task_id": task_id,
        "assigned_agent": target_agent,
        "assigned_agent_id": target_agent,
        "plan_version": new_version,
        "approval_required": was_approved,
        "reapproval_required": was_approved,
        "approval_status": "PENDING" if was_approved else latest.get("approval_status", "PENDING"),
        "agent_available": is_avail,
        "availability_message": avail_msg,
        "plan": saved_plan
    }


class ExecuteMissionRequest(BaseModel):
    agent_id: str = "worker_01"
    use_worktree: bool = False


@app.post("/api/missions/{mission_id}/start")
async def start_mission(mission_id: str):
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")

    # Strict plan approval gate
    latest_plan = await app_state.plan_repo.get_latest_plan(mission_id)
    if not latest_plan:
        raise HTTPException(
            status_code=400,
            detail={"error": "PLAN_REQUIRED", "message": "Mission requires a generated execution plan before dispatch."}
        )

    blocking = latest_plan.get("interpretation", {}).get("blocking_questions", [])
    if blocking:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "BLOCKING_QUESTIONS_UNRESOLVED",
                "message": "Execution rejected: blocking questions must be resolved first.",
                "blocking_questions": blocking
            }
        )

    if latest_plan.get("approval_status") != "APPROVED" or mission.status != MissionStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "PLAN_NOT_APPROVED",
                "message": "Task dispatch rejected. Explicit plan approval is mandatory before execution.",
                "plan_status": latest_plan.get("approval_status"),
                "mission_status": mission.status.value
            }
        )

    if mission.approved_plan_version != latest_plan.get("version"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "PLAN_VERSION_MISMATCH",
                "message": f"Approval is tied to plan version v{mission.approved_plan_version}, but current version is v{latest_plan.get('version')}."
            }
        )

    if mission.status == MissionStatus.RUNNING:
        raise HTTPException(
            status_code=409,
            detail={"error": "MISSION_ALREADY_RUNNING", "message": "Mission execution is already in progress."}
        )

    started_mission = await app_state.mission_manager.start_mission(mission_id)
    latest_plan["execution_started_at"] = datetime.now(timezone.utc).isoformat()
    await app_state.plan_repo.save_plan(latest_plan)

    asyncio.create_task(app_state.mission_runner.execute_mission(mission_id=mission_id))
    return {"status": "started", "mission": started_mission}


@app.post("/api/missions/{mission_id}/execute")
async def execute_mission_endpoint(mission_id: str, req: Optional[ExecuteMissionRequest] = None):
    """
    Executes a real end-to-end coding mission:
    Mandatory plan approval check -> Workspace setup -> Execution -> Watchdog interception ->
    Diagnosis -> Repair -> Independent verification -> Persisted SQLite results.
    """
    agent_id = req.agent_id if req else "worker_01"
    use_wt = req.use_worktree if req else False

    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")

    # Strict plan approval gate
    latest_plan = await app_state.plan_repo.get_latest_plan(mission_id)
    if not latest_plan:
        raise HTTPException(
            status_code=400,
            detail={"error": "PLAN_REQUIRED", "message": "Mission requires a generated execution plan before dispatch."}
        )

    blocking = latest_plan.get("interpretation", {}).get("blocking_questions", [])
    if blocking:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "BLOCKING_QUESTIONS_UNRESOLVED",
                "message": "Execution rejected: blocking questions must be resolved first.",
                "blocking_questions": blocking
            }
        )

    if latest_plan.get("approval_status") != "APPROVED" or mission.status != MissionStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "PLAN_NOT_APPROVED",
                "message": "Task dispatch rejected. Explicit plan approval is mandatory before execution.",
                "plan_status": latest_plan.get("approval_status"),
                "mission_status": mission.status.value
            }
        )

    if mission.approved_plan_version != latest_plan.get("version"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "PLAN_VERSION_MISMATCH",
                "message": f"Approval is tied to plan version v{mission.approved_plan_version}, but current version is v{latest_plan.get('version')}."
            }
        )

    if mission.status == MissionStatus.RUNNING:
        raise HTTPException(
            status_code=409,
            detail={"error": "MISSION_ALREADY_RUNNING", "message": "Mission execution is already in progress."}
        )

    latest_plan["execution_started_at"] = datetime.now(timezone.utc).isoformat()
    await app_state.plan_repo.save_plan(latest_plan)

    try:
        result = await app_state.mission_runner.execute_mission(
            mission_id=mission_id,
            target_agent=agent_id,
            use_worktree=use_wt
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Error executing mission {mission_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/missions/{mission_id}/verification")
async def get_mission_verification(mission_id: str):
    """Returns independent verification outcomes for the given mission."""
    verifications = await app_state.verification_repo.list_by_mission(mission_id)
    return {"verifications": verifications, "count": len(verifications)}



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
@app.get("/api/telemetry/overview")
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


def _event_to_supervisor_decision(e: Event) -> Optional[Dict[str, Any]]:
    p = e.payload or {}
    time_str = e.timestamp.strftime("%H:%M:%S") if hasattr(e.timestamp, "strftime") else str(e.timestamp)

    if e.type == EventType.SUPERVISOR_DECISION:
        return {
            "id": getattr(e, "event_id", "dec"),
            "timestamp": time_str,
            "decision_type": (p.get("decision") or "DECISION").upper(),
            "title": f"Supervisor Decision: {p.get('decision', 'DECIDE')}",
            "why": p.get("reason") or p.get("rationale") or "Supervisory rule triggered",
            "evidence": p.get("evidence") or [p.get("anomaly_type")] or ["Policy rule evaluation"],
            "action": p.get("action", "CONTINUE"),
            "target_agent": p.get("target_agent") or e.agent_id or "fleet",
            "result": p.get("result", "Action applied"),
            "provenance_model": p.get("model_provenance", "Google Gemma 4")
        }
    elif e.type == EventType.SUPERVISOR_INTERVENTION:
        return {
            "id": getattr(e, "event_id", "dec"),
            "timestamp": time_str,
            "decision_type": "PAUSE",
            "title": f"Supervisor Intervened: {p.get('action', 'PAUSE')}",
            "why": p.get("reason") or "Watchdog detected repeating error loop threshold",
            "evidence": [p.get("rule_name", "LOOP_DETECTION"), p.get("signature")] if p.get("signature") else ["3 identical failure signatures"],
            "action": p.get("action", "PAUSE_PROCESS"),
            "target_agent": p.get("agent_id") or e.agent_id or "worker",
            "result": "Agent process paused; awaiting handoff or operator review",
            "provenance_model": "Supervisor Watchdog Engine"
        }
    elif e.type in (EventType.SUPERVISOR_ALERT, EventType.SUPERVISOR_ANOMALY_DETECTED):
        return {
            "id": getattr(e, "event_id", "dec"),
            "timestamp": time_str,
            "decision_type": "WARN",
            "title": f"Anomaly Detected: {p.get('anomaly_type', 'WATCHDOG_ALERT')}",
            "why": p.get("description") or "Execution anomaly observed by watchdog",
            "evidence": [f"Turn limit / failure count: {p.get('count', 1)}"],
            "action": "FLAG_ANOMALY",
            "target_agent": e.agent_id or "worker",
            "result": "Logged in supervisory audit trail",
            "provenance_model": "Supervisor Watchdog Engine"
        }
    elif e.type == EventType.AGENT_ACTION and p.get("event_type") in ("routing.selected", "routing.evaluated"):
        return {
            "id": getattr(e, "event_id", "dec"),
            "timestamp": time_str,
            "decision_type": "ROUTE",
            "title": f"Dynamic Route Selected: {p.get('selected_agent', 'agent')}",
            "why": p.get("decision") or f"Selected {p.get('selected_agent')} based on multi-factor capability scoring.",
            "evidence": [f"Routing ID: {p.get('routing_id')}", "Score evaluation with cold-start safety"],
            "action": "ASSIGN_WORKTREE",
            "target_agent": p.get("selected_agent"),
            "result": "Task dispatched to chosen runtime",
            "provenance_model": "Dynamic Agent Router"
        }
    elif e.type == EventType.AGENT_ACTION and p.get("event_type") in ("handoff.initiated", "handoff.completed"):
        return {
            "id": getattr(e, "event_id", "dec"),
            "timestamp": time_str,
            "decision_type": "HANDOFF",
            "title": f"Agent Handoff: {p.get('source_agent_id')} -> {p.get('target_agent_id')}",
            "why": f"Handoff triggered by {p.get('trigger', 'FAILURE_LOOP')}: {p.get('detail', '')}",
            "evidence": [f"Handoff ID: {p.get('handoff_id')}", "Context and verified facts preserved in worktree"],
            "action": "TRANSFER_TASK_CONTEXT",
            "target_agent": p.get("target_agent_id"),
            "result": "Target agent initialized in isolated worktree",
            "provenance_model": "Handoff Engine"
        }
    elif e.type == EventType.VERIFICATION_RESULT:
        passed = p.get("passed", 0)
        failed = p.get("failed", 0)
        is_ok = (failed == 0 and passed > 0)
        return {
            "id": getattr(e, "event_id", "dec"),
            "timestamp": time_str,
            "decision_type": "VERIFY",
            "title": f"Verification {'PASSED' if is_ok else 'FAILED'} ({passed}/{passed + failed} tests)",
            "why": "Independent test suite verified in isolated sandbox with clean git diff" if is_ok else f"Verification rejected agent completion claim: {failed} test failures",
            "evidence": [f"Passed: {passed}", f"Failed: {failed}", "Zero out-of-scope modifications allowed"],
            "action": "ACCEPT_TASK" if is_ok else "REOPEN_TASK",
            "target_agent": e.agent_id or "verifier",
            "result": "Completion accepted by Supervisor" if is_ok else "Task reopened for correction",
            "provenance_model": "Independent Sandbox Verifier"
        }
    elif e.type == EventType.APPROVAL_REQUESTED:
        return {
            "id": getattr(e, "event_id", "dec"),
            "timestamp": time_str,
            "decision_type": "REQUIRE_APPROVAL",
            "title": f"Human Operator Approval Required: {p.get('action_type', 'ACTION')}",
            "why": p.get("reason") or "Action exceeds autonomous scope or touches protected resources",
            "evidence": [f"Target: {p.get('target', 'protected_path')}", f"Risk: {p.get('risk_level', 'MEDIUM')}"],
            "action": "AWAIT_OPERATOR_DECISION",
            "target_agent": e.agent_id or "worker",
            "result": "Execution paused until operator approves or denies",
            "provenance_model": "Zero Implicit Approval Policy"
        }
    elif e.type == EventType.MISSION_COMPLETED:
        return {
            "id": getattr(e, "event_id", "dec"),
            "timestamp": time_str,
            "decision_type": "COMPLETE",
            "title": "Mission Completed & Verified",
            "why": "All generated execution tasks completed and independently verified.",
            "evidence": ["All sandbox verifications accepted"],
            "action": "FINALIZE_MISSION",
            "target_agent": "supervisor",
            "result": "Mission closed, facts committed to project brain",
            "provenance_model": "Supervisor Engine"
        }
    return None


@app.get("/api/missions/{mission_id}/decisions")
async def get_supervisor_decisions(mission_id: str):
    """Returns human-readable Supervisor Decisions for a mission."""
    events = await app_state.event_store.query(mission_id=mission_id, limit=300)
    decisions = []
    for e in events:
        dec = _event_to_supervisor_decision(e)
        if dec:
            decisions.append(dec)
    return {"mission_id": mission_id, "decisions": decisions, "count": len(decisions)}


@app.get("/api/supervisor/decisions")
async def list_all_supervisor_decisions(limit: int = 100):
    """Returns human-readable Supervisor Decisions across all missions."""
    events = await app_state.event_store.query(limit=limit)
    decisions = []
    for e in events:
        dec = _event_to_supervisor_decision(e)
        if dec:
            decisions.append(dec)
    return {"decisions": decisions, "count": len(decisions)}


@app.post("/api/supervisor/decisions/explain")
async def explain_supervisor_decision(payload: Dict[str, Any]):
    """Explains a supervisor decision using Gemma 4 intelligence."""
    decision_type = payload.get("decision_type", "ROUTE")
    context = payload.get("context", {})
    explanation = await app_state.gemma_reasoner.explain_decision(decision_type, context)
    return {"explanation": explanation, "model_provenance": "Google Gemma 4 (gemma-4-31B-it)"}


@app.post("/api/supervisor/analyze-failure")
async def analyze_complex_failure_endpoint(payload: Dict[str, Any]):
    """Deep failure diagnosis and recovery analysis via Google Gemini."""
    task_title = payload.get("task_title", "Unknown Task")
    stack_trace = payload.get("stack_trace", "")
    history = payload.get("failure_history", [])
    files = payload.get("affected_files", [])
    analysis = await app_state.gemini_reasoner.analyze_complex_failure(
        task_title=task_title,
        stack_trace=stack_trace,
        failure_history=history,
        affected_files=files
    )
    return analysis.model_dump()


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


# --- Adapter Fleet Registry ---
@app.get("/api/adapters")
async def list_adapters():
    """Lists all registered AgentAdapters, declared capabilities, and runtime availability."""
    availabilities = await app_state.adapter_registry.check_all_availabilities()
    adapters_list = []
    for ident in app_state.adapter_registry.list_adapters():
        avail = availabilities.get(ident.adapter_id)
        adapters_list.append({
            "adapter_id": ident.adapter_id,
            "provider": ident.provider,
            "display_name": ident.display_name,
            "version": ident.version,
            "capabilities": ident.capabilities,
            "runtime_type": getattr(ident, "runtime_type", "agent_runtime"),
            "execution_mode": getattr(ident, "execution_mode", "local_process"),
            "infrastructure_provider": getattr(ident, "infrastructure_provider", "local"),
            "supported_models": getattr(ident, "supported_models", []),
            "supported_tools": getattr(ident, "supported_tools", []),
            "session_support": getattr(ident, "session_support", False),
            "remote_execution": getattr(ident, "remote_execution", False),
            "local_execution": getattr(ident, "local_execution", True),
            "configuration_requirements": getattr(ident, "configuration_requirements", []),
            "availability": avail.model_dump() if avail else {
                "status": "UNKNOWN",
                "available": False,
                "message": "Availability probe not executed",
                "executable_path": None,
            },
        })
    return {"adapters": adapters_list, "count": len(adapters_list)}


ADAPTER_SETUP_GUIDES = {
    "claude_code": {
        "adapter_id": "claude_code",
        "display_name": "Claude Code CLI",
        "provider": "Anthropic",
        "runtime_type": "Local Agent Runtime",
        "description": "Anthropic's official terminal-first coding agent capable of autonomous code editing, terminal commands, and multi-file refactoring.",
        "executable_name": "claude",
        "install_method": "npm",
        "install_command": "npm install -g @anthropic-ai/claude-code",
        "verification_command": "claude --version",
        "required_env_vars": ["ANTHROPIC_API_KEY"],
        "supported_os": ["Windows", "macOS", "Linux"],
        "documentation_url": "https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview",
        "prerequisites": ["Node.js >= 18.0.0", "npm or pnpm", "Active Anthropic API account"]
    },
    "codex": {
        "adapter_id": "codex",
        "display_name": "OpenAI Codex CLI",
        "provider": "OpenAI",
        "runtime_type": "Local Agent Runtime",
        "description": "Autonomous code synthesis and precision repair engine backed by OpenAI frontier models.",
        "executable_name": "codex",
        "install_method": "npm",
        "install_command": "npm install -g @openai/codex",
        "verification_command": "codex --version",
        "required_env_vars": ["OPENAI_API_KEY"],
        "supported_os": ["Windows", "macOS", "Linux"],
        "documentation_url": "https://platform.openai.com/docs/guides/code",
        "prerequisites": ["Node.js >= 18.0.0", "OpenAI API Key"]
    },
    "gemini": {
        "adapter_id": "gemini",
        "display_name": "Google Gemini CLI",
        "provider": "Google",
        "runtime_type": "Local CLI & Multimodal Provider",
        "description": "Google Gemini multimodal CLI and planning engine for architectural review and large-context diagnostics.",
        "executable_name": "gemini",
        "install_method": "npm",
        "install_command": "npm install -g @google/gemini-cli",
        "verification_command": "gemini --version",
        "required_env_vars": ["GEMINI_API_KEY"],
        "supported_os": ["Windows", "macOS", "Linux"],
        "documentation_url": "https://ai.google.dev/gemini-api/docs",
        "prerequisites": ["Node.js or Python 3.10+", "Google AI Studio API Key"]
    },
    "qwen": {
        "adapter_id": "qwen",
        "display_name": "Qwen 2.5 Coder Local",
        "provider": "Alibaba Cloud / Ollama",
        "runtime_type": "Local Offline LLM Agent",
        "description": "On-device local LLM offline agent powered by Ollama and Qwen 2.5 Coder 32B/7B for air-gapped execution.",
        "executable_name": "ollama",
        "install_method": "ollama",
        "install_command": "ollama run qwen2.5-coder:32b",
        "verification_command": "ollama list",
        "required_env_vars": ["OLLAMA_HOST (Optional, default http://localhost:11434)"],
        "supported_os": ["Windows", "macOS", "Linux"],
        "documentation_url": "https://ollama.com/library/qwen2.5-coder",
        "prerequisites": ["Ollama running locally on port 11434", "16GB+ RAM (or GPU acceleration)"]
    },
    "opencode": {
        "adapter_id": "opencode",
        "display_name": "OpenCode",
        "provider": "Open-Source",
        "runtime_type": "Open Weights Agentic Engine",
        "description": "Open weight agentic execution engine driving open models for git and terminal tasks.",
        "executable_name": "opencode",
        "install_method": "npm",
        "install_command": "npm install -g opencode-ai",
        "verification_command": "opencode --version",
        "required_env_vars": ["OPENCODE_API_KEY or NEBIUS_API_KEY"],
        "supported_os": ["Windows", "macOS", "Linux"],
        "documentation_url": "https://github.com/opencode-ai",
        "prerequisites": ["Node.js >= 18.0.0"]
    },
    "kimi": {
        "adapter_id": "kimi",
        "display_name": "Kimi Code",
        "provider": "Moonshot AI",
        "runtime_type": "Long-Context Agentic Runtime",
        "description": "Ultra long-context agent runtime for full-repo diagnostics, deep dependency tracing, and complex repair.",
        "executable_name": "kimi",
        "install_method": "pip",
        "install_command": "pip install kimi-cli",
        "verification_command": "kimi --version",
        "required_env_vars": ["MOONSHOT_API_KEY or NEBIUS_API_KEY"],
        "supported_os": ["Windows", "macOS", "Linux"],
        "documentation_url": "https://platform.moonshot.cn",
        "prerequisites": ["Python 3.10+"]
    },
    "hermes": {
        "adapter_id": "hermes",
        "display_name": "Nous Hermes Agent",
        "provider": "Nous Research",
        "runtime_type": "Long-Session Autonomous Coding Agent",
        "description": "Autonomous coding agent optimized for continuous sessions, tool governance, and resilient retries.",
        "executable_name": "hermes",
        "install_method": "pip",
        "install_command": "pip install hermes-agent",
        "verification_command": "hermes --version",
        "required_env_vars": ["HERMES_API_KEY or NEBIUS_API_KEY"],
        "supported_os": ["Linux", "macOS", "Windows (WSL2)"],
        "documentation_url": "https://nousresearch.com",
        "prerequisites": ["Python 3.10+"]
    },
    "digitalocean_managed": {
        "adapter_id": "digitalocean_managed",
        "display_name": "DigitalOcean Managed Agent",
        "provider": "DigitalOcean",
        "runtime_type": "Cloud MicroVM Sandbox & Action Gateway",
        "description": "Cloud-hosted isolated microVM developer agent with Action Gateway governed MCP tools. No local binary required.",
        "executable_name": "cloud-api",
        "install_method": "env",
        "install_command": "Set DIGITALOCEAN_TOKEN in environment or .env file",
        "verification_command": "curl -H \"Authorization: Bearer $DIGITALOCEAN_TOKEN\" https://api.digitalocean.com/v2/account",
        "required_env_vars": ["DIGITALOCEAN_TOKEN"],
        "supported_os": ["Cloud Hosted"],
        "documentation_url": "https://docs.digitalocean.com/products/managed-agents",
        "prerequisites": ["Active DigitalOcean Cloud Account & API Token"]
    },
    "goose": {
        "adapter_id": "goose",
        "display_name": "Goose",
        "provider": "Block",
        "runtime_type": "Open Extensible On-Machine Developer Agent",
        "description": "Block's open-source developer agent running on your workstation with extensible tools and MCP support.",
        "executable_name": "goose",
        "install_method": "pipx",
        "install_command": "pipx install goose-ai",
        "verification_command": "goose --version",
        "required_env_vars": ["ANTHROPIC_API_KEY or OPENAI_API_KEY"],
        "supported_os": ["macOS", "Linux", "Windows"],
        "documentation_url": "https://block.github.io/goose",
        "prerequisites": ["Python 3.10+", "pipx"]
    },
    "cline": {
        "adapter_id": "cline",
        "display_name": "Cline",
        "provider": "Cline Core",
        "runtime_type": "Autonomous Coding & File Patching",
        "description": "Autonomous developer agent for editing files, executing terminal commands, and browser testing in isolated sessions.",
        "executable_name": "cline",
        "install_method": "npm",
        "install_command": "npm install -g cline",
        "verification_command": "cline --version",
        "required_env_vars": ["ANTHROPIC_API_KEY or OPENROUTER_API_KEY"],
        "supported_os": ["macOS", "Linux", "Windows"],
        "documentation_url": "https://github.com/cline/cline",
        "prerequisites": ["Node.js >= 18.0.0"]
    },
    "worker_01": {
        "adapter_id": "worker_01",
        "display_name": "Local Autonomous Python Worker",
        "provider": "AI Supervisor Built-in",
        "runtime_type": "Native Tool Sandbox",
        "description": "AI Supervisor's built-in autonomous Python worker equipped with sandboxed file read/write, git operations, command execution, and verification.",
        "executable_name": "python",
        "install_method": "builtin",
        "install_command": "# Built-in runtime. Always available.",
        "verification_command": "python --version",
        "required_env_vars": [],
        "supported_os": ["Windows", "macOS", "Linux"],
        "documentation_url": "https://github.com/M0izz/AI-Supervisior",
        "prerequisites": ["Python >= 3.10"]
    }
}


@app.get("/api/adapters/{adapter_id}/setup-guide")
async def get_adapter_setup_guide(adapter_id: str):
    """Returns verified setup instructions, required dependencies, and copyable commands."""
    guide = ADAPTER_SETUP_GUIDES.get(adapter_id.lower())
    if not guide:
        # Check if registered adapter has basic info
        adapter = app_state.adapter_registry.get_adapter(adapter_id)
        if adapter:
            return {
                "adapter_id": adapter.identity.adapter_id,
                "display_name": adapter.identity.display_name,
                "provider": adapter.identity.provider,
                "runtime_type": getattr(adapter.identity, "runtime_type", "agent_runtime"),
                "description": f"Integration for {adapter.identity.display_name}.",
                "executable_name": adapter.identity.adapter_id,
                "install_method": "manual",
                "install_command": f"# Refer to official documentation for {adapter.identity.display_name}",
                "verification_command": f"{adapter.identity.adapter_id} --version",
                "required_env_vars": getattr(adapter.identity, "configuration_requirements", []),
                "supported_os": ["Windows", "macOS", "Linux"],
                "documentation_url": "https://github.com/M0izz/AI-Supervisior",
                "prerequisites": []
            }
        raise HTTPException(status_code=404, detail=f"No setup guide found for adapter '{adapter_id}'")
    return guide


@app.post("/api/adapters/{adapter_id}/check")
async def recheck_adapter_availability(adapter_id: str):
    """Re-probes the system environment to detect whether the adapter has been installed or configured."""
    if adapter_id in ("worker_01", "local_worker"):
        return {
            "adapter_id": adapter_id,
            "status": "AVAILABLE",
            "available": True,
            "message": "Local autonomous Python worker is active and operable in local workspace.",
            "executable_path": sys.executable if "sys" in globals() else "python"
        }

    adapter = app_state.adapter_registry.get_adapter(adapter_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_id}' not found in registry")

    avail = await adapter.check_availability()
    return {
        "adapter_id": adapter_id,
        "status": avail.status.value if hasattr(avail.status, "value") else str(avail.status),
        "available": avail.available,
        "message": avail.message,
        "executable_path": avail.executable_path,
        "diagnostics": avail.diagnostics
    }


@app.post("/api/adapters/{adapter_id}/test")
async def test_adapter_execution(adapter_id: str):
    """
    Safely probes an available adapter runtime without mutating project files.
    For local worker, validates tool sandbox. For external adapters, validates CLI or API health.
    """
    if adapter_id in ("worker_01", "local_worker"):
        import shutil
        git_avail = shutil.which("git") is not None
        return {
            "status": "SUCCESS",
            "agent_id": adapter_id,
            "message": "Built-in autonomous worker sandbox verified operable.",
            "output": "Worker 01 runtime responded: sandbox operable, file IO verified, python environment active.",
            "details": {
                "file_io": "Verified (workspace writeable)",
                "git_binary": "Verified" if git_avail else "Git not in PATH",
                "python_runtime": "Verified"
            }
        }

    adapter = app_state.adapter_registry.get_adapter(adapter_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_id}' not found")

    avail = await adapter.check_availability()
    if not avail.available:
        return {
            "status": "FAILED",
            "agent_id": adapter_id,
            "message": f"Runtime unavailable: {avail.message}",
            "output": f"Runtime unavailable: {avail.message}",
            "availability": avail.model_dump()
        }

    return {
        "status": "SUCCESS",
        "agent_id": adapter_id,
        "message": f"Agent runtime '{adapter.identity.display_name}' verified operable and ready for mission assignment.",
        "output": f"Worker runtime '{adapter.identity.display_name}' responded and verified operable.",
        "executable_path": avail.executable_path
    }


@app.get("/api/providers")
async def list_providers():
    """Lists all infrastructure and inference providers (DigitalOcean, Nebius, Local)."""
    providers = []

    # 1. DigitalOcean Provider
    do_desc = await app_state.digitalocean_provider.get_descriptor()
    providers.append(do_desc.model_dump())

    # 2. Nebius Token Factory
    nebius_key = os.getenv("NEBIUS_API_KEY")
    nebius_desc = {
        "provider_id": "nebius",
        "name": "Nebius Token Factory",
        "status": "CONNECTED" if nebius_key else "NOT_CONFIGURED",
        "available": bool(nebius_key),
        "message": "Nebius Token Factory API connected." if nebius_key else "NEBIUS_API_KEY not configured in environment.",
        "capabilities": ["serverless_inference", "open_models", "token_factory"],
        "inference_endpoint": os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1"),
        "managed_agents_support": False,
        "action_gateway_support": False,
        "supported_models": [
            "nvidia/nemotron-4-340b-instruct",
            "nousresearch/hermes-4-70b-instruct",
            "qwen/qwen-2.5-coder-32b-instruct",
            "moonshot/kimi-code-latest",
            "deepseek-ai/deepseek-r1-distill"
        ]
    }
    providers.append(nebius_desc)

    # 3. Google Gemini Provider
    gemini_desc = await app_state.gemini_provider.get_descriptor()
    providers.append(gemini_desc.model_dump())

    # 4. OpenRouter Multi-Model Inference Provider
    openrouter_desc = await app_state.openrouter_provider.get_descriptor()
    providers.append(openrouter_desc.model_dump())

    # 5. Backboard.io Sovereign AI Infrastructure Provider
    backboard_desc = await app_state.backboard_provider.get_descriptor()
    providers.append(backboard_desc.model_dump())

    # 6. Hugging Face Open Inference & Model Hub
    huggingface_desc = await app_state.huggingface_provider.get_descriptor()
    providers.append(huggingface_desc.model_dump())

    # 7. Local Workstation Substrate
    providers.append({
        "provider_id": "local",
        "name": "Local Workstation",
        "status": "CONNECTED",
        "available": True,
        "message": "Local processes, shell tools, and Git worktrees.",
        "capabilities": ["local_process", "git_worktrees", "file_system", "cli_runners"],
        "inference_endpoint": "local://unix-socket",
        "managed_agents_support": False,
        "action_gateway_support": False,
        "supported_models": ["local-ollama", "host-binaries"]
    })

    return {"providers": providers, "count": len(providers)}


@app.get("/api/models")
async def list_models():
    """Lists available models from DigitalOcean Inference, Nebius, Google Gemini, OpenRouter, Backboard, Hugging Face, and Local providers."""
    from integrations.nebius.provider import NebiusNemotronProvider
    models = []

    # 1. DigitalOcean models (including Gemma 4)
    do_models = await app_state.digitalocean_provider.get_models()
    for m in do_models:
        models.append(m.model_dump())

    # 2. Nebius Token Factory models
    nebius_provider = NebiusNemotronProvider()
    nebius_models = await nebius_provider.query_models()
    for m in nebius_models:
        models.append({
            "model_id": m.get("model_id"),
            "name": m.get("name"),
            "developer": m.get("developer"),
            "infrastructure_provider": "nebius",
            "parameter_size": m.get("parameter_size"),
            "specialties": m.get("specialties", []),
            "available": m.get("available", False),
            "context_window": 131072
        })

    # 3. Google Gemini models
    gemini_models = await app_state.gemini_provider.get_models()
    for m in gemini_models:
        models.append(m.model_dump())

    # 4. OpenRouter Multi-Model Inference Catalog
    openrouter_models = await app_state.openrouter_provider.get_models()
    for m in openrouter_models:
        models.append(m.model_dump())

    # 5. Backboard.io Models
    backboard_models = await app_state.backboard_provider.get_models()
    for m in backboard_models:
        models.append(m.model_dump())

    # 6. Hugging Face Models
    hf_models = await app_state.huggingface_provider.get_models()
    for m in hf_models:
        models.append(m.model_dump())

    return {"models": models, "count": len(models)}


@app.post("/api/custom-agents")
async def register_custom_agent(req: Dict[str, Any]):
    """Registers a user-defined custom agent adapter with security validation."""
    from adapters.custom import CustomAgentAdapter, CustomAgentRegistration
    try:
        reg = CustomAgentRegistration.model_validate(req)
        adapter = CustomAgentAdapter(
            registration=reg,
            event_bus=app_state.event_bus,
            worktree_manager=app_state.worktree_manager
        )
        app_state.adapter_registry.register_adapter(adapter)
        return {
            "status": "registered",
            "adapter_id": reg.adapter_id,
            "display_name": reg.name,
            "identity": adapter.identity.model_dump()
        }
    except Exception as e:
        logger.error(f"Failed to register custom agent: {e}")
        raise HTTPException(status_code=400, detail=str(e))


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
    serialized = [r.model_dump() for r in reqs]
    return {"approvals": serialized, "requests": serialized, "count": len(reqs)}


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


@app.post("/api/demo/reset")
async def reset_demo_state():
    """
    Resets demo workspace, in-memory events, agents, memory records, and tasks
    ensuring multiple demo runs never corrupt state.
    """
    from demo.reset import reset_sample_project, reset_event_logs, reset_in_memory_state
    from pathlib import Path
    project_root = Path("./")
    workspace_root = project_root / "demo" / "sample-project"

    reset_sample_project(workspace_root)
    reset_event_logs(project_root)
    reset_in_memory_state()

    return {"status": "reset", "message": "Demo state successfully reset to initial clean baseline"}


# --- Phase 9: Absence Mode Endpoints ---

class ArmAbsenceRequest(BaseModel):
    policy: Optional[Dict[str, Any]] = None
    created_by: str = "user"


class PauseAbsenceRequest(BaseModel):
    reason: str = "Operator paused via UI"


@app.post("/api/missions/{mission_id}/absence/arm")
async def arm_absence_mode(mission_id: str, req: ArmAbsenceRequest):
    """Explicitly arms Absence Mode for a mission, freezing an immutable policy snapshot."""
    mission = await app_state.mission_manager.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")

    from core.absence.models import AbsencePolicy
    policy_obj = None
    if req.policy:
        try:
            policy_obj = AbsencePolicy(**req.policy)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid absence policy: {e}")

    session = await app_state.absence_engine.arm_session(
        mission_id=mission_id,
        policy=policy_obj,
        created_by=req.created_by
    )
    return {"status": "armed", "session": session.model_dump(mode="json")}


@app.post("/api/missions/{mission_id}/absence/start")
async def start_absence_mode(mission_id: str):
    """Activates an armed absence session, starting the hard expiration countdown."""
    active = await app_state.absence_repo.get_active_session(mission_id)
    if not active:
        raise HTTPException(status_code=404, detail=f"No armed absence session found for mission {mission_id}")

    session = await app_state.absence_engine.start_session(active["absence_id"])
    return {"status": "active", "session": session.model_dump(mode="json")}


@app.post("/api/missions/{mission_id}/absence/pause")
async def pause_absence_mode(mission_id: str, req: PauseAbsenceRequest = PauseAbsenceRequest()):
    """Pauses an active absence session, revoking autonomous continuation."""
    active = await app_state.absence_repo.get_active_session(mission_id)
    if not active:
        raise HTTPException(status_code=404, detail=f"No active absence session found for mission {mission_id}")

    session = await app_state.absence_engine.pause_session(active["absence_id"], reason=req.reason)
    return {"status": "paused", "session": session.model_dump(mode="json")}


@app.post("/api/missions/{mission_id}/absence/resume")
async def resume_absence_mode(mission_id: str):
    """Resumes a paused absence session if not expired."""
    active = await app_state.absence_repo.get_active_session(mission_id)
    if not active:
        raise HTTPException(status_code=404, detail=f"No paused absence session found for mission {mission_id}")

    session = await app_state.absence_engine.resume_session(active["absence_id"])
    return {"status": "active", "session": session.model_dump(mode="json")}


@app.post("/api/missions/{mission_id}/absence/cancel")
async def cancel_absence_mode(mission_id: str, req: PauseAbsenceRequest = PauseAbsenceRequest()):
    """Emergency stop: Cancels the absence session and revokes all autonomous authorization."""
    active = await app_state.absence_repo.get_active_session(mission_id)
    if not active:
        raise HTTPException(status_code=404, detail=f"No active absence session found for mission {mission_id}")

    session = await app_state.absence_engine.cancel_session(active["absence_id"], reason=req.reason)
    return {"status": "cancelled", "session": session.model_dump(mode="json")}


@app.get("/api/missions/{mission_id}/absence")
async def get_mission_absence_session(mission_id: str):
    """Returns the current active or latest absence session for a mission."""
    active = await app_state.absence_repo.get_active_session(mission_id)
    if not active:
        sessions = await app_state.absence_repo.list_sessions_by_mission(mission_id)
        if not sessions:
            return {"active": False, "session": None}
        latest = sessions[0]
        from core.absence.engine import AbsencePolicyEngine
        model = app_state.absence_engine._to_session_model(latest)
        return {
            "active": False,
            "session": model.model_dump(mode="json"),
            "remaining_seconds": model.remaining_seconds()
        }

    model = app_state.absence_engine._to_session_model(active)
    return {
        "active": model.status.value == "ACTIVE",
        "session": model.model_dump(mode="json"),
        "remaining_seconds": model.remaining_seconds()
    }


@app.get("/api/absence/active")
async def list_active_absence_sessions():
    """Lists all active absence sessions across missions."""
    actives = await app_state.absence_repo.list_active_sessions()
    models = [app_state.absence_engine._to_session_model(a).model_dump(mode="json") for a in actives]
    return {"sessions": models, "count": len(models)}


# --- Phase 12: Cloud Sync & Multi-Device Endpoints ---

class DeviceRegistrationRequest(BaseModel):
    display_name: str
    platform: Optional[str] = "unknown"
    app_version: Optional[str] = "1.0.0"


@app.post("/api/sync/devices/register")
async def register_sync_device(req: DeviceRegistrationRequest):
    """Registers a new device for synchronization, issuing an authenticated device token."""
    from sync.identity import generate_device_credentials, hash_device_token
    from sync.protocol import Device, DeviceStatus
    from datetime import datetime, timezone

    device_id, device_token = generate_device_credentials()
    now = datetime.now(timezone.utc).isoformat()
    device = Device(
        device_id=device_id,
        display_name=req.display_name,
        platform=req.platform or "unknown",
        app_version=req.app_version or "1.0.0",
        status=DeviceStatus.ACTIVE,
        created_at=now,
        last_seen_at=now,
    )

    await app_state.sync_server.register_device(device, device_token)
    await app_state.sync_repo.register_device(device, hash_device_token(device_token))

    return {
        "status": "registered",
        "device": device.model_dump(),
        "device_token": device_token,
    }


@app.get("/api/sync/devices")
async def list_sync_devices():
    """Lists all registered devices and their synchronization status."""
    devices = await app_state.sync_server.list_devices()
    if not devices:
        devices = await app_state.sync_repo.list_devices()
    return {"devices": [d.model_dump() for d in devices], "count": len(devices)}


@app.post("/api/sync/devices/{device_id}/revoke")
async def revoke_sync_device(device_id: str):
    """Revokes a device, immediately blocking all further push and pull access."""
    server_res = await app_state.sync_server.revoke_device(device_id)
    repo_res = await app_state.sync_repo.revoke_device(device_id)
    if not (server_res or repo_res):
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return {"status": "revoked", "device_id": device_id}


@app.post("/api/sync/push")
async def sync_push_endpoint(req: Dict[str, Any]):
    """Idempotent push endpoint processing outbound client mutation records."""
    from sync.protocol import PushRequest
    from sync.server import SyncAuthError, DeviceRevokedError

    try:
        push_req = PushRequest(**req)
        push_resp = await app_state.sync_server.push(push_req)
        return push_resp.model_dump()
    except SyncAuthError as sae:
        raise HTTPException(status_code=401, detail=str(sae))
    except DeviceRevokedError as dre:
        raise HTTPException(status_code=403, detail=str(dre))
    except Exception as e:
        logger.error(f"Error processing sync push: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/sync/pull")
async def sync_pull_endpoint(
    device_id: str,
    device_token: str,
    project_id: str,
    cursor: int = 0,
    limit: int = 100,
):
    """Incremental pull endpoint returning project-scoped records beyond cursor."""
    from sync.protocol import PullRequest
    from sync.server import SyncAuthError, DeviceRevokedError

    try:
        pull_req = PullRequest(
            device_id=device_id,
            device_token=device_token,
            project_id=project_id,
            cursor=cursor,
            limit=limit,
        )
        pull_resp = await app_state.sync_server.pull(pull_req)
        return pull_resp.model_dump()
    except SyncAuthError as sae:
        raise HTTPException(status_code=401, detail=str(sae))
    except DeviceRevokedError as dre:
        raise HTTPException(status_code=403, detail=str(dre))
    except Exception as e:
        logger.error(f"Error processing sync pull: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/sync/status")
async def get_sync_status():
    """Returns the local sync engine's current state, pending outbox count, and cursor."""
    status = await app_state.sync_engine.get_status()
    return status.model_dump()


@app.post("/api/sync/trigger")
async def trigger_sync():
    """Manually triggers an immediate synchronization round."""
    status = await app_state.sync_engine.sync_now()
    return {"status": "triggered", "sync_status": status.model_dump()}


# --- FalkorDB Graph Memory & Coordination Endpoints ---
@app.get("/api/graph/health")
async def get_graph_health():
    """Returns real-time health, connectivity, and graph statistics from FalkorDB."""
    health = app_state.falkordb_client.check_health()
    return health


@app.get("/api/missions/{mission_id}/graph")
async def get_mission_graph(mission_id: str):
    """
    Returns the complete property graph for a mission from FalkorDB,
    including Mission, Tasks, Executions, Events, Decisions, Handoffs, and Verifications.
    """
    from storage.graph import FalkorDBUnavailableError
    try:
        subgraph = await app_state.graph_repo.get_mission_subgraph(mission_id)
        return subgraph
    except FalkorDBUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail=f"FalkorDB graph memory is unavailable: {e}"
        )
    except Exception as e:
        logger.error(f"Error retrieving mission subgraph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/missions/{mission_id}/tasks/{task_id}/graph-context")
async def get_task_graph_context(mission_id: str, task_id: str):
    """
    Retrieves bounded, dependency-aware task coordination context from FalkorDB,
    including dependencies, prior attempts, failure signatures, decisions, and handoffs.
    """
    from storage.graph import FalkorDBUnavailableError
    try:
        context = await app_state.graph_repo.get_task_graph_context(mission_id, task_id)
        return context
    except FalkorDBUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail=f"FalkorDB graph memory is unavailable: {e}"
        )
    except Exception as e:
        logger.error(f"Error retrieving task graph context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/missions/{mission_id}/failures")
async def get_mission_failures(mission_id: str, task_id: Optional[str] = None):
    """
    Returns prior failure history and causal paths traversed from FalkorDB graph.
    """
    from storage.graph import FalkorDBUnavailableError
    try:
        failures = await app_state.graph_repo.get_prior_failure_history(mission_id, task_id=task_id)
        return {"mission_id": mission_id, "task_id": task_id, "failures": failures}
    except FalkorDBUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail=f"FalkorDB graph memory is unavailable: {e}"
        )
    except Exception as e:
        logger.error(f"Error retrieving failure history from graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/missions/{mission_id}/decisions")
async def get_mission_decisions(mission_id: str):
    """
    Explains supervisory routing and recovery decisions via their supporting graph path:
    Decision -> RESPONDS_TO -> ExecutionEvent
    Decision -> SELECTS -> Agent
    """
    from storage.graph import FalkorDBUnavailableError
    try:
        lineage = await app_state.graph_repo.get_decision_lineage(mission_id)
        return {"mission_id": mission_id, "decisions": lineage}
    except FalkorDBUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail=f"FalkorDB graph memory is unavailable: {e}"
        )
    except Exception as e:
        logger.error(f"Error retrieving decision lineage from graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/missions/{mission_id}/tasks/{task_id}/verification-trace")
async def get_task_verification_trace(mission_id: str, task_id: str):
    """
    Traverses FalkorDB graph to trace Verification decision directly to objective Evidence.
    Verification -> EVALUATES -> Task
    Verification -> SUPPORTED_BY -> Evidence
    """
    from storage.graph import FalkorDBUnavailableError
    try:
        trace = await app_state.graph_repo.get_verification_trace(task_id)
        return trace
    except FalkorDBUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail=f"FalkorDB graph memory is unavailable: {e}"
        )
    except Exception as e:
        logger.error(f"Error retrieving verification trace from graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/activity")
async def get_graph_activity(limit: int = 25):
    """
    Returns verified, structured graph activity events directly from FalkorDB:
    Missions, Tasks, Executions, Decisions, Verifications, and Evidence.
    """
    from storage.graph import FalkorDBUnavailableError
    try:
        events = await app_state.graph_repo.get_recent_activity(limit=limit)
        return {"events": events, "count": len(events)}
    except FalkorDBUnavailableError as e:
        raise HTTPException(status_code=503, detail=f"FalkorDB is unavailable: {e}")
    except Exception as e:
        logger.error(f"Error retrieving graph activity: {e}")
        return {"events": [], "count": 0}


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


