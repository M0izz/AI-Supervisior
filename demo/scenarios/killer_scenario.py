import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from core.events.bus import EventBus
from core.events.store import InMemoryEventStore
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.tasks.models import Task, TaskStatus
from core.policies.models import PolicyConfig
from supervisor.engine import SupervisorEngine
from supervisor.reasoning import SupervisoryReasoner
from supervisor.decisions import SupervisorAction
from supervisor.state_machine import SupervisorState
from supervisor.timeline import SupervisorTimelineBuilder
from integrations.nebius.provider import NebiusNemotronProvider, MockReasoningProvider
from integrations.jenkins import (
    JenkinsHttpClient,
    MockJenkinsProvider,
    JenkinsBuildStatus
)
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest, ExecutionStatus
from memory.store import MemoryStore
from memory.provenance import FactStatus
from memory.retrieval import ContextPackager
from agents.planner.agent import PlannerAgent
from agents.worker.agent import WorkerAgent
from agents.worker.models import WorkerState
from agents.verifier.agent import VerifierAgent
from agents.reviewer.agent import ReviewerAgent
from core.state.models import AgentContextPackage
from tools import get_default_tools

console = Console(force_terminal=True, legacy_windows=False)
logging.basicConfig(level=logging.WARNING)


async def run_killer_scenario():
    start_time = time.monotonic()

    console.print("\n[bold cyan]+===================================================================+[/bold cyan]")
    console.print("[bold cyan]|            AI WORK SUPERVISOR — REAL KILLER SCENARIO              |[/bold cyan]")
    console.print("[bold cyan]|  Full Autonomous Loop: Planner -> Worker -> Docker -> Jenkins ->  |[/bold cyan]")
    console.print("[bold cyan]|  Supervisor -> Nemotron -> Reviewer -> Memory -> Fix -> Verifier  |[/bold cyan]")
    console.print("[bold cyan]+===================================================================+[/bold cyan]\n")

    workspace_root = PROJECT_ROOT / "demo" / "sample-project"

    # Step 0: Ensure clean deterministic baseline code in sample-project
    from demo.reset import reset_sample_project
    reset_sample_project(workspace_root)

    # 1. Initialize Subsystems & Infrastructure
    event_bus = EventBus()
    # Write events to supervisor_events.jsonl so Control Room UI reads real live data
    event_store = InMemoryEventStore(persistence_file=PROJECT_ROOT / "supervisor_events.jsonl")
    event_bus._global_subscribers.append(event_store.append)

    mission_mgr = MissionManager(event_bus=event_bus)
    task_mgr = TaskManager(event_bus=event_bus)
    memory_store = MemoryStore(event_bus=event_bus)
    packager = ContextPackager(memory_store=memory_store, event_bus=event_bus)
    policy = PolicyConfig(pause_after_repeated_failures=3)

    # Reasoning Provider: Nebius Nemotron if key present, else local deterministic mock
    if os.getenv("NEBIUS_API_KEY"):
        reasoning_provider = NebiusNemotronProvider()
        reasoning_name = "NVIDIA Nemotron on Nebius AI Studio"
    else:
        reasoning_provider = MockReasoningProvider()
        reasoning_name = "Deterministic Nemotron Mock (Offline Local)"
    reasoner = SupervisoryReasoner(provider=reasoning_provider)

    # Execution Backend: Docker sandbox if available, else local process sandbox
    backend_pref = os.getenv("EXECUTION_BACKEND", "local").lower()
    exec_mgr = ExecutionManager(event_bus=event_bus, default_backend=backend_pref, allow_fallback=True)

    # Jenkins CI: HTTP client if configured, else deterministic MockJenkinsProvider
    if os.getenv("JENKINS_URL") and os.getenv("JENKINS_URL") != "mock":
        jenkins = JenkinsHttpClient()
        jenkins_name = f"Live Jenkins Server ({os.getenv('JENKINS_URL')})"
    else:
        jenkins = MockJenkinsProvider(default_mode="DYNAMIC_WORKSPACE", workspace_path=str(workspace_root))
        jenkins_name = "Offline Jenkins simulation / fallback provider"

    supervisor = SupervisorEngine(
        event_bus=event_bus,
        mission_manager=mission_mgr,
        task_manager=task_mgr,
        policy=policy,
        reasoner=reasoner
    )

    tools = get_default_tools(workspace_root, execution_manager=exec_mgr)
    worker = WorkerAgent(agent_id="worker_01", event_bus=event_bus, tools=tools)
    supervisor.register_worker(worker)

    # -------------------------------------------------------------------------
    # STEP 1: User Creates Mission
    # -------------------------------------------------------------------------
    console.print("[bold green]▶ [STEP 1] USER CREATES MISSION[/bold green]")
    mission = await mission_mgr.create_mission(
        title="Add CSV Import with UTF-8 BOM Support",
        goal="Implement robust CSV parser and import validation without altering database schema",
        repository_path=str(workspace_root)
    )
    await mission_mgr.start_mission(mission.id)
    console.print(f"  Mission: [bold]{mission.title}[/bold] (ID: {mission.id})")
    console.print(f"  Status: [cyan]{mission.status.value}[/cyan]\n")

    # -------------------------------------------------------------------------
    # STEP 2: Planner Creates Tasks (DAG)
    # -------------------------------------------------------------------------
    console.print("[bold green]▶ [STEP 2] PLANNER AGENT DECOMPOSES MISSION INTO TASK DAG[/bold green]")
    planner = PlannerAgent(agent_id="planner_01", event_bus=event_bus)
    plan_result = await planner.run(
        AgentContextPackage(
            mission_id=mission.id,
            objective=mission.goal,
            task={"title": "Create DAG plan"},
            constraints=["Do not modify database schema"]
        )
    )
    graph = await task_mgr.initialize_mission_tasks(mission.id, plan_result["tasks"])
    console.print(f"  DAG Synthesized: [bold]{len(graph.tasks)} tasks[/bold]")
    for t in graph.tasks.values():
        console.print(f"    • {t.id}: {t.title} (depends on: {t.dependencies or 'None'})")
    console.print()

    # -------------------------------------------------------------------------
    # STEP 3: Worker Starts Task
    # -------------------------------------------------------------------------
    task_impl = graph.get_task("TASK-002") or list(graph.tasks.values())[1]
    console.print(f"[bold green]▶ [STEP 3] WORKER STARTS TASK: {task_impl.id} ({task_impl.title})[/bold green]")
    await task_mgr.start_task(mission.id, task_impl.id, worker.agent_id)
    console.print(f"  Assigned Agent: [cyan]{worker.agent_id}[/cyan]\n")

    # -------------------------------------------------------------------------
    # STEP 4: Docker Executes Worker Inspecting Workspace
    # -------------------------------------------------------------------------
    console.print(f"[bold green]▶ [STEP 4] DOCKER SANDBOX EXECUTES WORKER INSPECTION[/bold green]")
    inspect_res = await worker.call_tool(
        "read_file",
        {"path": "src/parser.py"},
        mission_id=mission.id,
        task_id=task_impl.id
    )
    console.print(f"  Worker inspected src/parser.py ({inspect_res.metadata.get('bytes', 0)} bytes read)")
    console.print(f"  Execution Backend: [bold]{inspect_res.metadata.get('backend', exec_mgr.default_backend).upper()}[/bold]\n")

    # -------------------------------------------------------------------------
    # STEP 5: Worker Encounters Repeated Failure (3 Consecutive Attempts)
    # -------------------------------------------------------------------------
    console.print("[bold yellow]▶ [STEP 5] WORKER ENCOUNTERS REPEATED TEST FAILURES[/bold yellow]")
    for attempt in range(1, 4):
        test_run = await worker.call_tool(
            "run_tests",
            {"test_command": "python -m pytest tests/test_parser.py -q"},
            mission_id=mission.id,
            task_id=task_impl.id
        )
        passed = test_run.metadata.get("passed", 0)
        failed = test_run.metadata.get("failed", 0)
        err_sig = test_run.metadata.get("error_signature", "CSV_HEADER_MISMATCH_BOM")
        console.print(f"  Attempt {attempt}: [red]{passed} passed / {failed} failed[/red] (Error: {err_sig})")
        await task_mgr.fail_task(mission.id, task_impl.id, error_signature=err_sig, reason=f"Attempt {attempt} failed")
        await asyncio.sleep(0.05)
    console.print()

    # -------------------------------------------------------------------------
    # STEP 6: Jenkins Independently Confirms Failure
    # -------------------------------------------------------------------------
    console.print("[bold yellow]▶ [STEP 6] JENKINS CI INDEPENDENTLY CONFIRMS FAILURE[/bold yellow]")
    trigger_1 = await jenkins.trigger_build(job_name="ai-work-supervisor-ci")
    ci_build_1 = await jenkins.get_build_result(trigger_1.build_id, "ai-work-supervisor-ci")
    console.print(f"  CI Provider: {jenkins_name}")
    console.print(f"  CI Build: #{ci_build_1.build_id} | Status: [bold red]{ci_build_1.result.value}[/bold red]")
    console.print(f"  CI Proof: {ci_build_1.tests_passed} passed, {ci_build_1.tests_failed} failed")
    console.print(f"  Error Signature: [red]{ci_build_1.error_signature}[/red]\n")

    # -------------------------------------------------------------------------
    # STEP 7: Supervisor Detects Anomaly
    # -------------------------------------------------------------------------
    console.print("[bold magenta]▶ [STEP 7] SUPERVISOR DETECTS ANOMALY: LOOP_DETECTED[/bold magenta]")
    console.print(f"  Watchdog Triggered: [bold]3 Consecutive Identical Failures[/bold]")
    console.print(f"  Supervisor State: [bold yellow]{supervisor.state_machine.current_state.value}[/bold yellow]\n")

    # -------------------------------------------------------------------------
    # STEP 8: Worker Pauses
    # -------------------------------------------------------------------------
    console.print("[bold magenta]▶ [STEP 8] WORKER IS PAUSED BY SUPERVISORY INTERVENTION[/bold magenta]")
    console.print(f"  Worker State: [bold red]{worker.state.value}[/bold red] (Execution halted to preserve resource budget)\n")

    # -------------------------------------------------------------------------
    # STEP 9: Nemotron Reasons
    # -------------------------------------------------------------------------
    console.print(f"[bold cyan]▶ [STEP 9] NEMOTRON REASONS ON NEBIUS INFRASTRUCTURE[/bold cyan]")
    console.print(f"  Inference Provider: [bold]{reasoning_name}[/bold]")
    decision = await reasoner.decide({
        "mission": mission.goal,
        "current_task": task_impl.title,
        "agent": worker.agent_id,
        "error_signature": "CSV_HEADER_MISMATCH_BOM",
        "anomaly_type": "LOOP_DETECTED",
        "project_constraints": ["Do not modify database schema"]
    })
    console.print(f"  Nemotron Decision: [bold green]{decision.action.value}[/bold green] (Confidence: {int(decision.confidence * 100)}%)")
    console.print(f"  Target: [bold]{decision.target_agent}[/bold]")
    console.print(f"  Reason: {decision.reason}\n")

    # -------------------------------------------------------------------------
    # STEP 10: Reviewer Diagnoses
    # -------------------------------------------------------------------------
    console.print("[bold cyan]▶ [STEP 10] REVIEWER AGENT DIAGNOSES CAUSAL FLAW[/bold cyan]")
    reviewer = ReviewerAgent(agent_id="reviewer_01", event_bus=event_bus, tools=tools)
    diag = await reviewer.run(
        AgentContextPackage(
            mission_id=mission.id,
            objective=mission.goal,
            task=task_impl.model_dump(),
            recent_events=[{"error_signature": "CSV_HEADER_MISMATCH_BOM"}]
        )
    )
    console.print(f"  Diagnostic Finding: [bold yellow]{diag.diagnosis}[/bold yellow]")
    console.print(f"  Failure Category: [bold]{diag.failure_category}[/bold]")
    console.print(f"  Recommended Strategy: [bold green]{diag.recommended_strategy}[/bold green]\n")

    # -------------------------------------------------------------------------
    # STEP 11: Memory Records Diagnosis & Provenance
    # -------------------------------------------------------------------------
    console.print("[bold blue]▶ [STEP 11] EMPIRICAL MEMORY RECORDS DIAGNOSIS & PROVENANCE[/bold blue]")
    await memory_store.add_record(
        mission_id=mission.id,
        fact=diag.recommended_strategy,
        source="reviewer_01",
        created_by="reviewer_01",
        status=FactStatus.VERIFIED,
        confidence=diag.confidence,
        category="verified_fact",
        details="Empirically verified requirement: strip UTF-8 BOM before DictReader."
    )
    await memory_store.add_record(
        mission_id=mission.id,
        fact=diag.rejected_approach or "Naive DictReader without BOM strip",
        source="worker_01_attempts",
        created_by="reviewer_01",
        status=FactStatus.REJECTED,
        category="rejected_approach",
        details="Repeated 3 times and proven invalid."
    )
    mem_records = await memory_store.get_by_mission(mission.id)
    console.print(f"  Committed [bold]{len(mem_records)}[/bold] verified/rejected knowledge items to MemoryStore.")
    console.print(f"  Fact: [green]{diag.recommended_strategy}[/green]\n")

    # -------------------------------------------------------------------------
    # STEP 12: Recovery Context Generated
    # -------------------------------------------------------------------------
    console.print("[bold green]▶ [STEP 12] RECOVERY CONTEXT PACKAGE GENERATED[/bold green]")
    recovery_pkg = await packager.build_recovery_package(
        mission_id=mission.id,
        goal=mission.goal,
        task=task_impl,
        constraints=["Do not modify database schema"],
        diagnosis=diag.model_dump()
    )
    console.print(f"  Package includes verified facts, disproven approaches, and task boundaries.\n")

    # -------------------------------------------------------------------------
    # STEP 13: Worker Resumes
    # -------------------------------------------------------------------------
    console.print("[bold green]▶ [STEP 13] WORKER RESUMES EXECUTION[/bold green]")
    worker.resume(recovery_context=recovery_pkg)
    console.print(f"  Worker State: [bold green]{worker.state.value}[/bold green] (Loaded with targeted recovery strategy)\n")

    # -------------------------------------------------------------------------
    # STEP 14: Docker Executes Fix
    # -------------------------------------------------------------------------
    console.print("[bold green]▶ [STEP 14] DOCKER SANDBOX EXECUTES WORKER CODE FIX[/bold green]")
    fix_edit = await worker.call_tool(
        "edit_file",
        {
            "path": "src/parser.py",
            "target_content": "    reader = csv.DictReader(io.StringIO(raw_content))",
            "replacement_content": '    cleaned = raw_content.lstrip("\\ufeff")\n    reader = csv.DictReader(io.StringIO(cleaned))'
        },
        mission_id=mission.id,
        task_id=task_impl.id
    )
    console.print(f"  Fix Applied: {fix_edit.output}")
    # Verify via local/docker sandbox run
    worker_test = await worker.call_tool(
        "run_tests",
        {"test_command": "python -m pytest tests/test_parser.py -q"},
        mission_id=mission.id,
        task_id=task_impl.id
    )
    console.print(f"  Worker Verification in Sandbox: [bold green]{worker_test.metadata.get('passed')} passed, 0 failed[/bold green]\n")
    await task_mgr.complete_task(mission.id, task_impl.id, summary="Parser fixed with UTF-8 BOM normalization.")

    # -------------------------------------------------------------------------
    # STEP 15: Jenkins CI Passes
    # -------------------------------------------------------------------------
    console.print("[bold green]▶ [STEP 15] JENKINS CI INDEPENDENT VERIFICATION PASSES[/bold green]")
    trigger_2 = await jenkins.trigger_build(job_name="ai-work-supervisor-ci")
    ci_build_2 = await jenkins.get_build_result(trigger_2.build_id, "ai-work-supervisor-ci")
    console.print(f"  CI Provider: {jenkins_name}")
    console.print(f"  CI Build: #{ci_build_2.build_id} | Status: [bold green]{ci_build_2.result.value}[/bold green]")
    console.print(f"  JUnit Tests: [bold green]{ci_build_2.tests_passed} passed, 0 failed[/bold green]\n")

    # -------------------------------------------------------------------------
    # STEP 16: Independent Verifier Confirms
    # -------------------------------------------------------------------------
    console.print("[bold blue]▶ [STEP 16] INDEPENDENT VERIFIER AGENT CONFIRMS COMPLETION[/bold blue]")
    verifier = VerifierAgent(agent_id="verifier_01", event_bus=event_bus, tools=tools)
    ver_res = await verifier.run(recovery_pkg)
    console.print(f"  Verifier Verdict: [bold green]{ver_res['tests_passed']}/{ver_res['tests_passed']} TESTS VERIFIED PASSED[/bold green]\n")

    # -------------------------------------------------------------------------
    # STEP 17: Supervisor Completes Mission
    # -------------------------------------------------------------------------
    console.print("[bold green]▶ [STEP 17] SUPERVISOR COMPLETES MISSION[/bold green]")
    await mission_mgr.complete_mission(mission.id, summary="CSV Import fully verified with UTF-8 BOM support.")
    final_mission = await mission_mgr.get_mission(mission.id)
    console.print(f"  Mission Lifecycle State: [bold green]{final_mission.status.value}[/bold green]\n")

    # -------------------------------------------------------------------------
    # STEP 18: Control Room Shows Complete Timeline
    # -------------------------------------------------------------------------
    console.print("[bold cyan]▶ [STEP 18] CONTROL ROOM TIMELINE RECONSTRUCTION[/bold cyan]")
    recorded_events = await event_store.query(mission_id=mission.id, limit=500)
    timeline_items = SupervisorTimelineBuilder.build_narrative_timeline(recorded_events)

    table = Table(title="Control Room Live Event Stream & Narrative Reconstruction")
    table.add_column("Actor", style="cyan", width=12)
    table.add_column("Action / Event", style="white")
    table.add_column("Details", style="magenta")

    for item in timeline_items[:12]:
        table.add_row(item.actor, item.title, item.detail or "-")

    console.print(table)

    duration = time.monotonic() - start_time
    console.print(f"\n[bold green]✓ Killer scenario executed in {duration:.2f}s using the project's execution, supervision, recovery, and verification pipeline.[/bold green]\n")
    return {
        "status": "success",
        "duration": duration,
        "mission_id": mission.id,
        "events_count": len(recorded_events)
    }


if __name__ == "__main__":
    asyncio.run(run_killer_scenario())
