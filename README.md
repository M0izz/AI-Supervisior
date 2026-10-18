# AI Supervisor

> **Graph-Powered Memory and Coordination Layer for AI Agents.**
>
> *"Your AI agents work. Your Supervisor makes sure they finish the job."*

[![Track 02: Agent Memory & Coordination](https://img.shields.io/badge/FalkorDB%20Graph%20Hacks-Track%2002%3A%20Memory%20%26%20Coordination-FF4F00?style=for-the-badge&logo=redis)](docs/FALKORDB_GRAPH_INTEGRATION.md)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-ai--supervisior.vercel.app-blueviolet?style=for-the-badge&logo=vercel)](https://ai-supervisior.vercel.app/)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI%20%2B%20Python%203.11%2B-009688?style=for-the-badge&logo=fastapi)](apps/api/)
[![Frontend](https://img.shields.io/badge/frontend-React%2019%20%2B%20TypeScript-61DAFB?style=for-the-badge&logo=react)](apps/control-room/)
[![FalkorDB](https://img.shields.io/badge/Graph%20Memory-FalkorDB%20Property%20Graph-orange?style=for-the-badge)](storage/graph/)
[![License](https://img.shields.io/badge/license-MIT-blue?style=for-the-badge)](LICENSE)

[🚀 Live Hosted Demo](https://ai-supervisior.vercel.app/) • [FalkorDB Graph Integration Guide](docs/FALKORDB_GRAPH_INTEGRATION.md) • [GitHub Repository](https://github.com/M0izz/AI-Supervisior) • [Documentation Index](#12-documentation-index) • [Production Deployment](#8-production-deployment)

---

## 1. What is AI Supervisor?

Autonomous coding agents (Claude Code, OpenAI Codex, Gemini CLI, Qwen, OpenCode, Kimi) generate code rapidly. However, left unsupervised, they frequently loop on identical errors, hallucinate test passes, drift out of declared task scopes, run destructive shell commands, or silently abandon tasks.

**AI Supervisor** turns **FalkorDB** into a persistent, queryable coordination and memory layer for multi-agent workflows. It maps missions, tasks, multi-attempt execution histories, causal failures, recovery decisions, agent handoffs, produced artifacts, and empirical verification evidence into an authoritative property graph.

Before dispatching tasks or attempting recovery, the supervisor queries FalkorDB to retrieve predecessor dependencies and historical failure signatures. Its decision lineage makes it possible to inspect not only what an agent did, but also which exact events and relationships informed the supervisor's response. Unlike a simple execution dashboard, AI Supervisor preserves context across retries and restarts while keeping final completion strictly dependent on independent verification evidence.

> **Core Axiom**: *Worker completion ≠ verified completion.* No agent is permitted to certify its own success.

```
Goal ──► Plan Gate ──► Route ──► Execute ──► FalkorDB Graph ──► Intervene ──► Handoff ──► Verify ──► Complete
```

---

## 2. FalkorDB: The Graph Memory & Coordination Layer

FalkorDB is central to AI Supervisor's nervous system. It is **not** an auxiliary cache or decorative visualization database: graph queries actively govern task dispatch, recovery routing, and verification gates.

```
                   FALKORDB AUTHORITATIVE PROPERTY GRAPH
  ┌────────────────────────────────────────────────────────────────────────┐
  │                                                                        │
  │  (:Mission) ──[:CONTAINS_TASK]──► (:Task) ──[:DEPENDS_ON]──► (:Task)   │
  │       │                               ▲                                │
  │       │                      [:FOR_TASK]                               │
  │  [:HAS_REQUIREMENT]                   │                                │
  │       ▼                               │                                │
  │  (:Requirement)             (:Execution Attempt 1)                     │
  │                                       │                                │
  │                                 [:FAILS_WITH]                          │
  │                                       ▼                                │
  │                           (:ExecutionEvent: Failure)                   │
  │                                       ▲                                │
  │                                 [:RESPONDS_TO]                         │
  │                                       │                                │
  │                                 (:Decision)                            │
  │                                       │                                │
  │                                   [:SELECTS]                           │
  │                                       ▼                                │
  │  (:Agent: Codex) ◄──[:TRANSFERS]── (:Handoff) ◄── (:Agent: Claude)     │
  │         │                                                              │
  │     [:EXECUTES]                                                        │
  │         ▼                                                              │
  │  (:Execution Attempt 2) ──[:PRODUCES]──► (:Artifact)                   │
  │         ▲                                                              │
  │  [:EVALUATES_EXECUTION]                                                │
  │         │                                                              │
  │  (:Verification) ──[:SUPPORTED_BY]──► (:Evidence: Empirical Proof)     │
  │         │                                                              │
  │    [:EVALUATES] ──► (:Task)                                            │
  │                                                                        │
  └────────────────────────────────────────────────────────────────────────┘
```

### Architectural Traceability Invariants

1. **Failure Causality (`FAILS_WITH`)**:
   `(:Execution)-[:FAILS_WITH]->(:ExecutionEvent)` links an execution attempt directly to the causal failure event that explains its failure (including error signatures and diagnostic payloads), preventing ambiguity with generic task events.
2. **Verification Lineage (`EVALUATES_EXECUTION` and `EVALUATES`)**:
   `(:Verification)-[:EVALUATES]->(:Task)` and `(:Verification)-[:EVALUATES_EXECUTION]->(:Execution)` identify the exact execution attempt and task evaluated, guaranteeing that a passing verification cannot accidentally validate an untested subsequent retry.
3. **Empirical Prerequisite Gate (`DEPENDS_ON`)**:
   `(:Task)-[:DEPENDS_ON]->(:Task)` requires predecessor tasks to have an accepted Verification node (`is_verified = true`). If prerequisites lack empirical proof, the supervisor halts dispatch with a `BLOCK_DISPATCH` decision.

---

## 3. How AI Supervisor Works: The 7-Stage Supervisory Lifecycle

AI Supervisor orchestrates autonomous coding agents through a deterministic, auditable 7-stage operational lifecycle:

```
User Goal
   │
   ▼
[ 1. PLAN GATE ] ───────► Gemma 4 / Gemini parses goal into DAG with strict file scopes.
   │                      Mission locked in AWAITING_APPROVAL until human sign-off.
   ▼
[ 2. GRAPH DAG ] ───────► FalkorDB stores Task DAG. Traversal verifies predecessors have
   │                      empirical Verification acceptance (not merely status strings).
   ▼
[ 3. ROUTE & EXECUTE ] ─► Dynamic Router dispatches task to best agent (Claude, Codex, etc.)
   │                      running inside an isolated, scoped Git worktree.
   ▼
[ 4. OBSERVE ] ─────────► Real-time Event Bus streams actions; Watchdogs detect repetitive
   │                      failure loops (3x identical stack trace) and dangerous commands.
   ▼
[ 5. RECOVER ] ─────────► FalkorDB queries failure history; records Decision (RESPONDS_TO Event)
   │                      and routes Handoff to specialized secondary agent.
   ▼
[ 6. VERIFY ] ──────────► Independent Verifier tests in clean sandbox: Unit Tests + Git Diffs +
   │                      Scope Invariants. Links Verification to Execution with Evidence.
   ▼
[ 7. REMEMBER & SYNC ] ─► Project Memory stores facts/rejected approaches; SQLite Outbox syncs
                          state across developer machines and cloud cockpit.
```

### Stage Breakdown

1. **Stage 1: Intent Parsing & Mandatory Plan Review Gate**:
   - The user inputs a mission goal in natural language.
   - **Google Gemma 4** (or Gemini) parses the request into structured deliverables, in-scope files, explicit exclusions, and acceptance criteria.
   - **The Plan Gate**: The mission is placed in `AWAITING_APPROVAL`. No agent is permitted to touch code or start execution until a human operator reviews and explicitly approves the plan.
2. **Stage 2: DAG Resolution & FalkorDB Coordination**:
   - Approved tasks are stored in FalkorDB with `(:Task)-[:DEPENDS_ON]->(:Task)` relationships.
   - Before dispatching any task, the supervisor queries `get_task_graph_context`. Prerequisite tasks must possess an accepted `Verification` node (`is_verified == True`). Unverified tasks trigger an automatic `BLOCK_DISPATCH` decision.
3. **Stage 3: Multi-Agent Fleet Routing & Isolated Execution**:
   - The **Dynamic Router** selects the best agent for each task based on declared capabilities and historical verification scores.
   - Workers run inside isolated Git worktrees (`.worktrees/mission-xxx/`) or single-host Docker sandboxes with file-path whitelisting to prevent repository pollution.
4. **Stage 4: Real-Time Event Bus & Active Loop Watchdogs**:
   - Every terminal command, AST edit, and test execution emits structured events into the asynchronous Event Bus.
   - **Active Watchdogs** monitor execution streams to intercept infinite loops (3 repetitive failure signatures), unauthorized scope expansions, and dangerous commands (`rm -rf`, destructive SQL `DROP TABLE`).
5. **Stage 5: Causal Failure Logging & Decision Recovery in FalkorDB**:
   - When an execution attempt fails, FalkorDB records `(:Execution)-[:FAILS_WITH]->(:ExecutionEvent)`.
   - The supervisor traverses FalkorDB for previous failure history on the task to extract error signatures and avoid repeated bad patches.
   - It records a `(:Decision)` node linking `[:RESPONDS_TO]` the causal event and `[:SELECTS]` the recovery agent, transferring context via a `(:Handoff)` node.
6. **Stage 6: Independent Verification Perimeter**:
   - **Core Invariant**: The worker agent is **never** permitted to verify its own work.
   - An independent Verification Agent runs automated test suites, validates git diff boundaries, checks for syntax/AST integrity, and ensures no regressions were introduced.
   - The verdict is recorded in FalkorDB: `(:Verification)-[:EVALUATES_EXECUTION]->(:Execution)` linked to empirical proof via `[:SUPPORTED_BY]->(:Evidence)`.
7. **Stage 7: Local-First Multi-Device Sync**:
   - Operational logs and outbox events sync bidirectionally between local developer laptops and cloud control rooms using SQLite-backed transactional queues and WebSocket streams.

---

## 4. Product Cockpit: FalkorDB Graph Inspector

The React Control Room (`apps/control-room`) includes an interactive, polished **FalkorDB Graph Memory Inspector**:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  AI SUPERVISOR  ::  CONTROL ROOM              FALKORDB: CONNECTED  ●  LATENCY: 1.2ms  ●  NODES: 14     │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  MISSION: Add CSV Ingestion with UTF-8 BOM Support [MSN-042]                                           │
│  [Mandatory Plan Review (v1 APPROVED)]  [FALKORDB GRAPH MEMORY]  [Mission Story]  [Verification]       │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TRACEABILITY LINEAGE PIPELINE:                                                                        │
│  1.Mission (1) ──► 2.Task DAG (3) ──► 3.Execution (2) ──► 4.Failure (1) ──► 5.Decision (1) ──► ...   │
├───────────────────────────────────────────────────────────────────┬────────────────────────────────────┤
│  VISUAL TOPOLOGY / LINEAGE FLOW VIEW                              │  NODE PROPERTIES & EVIDENCE DRAWER │
│                                                                   │                                    │
│  (:Mission: MSN-042)                                              │  [VERIFICATION] ver_dbe42e22       │
│       │                                                           │  Status: ACCEPT                    │
│       ├──► (:Task: Implement Parser)                              │  Target: Task 002 (Attempt 2)      │
│       │         │                                                 │                                    │
│       │     [:FOR_TASK]                                           │  LINKED EMPIRICAL EVIDENCE:        │
│       │         ▼                                                 │  ✓ Unit Tests (47/47 passed)       │
│       │    (:Execution: Attempt 1) ──[:FAILS_WITH]──► (BOM Loop)  │  ✓ Worktree Git Diff Invariant     │
│       │         │                                       ▲         │  ✓ Scope Boundary Integrity        │
│       │     [:RETRIED_BY]                               │         │  ✗ Baseline Regression (None)      │
│       │         ▼                                 [:RESPONDS_TO]  │                                    │
│       │    (:Execution: Attempt 2)                      │         │  UPSTREAM / DOWNSTREAM PATH:       │
│       │         ▲                                 (:Decision)     │  (e2) -[:PRODUCES]-> (parser.py)   │
│       │         │                                                 │  (v) -[:EVALUATES_EXECUTION]-> (e2)│
│       │  [:EVALUATES_EXECUTION]                                   │  (v) -[:SUPPORTED_BY]-> (ev_01)    │
│       │         │                                                 │                                    │
│       └────(:Verification: ACCEPT) ──[:SUPPORTED_BY]──► (Evidence)│  [Copy Node ID]  [Close Drawer]    │
└───────────────────────────────────────────────────────────────────┴────────────────────────────────────┘
```

- **Lineage Flow & SVG Topology**: Switch between stage-by-stage causality cards and full directed SVG graph layout with zoom/pan controls.
- **Node Inspector & Evidence Drawer**: Click any node to slide open its properties, incoming/outgoing directed relationships, causal failure explanation, and linked empirical test assertions.

---

## 5. Infrastructure Providers & AI Substrates

AI Supervisor coordinates a best-of-breed hybrid infrastructure topology, leveraging dedicated providers for memory, reasoning, hosting, and sandboxed execution:

```
                                  AI SUPERVISOR
                     (Control Plane & Supervisory Nervous System)
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           ▼                            ▼                            ▼
     AGENT RUNTIMES            INTELLIGENCE / MODELS          INFRASTRUCTURE
  (Who does the work)           (Who reasons & plans)      (Where execution runs)
           │                            │                            │
   • Claude Code (Anthropic)    • Google Gemma 4             • FalkorDB Property Graph
   • OpenAI Codex               • Google Gemini API            - Task DAG & Readiness
   • Google Gemini CLI          • Nebius Models                - Failure Causal Chains
   • Qwen 2.5 Coder               - NVIDIA Nemotron            - Verification Evidence
   • OpenCode                     - Nous Hermes              • DigitalOcean
   • Moonshot Kimi                - Qwen 2.5                   - Droplets & MicroVMs
   • Nous Hermes Agent            - DeepSeek R1                - Serverless Inference
   • Block Goose                • Local Models               • Nebius AI Studio
   • Cline                        - Ollama / llama.cpp         - High-Throughput Tokens
                                                             • Vercel & Render (Hosting)
                                                             • Local Workstation (Worktrees)
```

### Provider Matrix

| Infrastructure Provider | Role in AI Supervisor | Operational Responsibility |
| :--- | :--- | :--- |
| **FalkorDB** | **Graph Memory & Coordination** | Stores the authoritative property graph: Task DAG, multi-attempt execution histories, causal failures (`FAILS_WITH`), supervisory decisions (`RESPONDS_TO`, `SELECTS`), agent handoffs, and verification evidence. |
| **DigitalOcean** | **Cloud Compute & Serverless Gemma 4** | Hosts DigitalOcean Droplets and MicroVM container sandboxes for remote worker isolation; provides serverless inference for Google Gemma 4; manages the Action Gateway security perimeter. |
| **Nebius AI Studio** | **High-Throughput Open Model Factory** | Low-latency inference gateway hosting open weights models (NVIDIA Nemotron 4-340B, Nous Hermes, Qwen 2.5 Coder, DeepSeek R1) for rapid code generation, recovery planning, and AST invariant extraction. |
| **Google Cloud & Gemini API** | **Deep Diagnostic Reasoning** | Multimodal reasoning, deep diagnostic root-cause analysis for complex test failures, architectural boundary review, and structured natural language plan interpretation. |
| **OpenRouter** | **Multi-Model Inference & Failover** | Unified routing substrate providing access to frontier models (Claude 3.7 Sonnet, GPT-4o, DeepSeek) with automated failover and budget management. |
| **Backboard.io (Espri.ai)** | **Sovereign AI Persistent Memory** | Long-term memory store and multi-device outbox replication for cross-machine developer continuity. |
| **Render** | **Backend Cloud Hosting** | Cloud host for the production FastAPI control plane backend, WebSocket hub, and background task orchestrators. |
| **Vercel** | **Edge Web Hosting** | Global edge CDN hosting the React 19 + TypeScript Control Room web application. |
| **Local Workstation** | **Isolated Execution Sandboxes** | Runs developer CLI processes (Claude Code, Gemini CLI, Ollama/Qwen, Cline, Goose) inside isolated Git worktrees and Docker sandboxes (`cap_drop=["ALL"]`). |

---

## 6. Multi-Agent Fleet Status & Availability

AI Supervisor truth-reports the operational readiness of every agent adapter. An adapter existing in code does not mean it is marked live:

| Agent Runtime | Adapter ID | Supported Interface | Runtime Status Requirements | Untrusted Boundary |
|---|---|---|---|---|
| **Anthropic Claude Code** | `claude_code` | CLI Process (`asyncio`) | `claude` executable in local `PATH` | Isolated Git Worktree |
| **OpenAI Codex** | `codex` | CLI Process (`asyncio`) | `codex` binary or fallback mock | Isolated Git Worktree |
| **Google Gemini CLI** | `gemini` | Gemini CLI / API | `gemini` executable or `GEMINI_API_KEY` | Isolated Git Worktree |
| **Qwen Local Runtime** | `qwen` | Ollama / vLLM / CLI | Local Ollama endpoint or `qwen` CLI | Isolated Git Worktree |
| **OpenCode** | `opencode` | OpenCode CLI Process | `opencode` binary in `PATH` | Isolated Git Worktree |
| **Moonshot Kimi** | `kimi` | Kimi CLI Process | `kimi` executable or Nebius endpoint | Isolated Git Worktree |
| **Nous Hermes** | `hermes` | Persistent Session CLI | `hermes` binary or DigitalOcean/Nebius | Worktree / Session |
| **Block Goose** | `goose` | Developer CLI Process | `goose` executable in local `PATH` | Isolated Git Worktree |
| **Cline** | `cline` | CLI / Extension Agent | `cline` binary or node process | Isolated Git Worktree |
| **DigitalOcean Managed**| `digitalocean_managed` | Cloud Agent API | `DIGITALOCEAN_TOKEN` configured | MicroVM Container |

---

## 7. Consistency & Recovery Guarantees

AI Supervisor avoids distributed transaction hazards through clear persistence boundaries and fail-fast semantics:

1. **No Silent Fallback**: If FalkorDB disconnects mid-mission, operations immediately raise `FalkorDBUnavailableError` (HTTP 503). The system never silently pretends graph-dependent decisions or verifications succeeded.
2. **Replay Idempotency**: All graph writes use parameterized Cypher `MERGE` on unique IDs (`id`). Replaying the mission event stream or re-evaluating the task DAG produces zero duplicate nodes or relationships.
3. **Restart Durability**: All execution attempts, failure events, decisions, and evidence persist in the FalkorDB Docker volume. Upon cold process restart, the supervisor queries FalkorDB to seamlessly restore in-flight context.

---

## 8. Production Deployment

```
                      PRODUCTION TOPOLOGY
                      
     ┌──────────────────────────────────────────────────┐
     │                FRONTEND (Vercel)                 │
     │        https://ai-supervisior.vercel.app/        │
     │             React 19 + TypeScript + Vite         │
     │           [FalkorDB Graph Inspector UI]          │
     └────────────────────────┬─────────────────────────┘
                              │ HTTPS / WSS
                              ▼
     ┌──────────────────────────────────────────────────┐
     │                BACKEND (Render)                  │
     │            FastAPI Control Plane Engine          │
     │     EventBus · Dynamic Router · Watchdogs · Sync │
     └──────────────┬───────────────────┬───────────────┘
                    │                   │
         REST / WSS │                   │ Parameterized Cypher Queries
                    ▼                   ▼
     ┌────────────────────────┐  ┌────────────────────────────────────┐
     │  LOCAL WORKSTATIONS    │  │    FALKORDB GRAPH MEMORY LAYER     │
     │  • Developer Machine   │  │  • Graph Name: ai_supervisor_memory│
     │  • Git Worktrees       │  │  • High Performance Graph Engine  │
     │  • Local CLI Agents    │  │  • Causal Failure Tracing          │
     │  • Docker Sandboxes    │  │  • Evidence Proof Lineage          │
     │  • Offline Outbox Sync │  │  • Docker Volume Persistence       │
     └────────────────────────┘  └────────────────────────────────────┘
```

---

## 9. Quickstart & Local Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Docker and Docker Compose (for FalkorDB)
- Git 2.30+

### 1. Clone & Configure Environment
```bash
git clone https://github.com/M0izz/AI-Supervisior.git
cd AI-Supervisior

# Copy configuration template
cp .env.example .env
```

### 2. Start FalkorDB Container
```bash
docker compose up -d
```
Verify FalkorDB connectivity:
```bash
python -c "from storage.graph.client import FalkorDBClient; print(FalkorDBClient().check_health())"
```

### 3. Launch Backend (FastAPI)
```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server on port 8000
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify backend health and FalkorDB graph memory endpoints:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/graph/health
```

### 4. Launch Frontend (Control Room)
```bash
cd apps/control-room
npm install
npm run build    # Compiles production distribution to dist/
npm run dev      # Launches local dev server on http://localhost:5173
```
Open [http://localhost:5173](http://localhost:5173) in your browser (or use the [Live Hosted Demo](https://ai-supervisior.vercel.app/)).

### 5. Run the End-to-End Real Mission Demonstration
```bash
python demo_falkordb_workflow.py
```
This script executes a full real mission:
- Enforces the plan approval gate.
- Persists DAG dependencies in FalkorDB.
- Executes Attempt 1, simulates a failure, and records the causal `FAILS_WITH` relationship.
- Queries failure history to record a recovery `Decision` (`RESPONDS_TO` and `SELECTS`).
- Dispatches Attempt 2, verifies empirical evidence, and links `Verification EVALUATES_EXECUTION`.
- Simulates an application crash/restart, confirming 100% graph memory preservation.

---

## 10. Verified Test Suite Results

Test numbers are verified directly against the repository execution:

### FalkorDB Integration Test Suite (15 / 15 Passed — 100%)
```bash
python -m pytest tests/test_graph_driven_decisions.py tests/test_falkordb_consistency_recovery.py tests/test_falkordb_graph_memory.py -v
```
```
tests/test_graph_driven_decisions.py::test_unverified_prerequisite_blocks_task_dispatch PASSED
tests/test_graph_driven_decisions.py::test_prior_failure_history_guides_recovery_routing PASSED
tests/test_falkordb_consistency_recovery.py::test_replay_idempotency_does_not_duplicate_nodes_or_edges PASSED
tests/test_falkordb_consistency_recovery.py::test_mid_mission_disconnection_raises_falkordb_unavailable_error PASSED
tests/test_falkordb_consistency_recovery.py::test_state_recovery_across_application_restart PASSED
tests/test_falkordb_graph_memory.py::test_connection_and_health_reporting PASSED
tests/test_falkordb_graph_memory.py::test_idempotent_creation PASSED
tests/test_falkordb_graph_memory.py::test_task_dependency_traversal PASSED
tests/test_falkordb_graph_memory.py::test_failure_retrieval_for_retry PASSED
tests/test_falkordb_graph_memory.py::test_handoff_context_retrieval PASSED
tests/test_falkordb_graph_memory.py::test_preservation_of_distinct_attempts PASSED
tests/test_falkordb_graph_memory.py::test_verification_evidence_traceability PASSED
tests/test_falkordb_graph_memory.py::test_unavailable_falkordb_fails_clearly PASSED
tests/test_falkordb_graph_memory.py::test_persistence_across_restart PASSED
tests/test_falkordb_graph_memory.py::test_plan_approval_gate_enforced_with_graph PASSED

======================== 15 passed in 8.13s ========================
```

### Full Repository Test Suite
```bash
python -m pytest -v
# 348 passed across all core, absence, fleet, watchdog, and desktop integration suites.
```

### Frontend Build & Lint Verification
- **Build**: `tsc -b && vite build` — 1,927 modules transformed, production distribution compiled in `apps/control-room/dist/` in 1.28s with zero errors.
- **Lint**: `oxlint` — 28 files evaluated: **0 errors**.

---

## 11. Key REST Endpoints for FalkorDB Graph Memory

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/graph/health` | Diagnostic report of FalkorDB connectivity, latency, and node/edge count. |
| `GET` | `/api/missions/{id}/graph` | Complete property graph subgraph (nodes and edges) for a mission. |
| `GET` | `/api/missions/{id}/tasks/{id}/graph-context` | Dependency-aware context, prior attempts, and unverified prerequisite warnings. |
| `GET` | `/api/missions/{id}/failures` | Prior causal failure history and error signatures traversed from FalkorDB. |
| `GET` | `/api/missions/{id}/decisions` | Supervisory decision lineage path (`Decision -> RESPONDS_TO -> Event`). |
| `GET` | `/api/missions/{id}/tasks/{id}/verification-trace` | Traceability from Verification decision directly to empirical Evidence items. |

---

## 12. Documentation Index

- [Live Web App](https://ai-supervisior.vercel.app/) — Hosted production Control Room cockpit on Vercel.
- [FalkorDB Graph Integration Specification](docs/FALKORDB_GRAPH_INTEGRATION.md) — Complete Cypher schema, consistency guarantees, and execution diagrams.
- [Architecture Guide](docs/architecture.md) — Comprehensive technical design, state machines, and data flows.
- [Cloud Sync Architecture](docs/sync-architecture.md) — Local-first synchronization engine design.
- [Multi-Device Continuity](docs/multi-device.md) — Workstation pairing and outbox replication guide.
- [Absence Mode Specification](docs/absence-mode.md) — Bounded autonomy policy, approval timeouts, and safety invariants.
- [Docker Execution Hardening](docs/docker-execution.md) — Sandbox security profiles and privilege isolation.
- [Reliability & Adversarial Report](docs/reliability-report.md) — 24-scenario adversarial failure test matrix.

---

## 13. Security & Safety Principles

1. **Zero Implicit Approval**: High-risk actions require explicit human approval; unapproved missions are blocked at the plan gate.
2. **Credential Sanitization**: Bearer tokens, API keys, passwords, and private URLs are scrubbed from tool execution traces, event payloads, and UI streams before emission.
3. **Worktree & Container Isolation**: Agent code executes inside isolated Git worktrees and single-host Docker sandboxes (`cap_drop=["ALL"]`, `network_mode="none"`, memory limits `512MB`).
4. **Append-Oriented Event Stream**: All actions, interventions, and watchdog triggers are recorded in an auditable event stream for forensic playback.
5. **Empirical Verification Invariant**: Claimed complete is never verified complete without objective test and diff evidence.

---

## 14. License

This project is open-source software licensed under the [MIT License](LICENSE).
