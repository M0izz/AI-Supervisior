# Killer Demo Sequence: Real Autonomous Supervisory Loop

This document details the unified, deterministic killer demonstration for the **AI Work Supervisor**, executing the complete 18-step supervisory lifecycle without mocked event injections.

---

## 1. Quick Demonstration Commands

### Reset Demo Environment to Baseline Clean State
```bash
python -m demo.reset
```
*(Wipes `supervisor_events.jsonl`, clears in-memory API state, and resets `demo/sample-project/src/parser.py` to the naive unpatched baseline).*

### Execute the Unified 18-Step Killer Demo
```bash
python -m demo.scenarios.killer_scenario
```
*(Or alternatively: `python -m demo.scenarios.scenario_01_loop_recovery`)*

### Run with Isolated Docker Sandbox Container (Optional)
```bash
EXECUTION_BACKEND=docker python -m demo.scenarios.killer_scenario
```
*(Runs Worker commands inside hardened `ai-work-supervisor-worker:latest` container with `network_mode="none"`, memory limits, and isolated `/workspace` mount).*

---

## 2. The 18-Step Full System Path

The killer demo executes the exact supervisory path:

$$\text{Human} \to \text{Mission} \to \text{Planner} \to \text{Worker} \to \text{Docker} \to \text{Jenkins} \to \text{Supervisor} \to \text{Nemotron} \to \text{Reviewer} \to \text{Memory} \to \text{Recovery} \to \text{Worker} \to \text{Jenkins} \to \text{Verifier} \to \text{COMPLETED}$$

| Step | Phase | System Action | Control Room Observable Cue |
| :--- | :--- | :--- | :--- |
| **1** | **Mission Creation** | User creates mission `Add CSV Import with UTF-8 BOM Support` in `demo/sample-project`. | Mission status `RUNNING` on active matrix. |
| **2** | **Planner DAG** | Planner decomposes mission into 6 sequential DAG tasks. | Task DAG visualizer illuminates with nodes and file scopes. |
| **3** | **Worker Dispatch** | Worker `worker_01` is assigned to `TASK-002` (CSV Parser implementation). | Agent detail shows active task assignment. |
| **4** | **Docker Execution** | Worker inspects `src/parser.py` within isolated Docker/subprocess sandbox. | Sandbox execution logged with resource limits. |
| **5** | **Repeated Failure** | Worker runs test suite 3 consecutive times; tests fail on UTF-8 BOM marker (`45 passed / 2 failed`). | Task retry badges increment; test failure counts highlighted. |
| **6** | **Jenkins CI Gate** | Independent Jenkins CI triggers build #481; confirms `FAILURE` via JUnit test report. | CI status badge shows `JENKINS FAIL (Build #481)`. |
| **7** | **Supervisor Detection** | Dual-layer Supervisor detects `LOOP_DETECTED` anomaly ($\ge 3$ identical failures). | Amber intervention warning flashes on dashboard. |
| **8** | **Worker Paused** | Supervisor immediately pauses `worker_01` to prevent budget exhaustion. | Worker status transitions to `PAUSED`. |
| **9** | **Nemotron Reasoning** | NVIDIA Nemotron on Nebius analyzes context and outputs `DELEGATE` (confidence 92%). | Structured intervention panel displays decision and reason. |
| **10** | **Reviewer Diagnosis** | Reviewer agent (read-only tools) identifies UTF-8 BOM encoding flaw (`\ufeff` prefix). | Diagnostic findings logged in Reviewer audit trace. |
| **11** | **Memory Recording** | Diagnosis committed as `VERIFIED_FACT` in Project Memory; naive approach saved as `REJECTED_APPROACH`. | Empirical memory records appear with provenance tags. |
| **12** | **Recovery Package** | ContextPackager bundles verified facts, rejected approaches, and constraints. | Curated recovery package dispatched to agent. |
| **13** | **Worker Resumes** | Worker resumes with targeted recovery instructions. | Worker status transitions to `RECOVERING`. |
| **14** | **Docker Code Fix** | Worker applies genuine code fix to `src/parser.py` stripping BOM; re-runs sandbox tests. | File edit applied; sandbox test reports 47 passed / 0 failed. |
| **15** | **Jenkins CI Passes** | Jenkins triggers build #482; independently verifies updated code (`47 passed / 0 failed`). | CI status transitions to `JENKINS PASS (Build #482)`. |
| **16** | **Verifier Handoff** | Independent Verifier agent executes verification suite and confirms completion. | Verifier seal awarded: `47/47 VERIFIED`. |
| **17** | **Mission Completed** | Supervisor marks mission lifecycle `COMPLETED`. | Green victory banner displays on Control Room cockpit. |
| **18** | **Timeline Story** | Event store provides complete narrative reconstruction of the loop and recovery. | Dynamic story timeline displays causal chain from failure to fix. |

---

## 3. Supplementary Demonstrations

- **Scenario 02: Independent CI Verification Gate**
  ```bash
  python -m demo.scenarios.scenario_02_ci_failure
  ```
  *Demonstrates worker premature completion claims blocked by independent Jenkins CI verification.*

- **Scenario 03: Complete Adversarial Failure Matrix**
  ```bash
  python -m demo.scenarios.scenario_03_failure_matrix
  ```
  *Demonstrates timeouts, scope violations, dangerous command approvals, and network partitions.*
