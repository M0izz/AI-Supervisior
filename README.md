# AI Work Supervisor

> **Control Room & Supervisory Nervous System for Autonomous AI Engineering Work**
> 
> *"AI agents are working, the Supervisor is watching them, and the system intervenes when they go wrong."*

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/tests-126%20passed-success.svg)]()
[![Model](https://img.shields.io/badge/model-NVIDIA%20Nemotron--4--340B-76B900.svg)]()
[![Cloud](https://img.shields.io/badge/inference-Nebius%20AI%20Studio-0052FF.svg)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 1. The Problem

Autonomous AI coding agents can write software independently, but without external supervision, they exhibit severe failure modes:

* **Infinite Loops**: Trapped repeating identical syntactic or runtime errors without making forward progress.
* **Misunderstanding Failures**: Applying superficial patches that treat symptoms rather than root causes.
* **Budget Overruns**: Consuming unbounded LLM tokens, tool calls, and compute cycles without terminating.
* **Modifying Incorrect Files**: Drifting out of declared task scope and mutating unauthorized or unrelated code files.
* **Falsely Claiming Completion**: Hallucinating that a task is finished and tests pass when regressions actually exist.
* **Failing Verification**: Unable to independently confirm code correctness against external continuous integration environments.
* **Losing Project Context**: Repeating previously rejected strategies and failed hypotheses across agent iterations.

---

## 2. The Solution

**AI Work Supervisor** is an authoritative control plane that supervises autonomous AI engineering work. It enforces non-bypassable constraints, monitors real-time agent telemetry, and intervenes before failures cause damage.

### Core Supervisory Loop

```
GOAL ──► PLAN ──► ACT ──► OBSERVE ──► VERIFY ──► SUPERVISE ──► RECOVER ──► VERIFY
```

1. **GOAL**: Human operator defines the mission objective in natural language.
2. **PLAN**: Planner agent decomposes the goal into a directed acyclic task graph (DAG).
3. **ACT**: Autonomous Worker agent modifies source code within an isolated sandbox.
4. **OBSERVE**: Watchdogs monitor tool calls, file diffs, iteration budgets, and test outputs.
5. **VERIFY**: Independent Jenkins CI runs automated pipelines to establish empirical ground truth.
6. **SUPERVISE**: Dual-layer supervisor detects anomalies and invokes NVIDIA Nemotron on Nebius for causal reasoning.
7. **RECOVER**: Reviewer agent diagnoses the failure; Project Memory packages recovery context; Worker resumes with targeted instructions.
8. **VERIFY**: Independent Verifier agent confirms all tests pass with zero regressions before task completion.

---

## 3. Technology Roles

Each technology in the stack fulfills an explicit, specialized role:

| Technology | Role | Description |
| :--- | :--- | :--- |
| **Nemotron** | **Supervisory Reasoning** | Open-source NVIDIA Nemotron-4-340B-Instruct evaluates complex failure context, performs causal reasoning, and decides whether to pause, delegate, or terminate. |
| **Supervisor** | **Intervention Decisions** | Deterministic engine combining rule-based watchdogs (loop detection, budget ceilings, scope boundaries) with cognitive decisions to control agent execution tokens. |
| **Worker** | **Autonomous Implementation** | Coding agent equipped with read, write, and bash tools to implement features and bug fixes within its assigned file scope. |
| **Docker** | **Isolated Execution** | Sandboxed container runtime with dropped Linux capabilities (`ALL`), memory limits (`512MB`), CPU quotas (`1.0`), and zero-network isolation (`none`). |
| **Jenkins** | **Independent CI Verification** | External continuous integration server executing automated test suites with cryptographic nonces to produce tamper-proof JUnit verification reports. |
| **Reviewer** | **Failure Diagnosis** | Specialized read-only diagnostic agent that analyzes execution diffs, error traces, and git logs to isolate root causes without modifying code. |
| **Memory** | **Persistent Project Knowledge** | Empirical knowledge store retaining verified facts with provenance tags and recording rejected hypotheses to prevent repeating failed strategies. |
| **Verifier** | **Final Validation** | Independent verification agent that reviews test results, confirms acceptance criteria, and issues final sign-off before a mission completes. |
| **EventBus** | **Real-Time Coordination** | High-throughput asynchronous event backbone connecting agents, supervisor watchdogs, WebSocket broadcasters, and audit loggers. |
| **Nebius** | **AI Infrastructure** | Nebius AI Studio provides high-performance cloud hosting for the open-weights NVIDIA Nemotron-4-340B foundation model. |

---

## 4. Architecture Diagram

```
                        ┌────────────────────────────────────────┐
                        │      Human Operator / Control Room     │
                        │    (React 19 + TypeScript Cockpit)     │
                        └───────────────────┬────────────────────┘
                                            │ HTTP / WebSocket (:8000)
                                            ▼
                        ┌────────────────────────────────────────┐
                        │      FastAPI Control Plane Engine      │
                        │  (/health, /ready, /ws/events, State)  │
                        └───────────────────┬────────────────────┘
                                            │
                        ┌───────────────────┴────────────────────┐
                        ▼                                        ▼
           ┌──────────────────────────┐             ┌──────────────────────────┐
           │    SUPERVISOR ENGINE     │             │        EVENT BUS         │
           │ • Deterministic Watchdog │             │ • Real-time coordination │
           │ • Scope & Budget Guard   │             │ • Persistent event log   │
           │ • Zero-Implicit-Approval │             │ • WebSocket broadcast    │
           └────────────┬─────────────┘             └──────────────────────────┘
                        │
       ┌────────────────┼────────────────┬────────────────┐
       ▼                ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│Nebius Cloud  │ │Docker Sandbox│ │  Jenkins CI  │ │Project Memory│
│(NVIDIA       │ │(Containers,  │ │(Independent  │ │(Verified     │
│ Nemotron)    │ │ No Network,  │ │ JUnit Proof, │ │ Facts, Diffs,│
│              │ │ 512MB Limit) │ │ Nonce Gate)  │ │ Hypotheses)  │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │                │
       └────────────────┼────────────────┴────────────────┘
                        ▼
       ┌──────────────────────────────────────────────────┐
       │             AUTONOMOUS AGENT FLEET               │
       │  Planner  •  Worker  •  Reviewer  •  Verifier    │
       └──────────────────────────────────────────────────┘
```

---

## 5. The Killer Demo Scenario

The system features a 100% genuine, deterministic killer scenario demonstrating the complete recovery cycle without mocked events:

```
Worker Failure
   ▼
Supervisor Detection (Loop Detected: 3 consecutive failures)
   ▼
Nemotron Decision (Causal reasoning on Nebius: DELEGATE)
   ▼
Reviewer Diagnosis (Read-only analysis: UTF-8 BOM encoding bug)
   ▼
Memory (Records verified fact and rejected hypothesis)
   ▼
Recovery (Context packager generates targeted instructions)
   ▼
Docker Execution (Worker resumes, executes byte-level fix in sandbox)
   ▼
Jenkins Verification (Build #482 confirms 47/47 tests passed)
   ▼
Verifier (Independent confirmation: zero regressions)
   ▼
SUCCESS (Mission completed)
```

### Complete 18-Step Execution Path

1. **User creates mission**: `Add CSV Import with UTF-8 BOM Support` in `demo/sample-project`.
2. **Planner creates tasks**: Generates 6-node DAG with strict file scope boundaries.
3. **Worker starts**: `worker_01` assigned to `TASK-002` (`src/parser.py`).
4. **Docker executes worker**: Inspects code within sandboxed environment.
5. **Worker encounters repeated failure**: Tests fail 3 consecutive times on byte order mark (`45 passed / 2 failed`).
6. **Jenkins independently confirms failure**: Build #481 confirms `FAILURE` via JUnit test reports.
7. **Supervisor detects anomaly**: Watchdog flags `LOOP_DETECTED` threshold reached.
8. **Worker pauses**: Supervisor revokes execution token and halts agent.
9. **Nemotron reasons**: NVIDIA Nemotron on Nebius evaluates failure context and issues `DELEGATE`.
10. **Reviewer diagnoses**: Read-only Reviewer isolates UTF-8 BOM encoding issue (`\ufeff` prefix).
11. **Memory records diagnosis**: Saved as `VERIFIED_FACT` in Project Memory; regex approach recorded as `REJECTED_APPROACH`.
12. **Recovery context is generated**: Context packager bundles diagnosis and constraints.
13. **Worker resumes**: Worker receives recovery package.
14. **Docker executes fix**: Worker modifies `src/parser.py` using `codecs.BOM_UTF8` strip; re-runs sandbox tests.
15. **Jenkins passes**: Jenkins build #482 independently verifies `47 passed / 0 failed`.
16. **Verifier confirms**: Verifier agent inspects JUnit proofs and signs off.
17. **Supervisor completes mission**: Mission lifecycle transitions to `COMPLETED`.
18. **Control Room shows complete timeline**: Dynamic story timeline renders the end-to-end causal trace.

---

## 6. Reproducibility & Exact Commands

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Docker (optional, for container execution)
- Jenkins (optional, for external CI server)

### 1. Clone & Configure Environment
```bash
git clone https://github.com/M0izz/AI-Supervisior.git
cd AI-Supervisior

# Copy sample configuration (preconfigured with local deterministic fallbacks)
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

### 3. Install Dependencies & Launch Backend
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

### 4. Build & Launch Control Room UI
```bash
cd apps/control-room
npm install
npm run build    # Compiles production distribution
npm run dev      # Launches dev server on http://localhost:5173
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

### 5. Reset Demo Environment
Before running demonstrations, reset the demo workspace to a clean baseline:
```bash
python -m demo.reset
```

### 6. Execute the Killer Demo
Run the complete 18-step killer demonstration in your terminal:
```bash
python -m demo.scenarios.killer_scenario
```
*(Or alternatively: `python -m demo.scenarios.scenario_01_loop_recovery`)*

### 7. Run Complete Automated Test Suite
```bash
python -m pytest tests/ -v
```

---

## 7. Control Room User Interface

The Control Room provides dense, real-time observability across 6 purpose-built pages:

| Page | Purpose |
| :--- | :--- |
| **Control Room** | Central operations dashboard with active mission matrix, agent fleet status, real-time interventions, and watchdog readiness. |
| **Mission Detail** | Mission objectives, interactive visual Task DAG, Jenkins JUnit build history, and Docker execution audit log. |
| **Agent Detail** | Agent profile, assigned DAG task, live tool execution trace, and exclusive file lock monitoring. |
| **Supervisor Events** | Live WebSocket event stream with dynamic story timeline and raw payload inspector. |
| **Project Memory** | Empirical facts with test proof IDs, rejected hypotheses, reviewer diagnoses, and full provenance badges. |
| **Approval Queue** | High-risk action approvals table with strict **Zero Implicit Approval** gate (timeouts automatically deny). |

---

## 8. Documentation Index

- [Architecture Guide](docs/architecture.md) — Comprehensive technical design and data flows.
- [Hackathon Requirements Mapping](docs/hackathon-requirements.md) — Feature-by-feature evaluation matrix.
- [3-Minute Demo Presentation Script](docs/demo-script.md) — Stage presentation script with timestamps and visual cues.
- [Killer Demo Detailed Guide](docs/demo.md) — Step-by-step demonstration walkthrough.
- [Deployment Guide](docs/deployment.md) — Production Nebius AI Studio and container deployment guide.
- [Docker Execution Hardening](docs/docker-execution.md) — Sandbox security profiles and privilege isolation.
- [Jenkins CI Integration](docs/jenkins-integration.md) — Independent continuous integration verification pipeline.
- [Mission Control Plane](docs/control-plane.md) — Agent registry, file locking, and multi-mission orchestration.
- [Reliability & Adversarial Report](docs/reliability-report.md) — 24-scenario adversarial failure test matrix.

---

## 9. Security & Safety Principles

1. **Zero Implicit Approval**: High-risk actions require explicit human operator approval. Any approval timeout strictly defaults to `DENIED`.
2. **Credential Sanitization**: Bearer tokens, API keys, passwords, and private URLs are stripped from logs and UI streams before emission.
3. **Container Isolation**: Untrusted agent code runs with dropped Linux capabilities (`cap_drop=["ALL"]`), zero network egress (`network_mode="none"`), and hard memory/CPU limits.
4. **Independent Verification**: No agent is permitted to certify its own success. Passing is only awarded after external Jenkins CI execution and Verifier validation.

---

## 10. License

This project is open-source software licensed under the [MIT License](LICENSE).
