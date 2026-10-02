# Killer Demo Sequence: "Add CSV Import Validation"

This scenario showcases real autonomous operation, empirical failure detection, Nemotron reasoning, intervention, reviewer delegation, project memory recording, worker recovery, and independent verification.

## Real Execution Commands

### Mode 1: Local Execution Sandbox (Default)
```bash
python demo/scenarios/scenario_01_loop_recovery.py
```

### Mode 2: Docker Container Isolation Sandbox (Phase 5)
```bash
EXECUTION_BACKEND=docker python demo/scenarios/scenario_01_loop_recovery.py
```
*(Runs Worker commands inside hardened `ai-work-supervisor-worker:latest` container with `network_mode="none"`, memory limits, and isolated `/workspace` mount).*


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

---

# Scenario 02: "Premature Completion vs. Independent Jenkins CI Gate" (Phase 6)

This scenario demonstrates the central architectural principle: **Worker completion is not verification**.
A worker claims task completion prematurely. An independent Jenkins CI execution pipeline detects hidden test failures, halts false completion, invokes Nemotron reasoning, and delegates to a Reviewer to guide the worker through recovery until full verification is achieved.

## Execution Commands

### Mode 1: Local / Deterministic Mock Jenkins (Default)
```bash
python demo/scenarios/scenario_02_ci_failure.py
```
*(Runs against `demo/sample-project` with dynamic workspace inspection; verifies code changes directly without requiring an active Jenkins server).*

### Mode 2: Live Jenkins Server Integration
```bash
JENKINS_ENABLED=true python demo/scenarios/scenario_02_ci_failure.py
```
*(Requires a running Jenkins server configured with `JENKINS_URL`, `JENKINS_JOB_NAME`, and `JENKINS_API_TOKEN`).*

## Sequence Timeline

| Time | Event | Real System Behavior | Verification Status |
|---|---|---|---|
| `0:00` | Start Mission | Mission initialized in workspace | `RUNNING` |
| `0:10` | Planner DAG | Planner creates task graph, assigns `TASK-002` to Worker | `IN_PROGRESS` |
| `0:25` | Premature Claim | Worker inspects parser, claims `"Implementation complete"` | **UNVERIFIED CLAIM** |
| `0:45` | Jenkins Run #1 | Jenkins independently triggers and tests workspace: 45 passed, 2 failed | `CI_FAILURE` (Build #481) |
| `1:10` | Supervisor Gate | Supervisor rejects completion claim, reopens task, pauses worker | **COMPLETION REJECTED** |
| `1:25` | Nemotron Reasoning | Nemotron analyzes CI contradiction, decides `DELEGATE → Reviewer` | Supervisory Decision |
| `1:40` | Reviewer Diagnosis | Reviewer discovers UTF-8 BOM encoding mismatch | Failure signature isolated |
| `1:55` | Memory Provenance | Verified fact stored in Project Memory (`source: jenkins_build_481`) | Provenance attached |
| `2:10` | Worker Recovers | Worker receives recovery context, applies real fix to `src/parser.py` | Implementation updated |
| `2:30` | Jenkins Run #2 | Jenkins independently verifies updated code: 47/47 passed | `CI_SUCCESS` (Build #482) |
| `2:45` | Verifier Handoff | Independent Verifier agent empirically confirms all tests pass | Final verification confirmed |
| `3:00` | Mission Complete | Supervisor confirms empirical evidence and marks mission `COMPLETED` | `VERIFIED` / `COMPLETED` |

