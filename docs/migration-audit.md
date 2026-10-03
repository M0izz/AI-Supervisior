# AI Supervisor — Architectural Migration Audit & Technical Assessment

> **Auditor**: Lead Systems Architect & Product Engineering  
> **Date**: October 2026  
> **Baseline**: Hackathon Implementation (`M0izz/AI-Supervisior`) vs Commercial Product Spec (`docs/product-spec.md`)

---

## 1. What from the Existing Codebase Can Be Directly Reused?

The existing AI Supervisor codebase contains robust architectural assets that directly align with the commercial product vision:

1. **Event Bus & Event Architecture (`core/events/bus.py`)**:
   - Asynchronous and synchronous publish/subscribe system.
   - Decouples all agents, watchdogs, storage engines, and UI broadcasters.
   - Immutable event structures with typed severity and payload dictionaries.
   - **Reuse Score**: 95% (needs only Work Protocol v1 typing refinement).

2. **Layer A Deterministic Watchdogs (`supervisor/rules.py`)**:
   - Signature normalization (`normalize_signature`) regexes stripping memory addresses (`0xADDR`) and line numbers to identify true identical failures across runs.
   - Consecutive loop detection ($\ge 3$ repeated identical failure signatures).
   - Scope violation guard checking file writes against task-declared file whitelists and protected system paths (`.git`, `.env`, `etc`).
   - Dangerous command pattern matching (`rm -rf`, `DROP TABLE`, format disk).
   - **Reuse Score**: 90% (ready to serve as the core deterministic watchdog in the product).

3. **Task Graph & DAG Resolution (`core/tasks/models.py`, `core/tasks/manager.py`)**:
   - Dependency-aware DAG resolution (`get_ready_tasks()`) based on topological task completion.
   - In-progress, completed, failed, blocked, and verified task state tracking.
   - React Flow node/edge generation for UI visualization.
   - **Reuse Score**: 90% (needs integration with SQLite persistence and worktree scope).

4. **Mission Lifecycle State Machine (`core/missions/models.py`, `supervisor/state_machine.py`)**:
   - Validated state transitions: `CREATED` $\to$ `PLANNING` $\to$ `RUNNING` $\to$ `PAUSED` $\to$ `INVESTIGATING` $\to$ `RECOVERING` $\to$ `VERIFYING` $\to$ `COMPLETED`.
   - Clear failure and approval branches: `FAILED`, `BLOCKED`, `WAITING_APPROVAL`, `CANCELLED`.
   - **Reuse Score**: 95%.

5. **Empirical Memory Store & Provenance (`memory/provenance.py`, `memory/store.py`, `memory/retrieval.py`)**:
   - Strict provenance status enum: `OBSERVED`, `INFERRED`, `DECIDED`, `VERIFIED`, `REJECTED`, `STALE`.
   - Rejection tracking: Permanently records disproven hypotheses so future runs do not repeat failed approaches.
   - `ContextPackager`: Dynamically bundles mission goals, task boundaries, verified facts, and rejected approaches into a compact prompt without dumping raw conversation logs.
   - **Reuse Score**: 85% (needs SQLite backing and multi-agent attribution).

6. **Human Safety Approval Engine (`supervisor/approvals.py`, `core/state/models.py`)**:
   - Asynchronous approval request lifecycle with explicit resolution actions (`APPROVE_ONCE`, `DENY`, `CANCEL`, `TAKE_CONTROL`).
   - Strict invariant: Timeouts automatically transition requests to `DENIED`. Absence of response never grants approval.
   - **Reuse Score**: 95%.

7. **Sandbox Tool Security & Credential Redaction (`tools/base.py`)**:
   - `BaseTool.sanitize_arguments()`: Automatic scrubbing of API keys (`sk-`, `ghp_`, `Bearer`), tokens, and private URLs before events are broadcast or stored.
   - **Reuse Score**: 95%.

8. **Telemetry & Audit Timeline Reconstruction (`supervisor/telemetry.py`, `supervisor/timeline.py`)**:
   - Four-quadrant metrics tracker (Execution, Reliability, Risk, CI).
   - Narrative timeline builder converting raw event streams into causal human-readable story items.
   - **Reuse Score**: 90%.

---

## 2. What Must Be Refactored?

1. **Internal Agent Classes $\to$ External Agent Adapters**:
   - *Current*: `WorkerAgent`, `PlannerAgent`, `ReviewerAgent`, `VerifierAgent` (`agents/`) are internal Python classes executing local Python tools.
   - *Refactoring*: Transform into the `AgentAdapter` contract (`adapters/base.py`). External agents (Claude Code, OpenAI Codex, Gemini CLI) run out-of-process via their official SDKs or CLI processes. The adapter maps their native tool calls and stdout/stderr into standard Work Protocol events.

2. **In-Memory State $\to$ Local-First SQLite Persistence**:
   - *Current*: `AppState` (`apps/api/state.py`) keeps missions, tasks, memory, agents, and approvals in memory dictionaries. A single JSONL file (`supervisor_events.jsonl`) logs events.
   - *Refactoring*: Introduce an embedded SQLite database (`supervisor.db`) with WAL mode. `MissionManager`, `TaskManager`, `AgentRegistry`, `MemoryStore`, and `EventStore` must read and write to SQLite so state survives application restarts.

3. **Direct Workspace Modification $\to$ Git Worktree Isolation**:
   - *Current*: `WorkerAgent` directly edits files in a shared folder (`./demo/sample-project`).
   - *Refactoring*: Introduce `WorkspaceManager` and `GitWorktreeManager` (`execution/worktree.py`). Each agent executes in an isolated Git worktree (`.supervisor/worktrees/{agent_id}-{task_id}`) on an isolated branch. Changes are merged into the mission branch only after independent verification.

4. **Hardcoded Model Provider $\to$ Pluggable Supervisory Reasoner**:
   - *Current*: `SupervisoryReasoner` (`supervisor/reasoning.py`) explicitly calls `NebiusNemotronProvider` or `MockReasoningProvider`.
   - *Refactoring*: Refactor into a provider-agnostic cognitive layer that can invoke local models (Qwen via Ollama/vLLM), Claude, or OpenAI for supervisory analysis, with automatic fallback to deterministic rules.

---

## 3. What Is Missing?

1. **Formal Work Protocol Specification (`core/protocol/`)**:
   - Versioned schema (`work_protocol.v1`) defining standardized actions (`read_file`, `write_file`, `edit_lines`, `execute_command`, `run_tests`, `git_commit`, `delegate_task`, `report_completion`) and events.
2. **Production Agent Adapters (`adapters/`)**:
   - `ClaudeCodeAdapter` (Anthropic Claude Agent SDK / Claude Code CLI).
   - `CodexAdapter` (OpenAI Codex / Agents SDK).
   - `GeminiAdapter` (Google Gemini CLI / SDK).
   - `QwenLocalAdapter` (Local Ollama / vLLM API).
3. **Automated Handoff Engine (`core/handoff/`)**:
   - Dedicated subsystem that packages failure signatures, attempted approaches, diffs, and constraints into a standardized Handoff Package when switching agents.
4. **Dynamic Capability Router (`core/routing/`)**:
   - Transparent scoring engine matching tasks to agents based on capability tags, cost, latency, context size, and past success rates.
5. **Desktop Shell & Floating HUD (`apps/desktop/`)**:
   - Electron wrapper managing the local FastAPI background process, providing an ambient always-on-top HUD, system tray integration, and OS notifications.
6. **Absence Mode Policy Engine (`core/policies/absence.py`)**:
   - Automated rule evaluator for unattended execution with strict pause conditions on destructive operations.

---

## 4. What Architecture Conflicts Exist?

| Conflict | Current Hackathon Design | Commercial Product Target | Resolution Strategy |
| :--- | :--- | :--- | :--- |
| **Workspace Mutability** | All agents touch `./demo/sample-project` directly. | Concurrent agents must not collide. | Introduce Git worktrees per agent task; merge only upon verification. |
| **Agent Execution Authority** | Agent executes internal Python tool methods. | Agents are external runtimes (CLI/SDK) with their own tools. | Adapter translates external tool calls into Work Protocol events before execution. |
| **Persistence Boundary** | Python process memory + flat JSONL file. | Desktop app requires resilient local-first persistence. | SQLite with WAL mode becomes authoritative storage; in-memory cache for speed. |
| **Verification Authority** | Verifier was an internal agent running pytest. | Independent verification must be a first-class subsystem. | `VerifierEngine` runs out-of-process checks (tests, linters, diffs) in a clean worktree. |
| **Configuration** | Environment variables in `.env`. | Desktop app configuration managed via UI/local DB. | SQLite stores agent configurations; `.env` remains for development fallback. |

---

## 5. What Is Already Production-Quality?

* **Deterministic Watchdog Engine (`supervisor/rules.py`)**: High quality, well-tested, robust signature normalization, catches real loops without false positives.
* **Approval State Machine (`supervisor/approvals.py`)**: Proper locking, explicit status transitions, automatic timeout default to `DENIED`.
* **Provenance Data Model (`memory/provenance.py`)**: Clean 6-tuple model for knowledge items.
* **Adversarial Test Suite (`tests/test_phase8_reliability_adversarial.py`)**: 24 rigorous test cases verifying infinite loops, budget overruns, scope violations, OOMs, and timeouts.
* **FastAPI Backend Structure (`apps/api/`)**: Clean REST and WebSocket endpoints for mission control, telemetry, and live event streaming.
* **Control Room Frontend (`apps/control-room/`)**: React 19 + TypeScript dashboard with functional views for missions, agents, memory, approvals, and events.

---

## 6. What Is Hackathon / Demo-Only?

* **`demo/sample-project`**: Hardcoded sample project designed specifically for the CSV parser BOM scenario.
* **`demo/reset.py`**: Hardcoded reset script for `parser.py` and `supervisor_events.jsonl`.
* **`integrations/nebius/`**: Cloud-specific Nebius AI Studio adapter. Valuable as an optional reasoning provider, but must not be hardcoded as the sole provider.
* **`integrations/jenkins/mock.py`**: Hardcoded Jenkins build numbers (#481, #482). Useful for deterministic simulation, but product must prioritize local test runners.

---

## 7. What Should Become the Reusable Supervisor Core?

The clean, modular core will reside under `core/`:

```text
core/
├── protocol/         # Work Protocol v1 schemas and event models
├── missions/         # Mission lifecycle, constraints, and metrics
├── tasks/            # Task DAG, dependency resolution, and state
├── supervisor/       # Watchdogs (Layer A) and cognitive reasoning (Layer B)
├── routing/          # Capability registry and suitability scoring
├── memory/           # Project memory, provenance, and context packager
├── handoff/          # Cross-agent handoff packaging and second opinions
├── verification/     # Independent out-of-process verification engine
├── policies/         # Permission boundaries and Absence Mode policies
├── approvals/        # Human safety gate and operator intervention
└── events/           # EventBus and append-only event store
```

---

## 8. What Should Remain Optional / Integration-Specific?

* **Nebius Cloud Reasoning (`integrations/nebius/`)**: Kept as an optional cognitive reasoning backend when `NEBIUS_API_KEY` is provided.
* **Remote Jenkins CI (`integrations/jenkins/`)**: Kept as an optional enterprise CI verification gate when `JENKINS_URL` is configured.
* **Docker Container Execution (`execution/docker.py`)**: Kept as an optional sandbox isolation backend when Docker daemon is available.

---

## 9. What Should Be Deleted?

* **No immediate file deletions are required.**
* Hackathon demonstration assets (`demo/sample-project`, `demo/scenarios/`) remain isolated under `demo/` and serve as reference end-to-end regression tests.
* Unused legacy compatibility aliases will be deprecated gracefully rather than breaking existing tests.

---

## 10. What Is the Safest Phase 1 Implementation?

To build the foundation without breaking a single existing test or demo:

1. **Create `core/protocol/`**: Define `WorkProtocolEvent` and `TaskDispatchPackage` Pydantic models.
2. **Create `storage/sqlite/`**: Implement SQLite database connection, table schemas (DDL), and async repositories for missions, tasks, agents, events, and memory.
3. **Create `execution/worktree.py`**: Implement safe Git worktree isolation with automatic fallback to workspace jail if Git is uninitialized.
4. **Maintain Complete Backward Compatibility**: Ensure existing `EventBus`, `SupervisorEngine`, `WorkerAgent`, and API endpoints continue operating seamlessly while reading and writing through the new persistence layer.
5. **Verify with Comprehensive Tests**: Add unit tests for Work Protocol validation, SQLite repositories, and worktree isolation.
