# AI Work Supervisor

> **Control Room & Supervisory Nervous System for Autonomous AI Work**
> 
> *"AI agents are working, the Supervisor is watching them, and the system intervenes when they go wrong."*

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/tests-126%20passed-success.svg)]()
[![Model](https://img.shields.io/badge/model-NVIDIA%20Nemotron--4--340B-76B900.svg)]()
[![Cloud](https://img.shields.io/badge/inference-Nebius%20AI%20Studio-0052FF.svg)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)]()

---

## 1. What the System Does

In real-world software engineering, autonomous AI agents face realistic failure modes:
- They **loop infinitely** on identical syntax or assertion errors.
- They **falsely report completion** when tests actually fail.
- They **drift out of scope** and mutate files they were never authorized to touch.
- They propose **destructive commands** (`rm -rf`, `DROP TABLE`).
- They experience **concurrency file conflicts** when multiple agents edit simultaneously.

The **AI Work Supervisor** solves this by establishing a central, non-bypassable supervisory authority:
1. **Watches what agents actually do**: Monitors tool calls, shell executions, and test outcomes in real-time.
2. **Deterministic & Cognitive Watchdogs**: Detects loops (threshold = 3 identical errors), out-of-scope edits, and execution budget overflows.
3. **Independent CI Verification (Jenkins)**: Refuses to trust self-reported success. Requires cryptographic nonces and empirical JUnit test execution.
4. **Isolated Docker Sandboxing**: Restricts file mounts, disables egress network, drops Linux capabilities, and enforces memory/CPU ceilings.
5. **Causal Reasoning via NVIDIA Nemotron on Nebius**: When an anomaly is detected, uses `nvidia/nemotron-4-340b-instruct` on **Nebius AI Studio** to diagnose root causes and autonomously formulate recovery strategies (e.g. `DELEGATE → Reviewer`).
6. **Strict Human Gate**: Destructive actions require explicit operator sign-off with **Zero Implicit Approval** (timeouts strictly deny).

---

## 2. Architecture & Data Flow

```
                          ┌───────────────────────────┐
                          │    Human Operator /       │
                          │   Control Room UI (Vite)  │
                          └─────────────┬─────────────┘
                                        │ HTTP / WebSocket (:8000)
                                        ▼
                          ┌───────────────────────────┐
                          │   FastAPI Control Plane   │
                          │  (/health, /ready, /ws)   │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │  Supervisor Engine Core   │
                          │(Deterministic Watchdogs & │
                          │ Empirical Memory Store)   │
                          └─────────────┬─────────────┘
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
┌──────────────────────────┐ ┌─────────────────────┐ ┌──────────────────────────┐
│   Nebius AI Cloud        │ │ Docker Sandbox      │ │ Independent Jenkins CI   │
│   (NVIDIA Nemotron)      │ │ Container Engine    │ │ Pipeline (JUnit Report)  │
│                          │ │                     │ │                          │
│ • Model:                 │ │ • Isolated Workdir  │ │ • Nonce validation       │
│   nemotron-4-340b        │ │ • No Network        │ │ • Regressions check      │
│ • Endpoint:              │ │ • Dropped Caps      │ │ • Empirical ground truth │
│   api.studio.nebius.ai/v1│ │ • Memory/CPU limits │ │ • Prevents false success │
└──────────────────────────┘ └─────────────────────┘ └──────────────────────────┘
             │                          ▲                          │
             │ Causal Diagnosis         │ Shell Execution          │ Independent
             │ & Recovery Decision      │                          │ Evidence
             ▼                          │                          │
┌───────────────────────────────────────┴──────────────────────────┴────────────┐
│                       Autonomous Agent Fleet                                 │
│          Planner  •  Worker_01  •  Reviewer_01  •  Verifier_01               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Infrastructure Topology

- **Nebius AI Studio (Cloud)**: Hosts open-source **NVIDIA Nemotron** inference (`nvidia/nemotron-4-340b-instruct`) for supervisory reasoning, anomaly diagnosis, and recovery strategy generation.
- **FastAPI Control Plane**: Asynchronous event hub, state machine, and WebSocket broadcaster.
- **Docker Sandbox Engine**: Dedicated containerized execution environments with strict CPU/memory limits and dropped privileges.
- **Jenkins CI Server**: Independent CI verification runner executing automated test suites and providing empirical JUnit proofs.
- **Control Room UI**: Dense, developer-grade React 19 + TypeScript cockpit.

---

## 3. Quickstart & Local Setup

The system preserves **full offline local development**: all tests, scenarios, and the Control Room UI run locally with zero external dependencies via deterministic fallbacks.

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm
- Docker (optional, for container execution)
- Jenkins (optional, for external CI server)

### 1. Clone & Environment Configuration
```bash
git clone https://github.com/M0izz/AI-Supervisior.git
cd AI-Supervisior

# Copy sample configuration
cp .env.example .env
```

### 2. Configure Nebius API Key (Optional for Cloud Mode)
To connect to NVIDIA Nemotron on Nebius AI Studio:
```ini
NEBIUS_API_KEY=your_nebius_api_key_here
NEBIUS_BASE_URL=https://api.studio.nebius.ai/v1
NEBIUS_MODEL=nvidia/nemotron-4-340b-instruct
```
*(If `NEBIUS_API_KEY` is omitted, the supervisor automatically uses the built-in deterministic local reasoning mock).*

### 3. Install Backend Dependencies & Start API
```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI Control Plane on port 8000
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify backend health:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### 4. Build & Launch the Control Room Frontend
```bash
cd apps/control-room
npm install
npm run build    # Compiles production distribution
npm run dev      # Launches dev server on http://localhost:5173
```
Open [http://localhost:5173](http://localhost:5173) in your browser to access the Control Room.

---

## 4. Control Room UI

The Control Room provides dense, real-time observability across 6 purpose-built pages:

| Page | Description |
| :--- | :--- |
| **1. Control Room** | Cockpit overview with active mission matrix, agent fleet status, real-time interventions, and watchdog readiness. |
| **2. Mission Detail** | Mission objectives, visual Task DAG, Jenkins JUnit build history, and Docker execution audit log. |
| **3. Agent Detail** | Agent profile, assigned DAG task, live tool execution trace, and exclusive file lock monitoring. |
| **4. Supervisor Events** | Live WebSocket event stream with dynamic story timeline and raw payload inspector. |
| **5. Project Memory** | Verified facts with empirical proofs, inferred facts, rejected hypotheses, diagnoses, and full provenance. |
| **6. Approval Queue** | High-risk action approvals table with strict **Zero Implicit Approval** gate, `[DENY]` and `[APPROVE ONCE]` buttons. |

### Persistent Intervention Panel
When the Supervisor detects an anomaly, a structured card surfaces immediately without chain-of-thought dumps:
```
┌────────────────────────────────────────────────────────────────────────┐
│ ⚠ SUPERVISOR INTERVENTION TRIGGERED                    CONFIDENCE 94%  │
├──────────────────────────────────┬─────────────────────────────────────┤
│ DETECTED ANOMALY                 │ SUPERVISOR DECISION & ACTION        │
│ LOOP DETECTED                    │ DELEGATE → REVIEWER_01              │
│ Evidence: 3 consecutive          │ Reason: Repeated failure on regex   │
│ identical test failures          │ parser; escalating to reviewer for  │
│                                  │ causal root diagnosis.              │
└──────────────────────────────────┴─────────────────────────────────────┘
```

---

## 5. Demonstration & Scenario Execution

Reproduce real-world supervisory workflows via the terminal demo runners:

### Scenario 1: Infinite Loop Detection & Reviewer Recovery
Demonstrates an agent trapped in a regex parsing loop, detected by the supervisor, paused, delegated to Reviewer for diagnosis, and successfully recovered:
```bash
python -m demo.scenarios.scenario_01_loop_recovery
```

### Scenario 2: Independent CI Verification & False Completion Rejection
Demonstrates a worker falsely claiming success while Jenkins CI reveals 45 passed / 2 failed, triggering task reopening and recovery:
```bash
python -m demo.scenarios.scenario_02_ci_failure
```

### Scenario 3: Complete Failure Matrix
Executes the adversarial matrix covering timeouts, scope violations, dangerous commands, file contention, and infrastructure outages:
```bash
python -m demo.scenarios.scenario_03_failure_matrix
```

---

## 6. Test Suite & Verification

The system includes a 126-test automated verification suite covering Phases 0 through 10:

```bash
# Run all 126 test cases
python -m pytest tests/ -v

# Run Phase 10 deployment tests specifically
python -m pytest tests/test_phase10_deployment.py -v
```

### Test Classification
- **REAL CLOUD TEST**: Validated against `api.studio.nebius.ai` with NVIDIA Nemotron.
- **LOCAL TEST**: Validated on local container sandboxes and process runners.
- **MOCK TEST**: Validated against deterministic simulation providers for CI outages and loop matrix scenarios.

---

## 7. Media & Screenshots

<!-- Placeholder for Control Room Cockpit Video Demo / Screenshot -->
```
┌───────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│            [ SCREENSHOT / DEMO VIDEO PLACEHOLDER ]                        │
│                                                                           │
│   AI Work Supervisor — Control Room UI in Action:                         │
│   • Live Task DAG Execution Pipeline                                      │
│   • Supervisor Loop Detection & Intervention Banner                       │
│   • Jenkins CI Test Verifications (47/47 Passed)                          │
│   • Empirical Memory Store with Provenance Badges                         │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 8. License

This project is licensed under the [MIT License](LICENSE).
