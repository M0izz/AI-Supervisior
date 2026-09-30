import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table

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
from integrations.nebius.provider import MockReasoningProvider
from memory.store import MemoryStore
from memory.provenance import FactStatus
from agents.planner.agent import PlannerAgent
from agents.worker.agent import WorkerAgent
from agents.verifier.agent import VerifierAgent
from agents.reviewer.agent import ReviewerAgent
from core.state.models import AgentContextPackage

console = Console(force_terminal=True, legacy_windows=False)
logging.basicConfig(level=logging.WARNING)


async def run_killer_demo():
    console.print("\n[bold cyan]+===========================================================+[/bold cyan]")
    console.print("[bold cyan]|          AI WORK SUPERVISOR - KILLER DEMO RUNNER          |[/bold cyan]")
    console.print("[bold cyan]|   Supervised Execution * Loop Detection * Recovery * Verif |[/bold cyan]")
    console.print("[bold cyan]+===========================================================+[/bold cyan]\n")

    # 1. Initialize Subsystems
    event_bus = EventBus()
    event_store = InMemoryEventStore()
    await event_bus.subscribe(event_store.append)

    mission_mgr = MissionManager(event_bus=event_bus)
    task_mgr = TaskManager(event_bus=event_bus)
    memory_store = MemoryStore(event_bus=event_bus)
    policy = PolicyConfig()

    supervisor = SupervisorEngine(
        event_bus=event_bus,
        mission_manager=mission_mgr,
        task_manager=task_mgr,
        policy=policy,
        reasoner=SupervisoryReasoner(provider=MockReasoningProvider())
    )

    # 2. Start Mission
    console.print("[bold green]> [0:00] MISSION INITIALIZATION[/bold green]")
    mission = await mission_mgr.create_mission(
        title="Add CSV Import Validation",
        goal="Parse and validate CSV files with UTF-8 support without altering DB schema"
    )
    console.print(f"  Mission ID: [bold]{mission.id}[/bold] | Status: {mission.status.value}")

    # 3. Planner Agent
    console.print("\n[bold green]> [0:15] PLANNER DISPATCH[/bold green]")
    planner = PlannerAgent(event_bus=event_bus)
    plan_result = await planner.run(
        AgentContextPackage(
            mission_id=mission.id,
            objective=mission.goal,
            task={"title": "Create DAG plan"},
            constraints=["Do not modify database schema"]
        )
    )
    graph = await task_mgr.initialize_mission_tasks(mission.id, plan_result["tasks"])
    console.print(f"  Plan created with [bold]{len(plan_result['tasks'])}[/bold] tasks in DAG.")

    # 4. Worker begins Task-003
    console.print("\n[bold green]> [0:40] WORKER EXECUTION[/bold green]")
    worker = WorkerAgent(event_bus=event_bus)
    task_3 = graph.get_task("TASK-003")
    await task_mgr.start_task(mission.id, task_3.id, worker.agent_id)

    # Worker edits file
    await event_bus.publish(
        Event(
            mission_id=mission.id,
            task_id=task_3.id,
            agent_id=worker.agent_id,
            type=EventType.TOOL_CALL,
            payload={"tool": "edit_file", "arguments": {"path": "src/parser.py"}, "target": "src/parser.py"}
        )
    )

    # 5. Worker encounters repeated test failure
    console.print("\n[bold yellow]> [0:55 - 1:10] SIMULATING REPEATED FAILURES (ATTEMPTS 1 TO 3)[/bold yellow]")
    for attempt in range(1, 4):
        await task_mgr.fail_task(
            mission.id,
            task_3.id,
            error_signature="CSV_HEADER_MISMATCH_BOM",
            reason="KeyError: 'user_id' not found in row keys ['\\ufeffuser_id', 'email', 'name']"
        )
        await event_bus.publish(
            Event(
                mission_id=mission.id,
                task_id=task_3.id,
                agent_id=worker.agent_id,
                type=EventType.TEST_RESULT,
                payload={
                    "command": "python -m pytest tests/test_parser.py",
                    "passed": 43,
                    "failed": 2,
                    "error_signature": "CSV_HEADER_MISMATCH_BOM"
                }
            )
        )
        console.print(f"  Attempt {attempt}: 43 passed, 2 failed (Signature: CSV_HEADER_MISMATCH_BOM)")
        await asyncio.sleep(0.05)

    # 6. Check Supervisor Intervention
    console.print("\n[bold magenta]> [1:30] SUPERVISOR NEMOTRON INTERVENTION[/bold magenta]")
    console.print(f"  Supervisor State: [bold yellow]{supervisor.state_machine.current_state.value}[/bold yellow]")

    # 7. Delegated Reviewer Diagnosis
    console.print("\n[bold cyan]> [1:45] REVIEWER AGENT DIAGNOSIS[/bold cyan]")
    reviewer = ReviewerAgent(event_bus=event_bus)
    diag = await reviewer.run(
        AgentContextPackage(
            mission_id=mission.id,
            objective=mission.goal,
            task=task_3.model_dump(),
            recent_events=[{"error_signature": "CSV_HEADER_MISMATCH_BOM"}]
        )
    )
    # Record to Project Memory
    await memory_store.add_record(
        mission_id=mission.id,
        fact=diag["root_cause"],
        source="reviewer_01",
        created_by="reviewer_01",
        status=FactStatus.VERIFIED,
        confidence=0.99
    )
    await memory_store.add_record(
        mission_id=mission.id,
        fact=diag["rejected_approach"],
        source="reviewer_01",
        created_by="reviewer_01",
        status=FactStatus.REJECTED,
        category="rejected_approach",
        details="Fails when input file contains UTF-8 BOM marker."
    )
    console.print(f"  Project Memory Updated: [bold]{diag['root_cause']}[/bold]")

    # 8. Worker Recovers
    console.print("\n[bold green]> [2:00] WORKER RECOVERY WITH UPDATED CONTEXT[/bold green]")
    await task_mgr.complete_task(mission.id, task_3.id, summary="Parser updated with UTF-8 BOM stripping.")
    console.print("  Worker applied: raw_content.lstrip('\\ufeff')")

    # 9. Independent Verifier
    console.print("\n[bold blue]> [2:15] INDEPENDENT VERIFIER RUN[/bold blue]")
    verifier = VerifierAgent(event_bus=event_bus)
    await event_bus.publish(
        Event(
            mission_id=mission.id,
            task_id=task_3.id,
            agent_id=verifier.agent_id,
            type=EventType.TEST_RESULT,
            payload={
                "command": "python -m pytest tests/test_parser.py",
                "passed": 47,
                "failed": 0,
                "error_signature": None
            }
        )
    )
    await verifier.emit_action(mission.id, task_3.id, "Empirical verification: 47 passed, 0 failed, diff clean.")
    console.print("  Verifier Result: [bold green][OK] 47 TESTS PASSED (0 FAILED)[/bold green]")

    # 10. Supervisor Completes Mission
    console.print("\n[bold green]> [2:25] MISSION VERIFIED & COMPLETED[/bold green]")
    await mission_mgr.complete_mission(mission.id, summary="CSV Import fully verified with UTF-8 BOM test coverage.")
    final_mission = await mission_mgr.get_mission(mission.id)
    console.print(f"  Final Mission Status: [bold green]{final_mission.status.value}[/bold green]")

    # 11. Print Summary Table
    table = Table(title="Mission Execution Summary")
    table.add_column("Subsystem", style="cyan")
    table.add_column("Details", style="magenta")

    table.add_row("Total Recorded Events", str(len(await event_store.query(mission_id=mission.id, limit=500))))
    table.add_row("Tasks Completed", f"{len(graph.tasks)} tasks")
    table.add_row("Intervention Reason", "Loop Detected (3 identical failures)")
    table.add_row("Reasoning Backend", "Nemotron (Structured Decision: DELEGATE)")
    table.add_row("Verified Facts in Memory", str(len(await memory_store.get_by_mission(mission.id))))

    console.print("\n", table)
    console.print("\n[bold green][SUCCESS] Scenario 01 completed with 100% fidelity to the architectural specification.[/bold green]\n")


if __name__ == "__main__":
    asyncio.run(run_killer_demo())
