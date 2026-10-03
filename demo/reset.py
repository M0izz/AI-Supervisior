import asyncio
import os
import shutil
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def reset_sample_project(workspace_root: Path) -> None:
    """Restores sample project parser.py to its original unpatched implementation."""
    src_dir = workspace_root / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    parser_file = src_dir / "parser.py"

    naive_parser_content = (
        'import csv\n'
        'import io\n'
        'from typing import Any, Dict, List\n\n'
        'def parse_csv_data(raw_content: str) -> List[Dict[str, Any]]:\n'
        '    """Parses CSV data into list of dictionaries (naive implementation without BOM handling)."""\n'
        '    reader = csv.DictReader(io.StringIO(raw_content))\n'
        '    return [row for row in reader]\n'
    )
    parser_file.write_text(naive_parser_content, encoding="utf-8")
    print(f"[RESET] Reset {parser_file} to baseline naive implementation.")


def reset_event_logs(project_root: Path) -> None:
    """Cleans up in-workspace event log files."""
    event_file = project_root / "supervisor_events.jsonl"
    if event_file.exists():
        event_file.unlink()
        print(f"[RESET] Removed {event_file}.")
    # Create empty fresh event file
    event_file.touch()
    print(f"[RESET] Initialized fresh {event_file}.")


def reset_in_memory_state():
    """Resets global AppState if running in an active API process."""
    try:
        from apps.api.state import app_state
        app_state.event_store._events.clear()
        app_state.agent_registry._records.clear()
        app_state.agent_registry._instances.clear()
        app_state.agent_registry._file_locks.clear()
        app_state.memory_store._records.clear()
        app_state.approval_manager._requests.clear()
        app_state.mission_manager._missions.clear()
        app_state.task_manager._graphs.clear()
        print("[RESET] Cleared API in-memory stores and state machines.")
    except Exception as e:
        print(f"[RESET] In-memory reset note: {e} (normal if running standalone)")



def main():
    print("=" * 60)
    print(" AI WORK SUPERVISOR — DEMO STATE RESET")
    print("=" * 60)

    workspace_root = PROJECT_ROOT / "demo" / "sample-project"
    reset_sample_project(workspace_root)
    reset_event_logs(PROJECT_ROOT)
    reset_in_memory_state()

    print("=" * 60)
    print(" [SUCCESS] Demo environment cleanly reset and ready for re-run.")
    print("=" * 60)


if __name__ == "__main__":
    main()
