# Killer Demo Sequence: "Add CSV Import Validation"

This scenario showcases autonomous operation, failure detection, Nemotron reasoning, intervention, reviewer delegation, and independent verification.

## Sequence Timeline

| Time | Event | System Behavior | Visual Cue |
|---|---|---|---|
| `0:00` | Start Mission | User inputs: *"Add CSV import validation"* | Mission card initializes in Control Room |
| `0:15` | Planner Dispatches | Planner generates 6-step DAG task graph | Tasks illuminate in DAG viewer |
| `0:40` | Worker Acts | Worker edits `src/parser.py`, runs tests | Live event stream fills with tool calls |
| `0:55` | Test Failure | Test fails: `CSV_HEADER_MISMATCH (UTF-8 BOM)` | Red badge on task, worker retries |
| `1:10` | Repeated Failure | Worker retries same logic, same failure | Supervisor Rule detects loop ($\ge 3$) |
| `1:20` | Anomaly Detected | Supervisor flags `LOOP_DETECTED` anomaly | Amber warning banner flashes |
| `1:30` | Nemotron Decides | Nemotron analyzes context, outputs `DELEGATE` | Reasoning card displays decision |
| `1:45` | Reviewer Consulted | Reviewer pinpoints UTF-8 BOM encoding issue | New verified fact added to Project Memory |
| `2:00` | Worker Recovers | Worker receives context package with rejected approach, fixes code | Green test results stream in |
| `2:15` | Verifier Validates | Verifier independently checks all 47 tests + diff | Verifier seal: 100% passed |
| `2:25` | Mission Complete | Supervisor marks mission `VERIFIED_COMPLETE` | Green banner with verified memory summary |
