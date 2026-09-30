# Killer Demo Sequence: "Add CSV Import Validation"

This scenario showcases real autonomous operation, empirical failure detection, Nemotron reasoning, intervention, reviewer delegation, project memory recording, worker recovery, and independent verification.

## Real Execution Command
```bash
python demo/scenarios/scenario_01_loop_recovery.py
```

## Sequence Timeline

| Time | Event | Real System Behavior | Visual Cue |
|---|---|---|---|
| `0:00` | Start Mission | Mission initialized in `demo/sample-project/` | Mission card initializes in Control Room |
| `0:15` | Planner Dispatches | Planner generates 6-step DAG task graph | Tasks illuminate in DAG viewer |
| `0:40` | Worker Acts | Worker inspects `src/parser.py`, executes real pytest | Live event stream fills with tool calls |
| `0:55` | Test Failure | Pytest fails: 45 passed, 2 failed (`AssertionError: Expected 'user_id' header`) | Red badge on task, worker retries |
| `1:10` | Repeated Failure | Worker retries 3 consecutive times with identical failure | Supervisor Rule detects loop ($\ge 3$) |
| `1:20` | Anomaly Detected | Supervisor flags `LOOP_DETECTED` anomaly and pauses Worker | Amber warning banner flashes |
| `1:30` | Nemotron Decides | Nemotron analyzes structured context, outputs `DELEGATE` | Reasoning card displays decision |
| `1:45` | Reviewer Consulted | Reviewer (read-only tools) identifies UTF-8 BOM encoding issue | New verified fact & rejected approach added to Memory |
| `2:00` | Worker Recovers | Worker receives curated recovery context, edits `src/parser.py` via `edit_file` | Tool completed, real tests re-run |
| `2:15` | Verifier Validates | Verifier independently checks all 47 tests + diff | Verifier seal: 47 passed, 0 failed |
| `2:25` | Mission Complete | Supervisor confirms verification and marks mission `COMPLETED` | Green banner with verified memory summary |
