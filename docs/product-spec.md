# AI Supervisor — Technical Product Specification & Architecture (v1.0)

> *"AI agents are becoming abundant. The scarce resource is reliable coordination."*

---

## 1. Executive Summary & Core Positioning

### 1.1 The Product
**AI Supervisor** is an authoritative, local-first desktop control plane that unifies, orchestrates, supervises, and independently verifies autonomous AI engineering agents (Claude Code, OpenAI Codex, Google Gemini CLI, Qwen Local, Kimi, Cursor, and custom tools).

The user does not select models for individual files or switch between disconnected agent chat tabs. The user simply specifies an objective:

```text
"Build this."
```

AI Supervisor autonomously:
1. **Decomposes** the mission into a dependency-aware Task DAG.
2. **Routes** each task to the most suitable connected agent based on capability, cost, latency, context window, and historical performance.
3. **Isolates** concurrent agents within independent Git worktrees to prevent workspace collisions.
4. **Enforces** fine-grained permission boundaries (Read, Write, Execute, Network, Delete, Deploy).
5. **Observes** all agent actions through a unified **Work Protocol**.
6. **Intervenes** upon detecting repeated errors, stalled progress, scope drift, or safety violations.
7. **Coordinates Handoffs** by extracting failure signatures, generating empirical recovery context, and switching agents or seeking second opinions.
8. **Independently Verifies** completion using empirical ground truth (unit tests, linters, typecheckers, security scans, git diff audits) before accepting any task.

```text
                    USER / DEVELOPER
                           │
                     "Build this"
                           ▼
              ┌─────────────────────────┐
              │      AI SUPERVISOR      │
              │                         │
              │  Mission Control & DAG  │
              │  Dynamic Agent Router   │
              │  Shared Project Memory  │
              │  Dual-Layer Supervisor  │
              │  Independent Verifier   │
              │  Permission & Gate      │
              └────────────┬────────────┘
                           │ Work Protocol (Events & Actions)
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Claude Code  │    │ OpenAI Codex │    │  Gemini CLI  │
│ (Refactor &  │    │  (Backend &  │    │  (Frontend & │
│  Diagnosis)  │    │ Logic Impl)  │    │ Documentation│
└──────────────┘    └──────────────┘    └──────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Qwen Local  │    │  Kimi / Open │    │ Cursor / IDE │
│  (Private &  │    │    Code      │    │  Workspace   │
│   Fast-Edit) │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

### 1.2 What We Are NOT Building
* ❌ **Not a chatbot or generic AI wrapper**: No conversation threads for general banter.
* ❌ **Not a 15-tab agent switcher**: We do not force the user to babysit separate agent windows.
* ❌ **Not a prompt marketplace**: We orchestrate real software execution, not prompt templates.
* ❌ **Not an IDE replacement**: We act as the background supervisory control plane alongside VS Code, Cursor, or JetBrains.
* ❌ **Not a cloud SaaS dependency**: The core runs locally on developer hardware with full privacy and low latency.

---

## 2. The Core Foundation: Work Protocol Specification

To prevent every AI provider from becoming an unmaintainable special case, all external agent integrations normalize their input, output, events, and tool calls into the **Work Protocol**.

```text
Claude Agent SDK ──┐
Codex SDK / CLI ───┤
Gemini CLI ────────┤
Qwen Local ────────┼──► [ WORK PROTOCOL NORMALIZER ] ──► [ SUPERVISOR CORE ]
Kimi Process ──────┤
Cursor / MCP ──────┘
```

### 2.1 Work Protocol Event Schema (`work_protocol.v1.json`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "WorkProtocolEvent",
  "type": "object",
  "required": [
    "event_id",
    "mission_id",
    "task_id",
    "agent_id",
    "provider",
    "timestamp",
    "event_type",
    "action",
    "payload"
  ],
  "properties": {
    "event_id": { "type": "string", "pattern": "^evt_[a-z0-9]{12}$" },
    "mission_id": { "type": "string", "pattern": "^msn_[a-z0-9]{8}$" },
    "task_id": { "type": "string" },
    "agent_id": { "type": "string" },
    "provider": { 
      "type": "string", 
      "enum": ["claude-code", "openai-codex", "google-gemini", "qwen-local", "kimi-code", "cursor", "antigravity", "generic"] 
    },
    "timestamp": { "type": "string", "format": "date-time" },
    "event_type": {
      "type": "string",
      "enum": [
        "agent.started",
        "agent.action.proposed",
        "agent.action.executed",
        "agent.tool_called",
        "agent.file_changed",
        "agent.test_executed",
        "agent.stuck",
        "agent.paused",
        "agent.switched",
        "agent.completed_claim",
        "agent.error"
      ]
    },
    "action": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": {
          "type": "string",
          "enum": [
            "read_file",
            "write_file",
            "edit_lines",
            "execute_command",
            "run_tests",
            "git_commit",
            "git_diff",
            "delegate_task",
            "ask_human",
            "report_completion"
          ]
        },
        "target": { "type": "string" },
        "command": { "type": "string" },
        "diff": { "type": "string" },
        "exit_code": { "type": "integer" }
      }
    },
    "telemetry": {
      "type": "object",
      "properties": {
        "tokens_input": { "type": "integer" },
        "tokens_output": { "type": "integer" },
        "cost_usd": { "type": "number" },
        "duration_ms": { "type": "integer" }
      }
    },
    "payload": { "type": "object" }
  }
}
```

### 2.2 Standardized Task Dispatch Schema

When dispatching work to any agent, the Supervisor emits a standardized **Task Dispatch Package**:

```json
{
  "task_id": "task_auth_002",
  "mission_id": "msn_b8a910f2",
  "objective": "Implement JWT verification middleware with RSA256 signature check",
  "scope": {
    "allowed_files": ["src/middleware/auth.ts", "tests/auth.test.ts"],
    "forbidden_files": ["config/secrets.env", "src/db/schema.prisma"],
    "allowed_tools": ["read_file", "write_file", "run_tests"]
  },
  "constraints": [
    "Do not modify database schema",
    "Must pass existing unit tests in tests/auth.test.ts",
    "Budget ceiling: 30,000 tokens or $1.50"
  ],
  "workspace_path": "/Users/moiz/projects/myapp/.supervisor/worktrees/claude",
  "context": {
    "verified_facts": [
      {
        "fact": "Public signing key is loaded from JWKS endpoint in auth_config.ts",
        "provenance": "codex_inspection",
        "status": "VERIFIED"
      }
    ],
    "rejected_approaches": [
      {
        "approach": "Parsing token with raw base64 string slice",
        "reason": "Fails RFC 7519 validation and vulnerable to signature stripping"
      }
    ]
  }
}
```

---

## 3. Layer 1 — The Agent Adapter Subsystem

The Adapter layer standardizes diverse external tools into the Work Protocol.

```text
adapters/
├── base.py               # Abstract Base Adapter contract
├── claude/
│   ├── adapter.py        # Anthropic Claude Agent SDK / Claude Code CLI
│   └── normalizer.py     # Maps Claude tool calls -> Work Protocol
├── codex/
│   ├── adapter.py        # OpenAI Codex SDK / Agents API
│   └── normalizer.py     # Maps tool_calls -> Work Protocol
├── gemini/
│   ├── adapter.py        # Google Gemini CLI / SDK
│   └── normalizer.py     # Maps Gemini function calls -> Work Protocol
├── qwen/
│   ├── adapter.py        # Ollama / vLLM / llama.cpp local endpoint
│   └── normalizer.py     # Maps local JSON completions -> Work Protocol
├── kimi/
│   ├── adapter.py        # Moonshot Kimi API / Process
│   └── normalizer.py
├── cursor/
│   ├── adapter.py        # MCP Server / IDE bridge
│   └── normalizer.py
└── generic/
    ├── process_adapter.py # Any CLI process running via stdio/pty
    └── mcp_adapter.py     # Any standard Model Context Protocol server
```

### 3.1 Adapter Interface Contract

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, Optional
from core.protocol import WorkProtocolEvent, TaskDispatchPackage, AgentStatus, AgentCapabilities

class AgentAdapter(ABC):
    """Universal interface for all external AI agent backends."""

    @abstractmethod
    async def connect(self, config: Dict[str, Any]) -> bool:
        """Validate agent executable, SDK credentials, or local endpoint."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Cleanly terminate agent process or SDK session."""
        pass

    @abstractmethod
    async def start_task(self, package: TaskDispatchPackage) -> bool:
        """Dispatch task with bound scope, constraints, and worktree."""
        pass

    @abstractmethod
    async def stream_events(self) -> AsyncIterator[WorkProtocolEvent]:
        """Stream real-time standardized events (tool calls, edits, tests)."""
        pass

    @abstractmethod
    async def pause(self, reason: str) -> bool:
        """Interrupt and pause agent execution immediately."""
        pass

    @abstractmethod
    async def resume(self, recovery_instructions: Optional[str] = None) -> bool:
        """Resume paused agent with optional targeted recovery prompt."""
        pass

    @abstractmethod
    async def abort(self) -> bool:
        """Forcefully terminate active task run."""
        pass

    @abstractmethod
    async def get_status(self) -> AgentStatus:
        """Return IDLE, RUNNING, PAUSED, BUSY, FAILED."""
        pass

    @abstractmethod
    def get_capabilities(self) -> AgentCapabilities:
        """Return static & learned capabilities (refactor, frontend, offline, etc.)."""
        pass
```

### 3.2 Authentication Integrity Principle
* **Zero Password Storage**: AI Supervisor **NEVER** prompts for or stores passwords or session cookies.
* **Provider Authentication**:
  - Anthropic: Official `ANTHROPIC_API_KEY` or system keychain / Claude CLI login.
  - OpenAI: Official `OPENAI_API_KEY` or Codex SDK credentials.
  - Gemini: Google Cloud Application Default Credentials (ADC) or `GEMINI_API_KEY`.
  - Local Models: Direct connection to local loopback (Ollama `http://127.0.0.1:11434`, vLLM, LMStudio).

---

## 4. Layer 2 — The Supervisor Core (The Product Moat)

```text
                     SUPERVISOR CORE
             ┌──────────────────────────────┐
             │       Mission Manager        │
             │   (Objective -> Task DAG)    │
             └──────────────┬───────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Planner    │    │Dynamic Router│    │Shared Memory │
│   Engine     │    │  & Scoring   │    │& Provenance  │
└──────────────┘    └───────┬──────┘    └──────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │       Agent Manager       │
              │ (Worktree Isolation, Git) │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │     Supervisor Engine     │
              │  Layer A: Watchdogs       │
              │  Layer B: Reasoning       │
              └─────────────┬─────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Continuous  │    │ Causal Fault │    │ Independent  │
│  Observation │    │  Diagnosis   │    │  Verifier    │
└──────────────┘    └──────────────┘    └──────────────┘
```

### 4.1 Mission Manager & Task DAG
Translates unstructured high-level human objectives into structured dependencies:

```text
MISSION: "Add Stripe Checkout with Webhook Reconciliation"
│
├── [TASK-001] (Planner) Inspect repository structure & package dependencies
├── [TASK-002] (Codex)   Implement Stripe webhook receiver endpoint (Depends on: 001)
├── [TASK-003] (Claude)  Implement idempotency key table & DB migrations (Depends on: 001)
├── [TASK-004] (Gemini)  Build checkout button & frontend modal UI (Depends on: 001)
├── [TASK-005] (Codex)   Reconcile webhook signature verification (Depends on: 002, 003)
├── [TASK-006] (Qwen)    Security audit on webhook secret handling (Depends on: 005)
└── [TASK-007] (Verifier)Independent end-to-end integration test validation
```

### 4.2 Dynamic Capability Router (Phase 6 Implemented)
The Router is a Supervisor component. Agents do NOT select themselves or influence their own score.
Given a task requirement, the Router evaluates all registered adapters through an Eligibility Gate and scores eligible candidates deterministically:

1. **Eligibility Gate (Hard Constraints)**:
   - **Exclusions**: Evaluates `excluded_agent_ids` (e.g. failing source agent during handoff).
   - **Availability Probe**: Probes `AgentAdapter.check_availability()`. Any non-`AVAILABLE` status marks the candidate ineligible.
   - **Required Capabilities**: Missing even one required capability (`code_execution`, `filesystem_write`, `git`, `test_execution`) makes the candidate ineligible. Historical score cannot override this gate.

2. **Deterministic Additive Scoring**:
   $$\text{Score} = \text{Capability Base (10.0)} + \sum \text{Preferred Bonus (2.0)} + \text{Availability Bonus (2.0)} + \text{Bounded Reliability Score}$$
   Where:
   $$\text{Net Performance} = (\text{Verified Successes} \times 1.5) - (\text{Verification Failures} \times 2.0) - (\text{Handoffs} \times 1.0)$$
   $$\text{Reliability Score} = \text{clamp}(\text{Net Performance}, -10.0, 10.0)$$

3. **Cold-Start Policy**: Agents with zero historical tasks receive a neutral reliability score of `0.0` and remain eligible without penalty.
4. **Deterministic Tie-Breaking**: Breaks ties using total capability count (specialization), fewest historical failures, fewest handoffs, and stable `agent_id` ordering.
5. **Decisions & Persistence**: Outputs `ROUTE`, `NO_ELIGIBLE_AGENT`, or `REQUIRE_REVIEW` with human-readable rationales, persisted to SQLite WAL table `routing_decisions` and streamed via EventBus.

### 4.3 Shared Project Memory with Provenance (Phase 7 Implemented)
To prevent hallucinated context from becoming permanent project dogma, every memory record enforces explicit provenance, immutable audit trails, and strict epistemic verification gates:

$$\text{Memory Record} = \langle \text{Content}, \text{Type}, \text{Status}, \text{Confidence}, \text{Provenance}, \text{Scope} \rangle$$

* **Core Invariant**: Agents are ephemeral and replaceable; project knowledge is durable. Agent claims remain `UNVERIFIED` until corroborated by independent verification or ground-truth execution.
* **Epistemic Status Hierarchy**:
  - `VERIFIED`: Proven by independent test suites, static analysis, or compiler verification (Trust score: 5.0).
  - `DECIDED`: Architectural or policy choices confirmed by operator or supervisor (Trust score: 4.0).
  - `OBSERVED`: Raw empirical evidence, compiler error outputs, failing assertions (Trust score: 3.0).
  - `INFERRED`: Hypotheses or conclusions drawn by an agent during analysis (Trust score: 2.0).
  - `UNVERIFIED`: Raw agent claims awaiting independent proof (Trust score: 1.0).
  - `REJECTED`: Disproven hypotheses stored permanently so **no subsequent agent repeats them** (Trust score: 0.5).
  - `STALE`: Outdated facts superseded by newer state.

* **Typed Knowledge Classification**:
  - `FACT`: Empirical statements about the codebase, dependencies, or environment.
  - `DECISION`: Architectural choices, design directions, framework selections.
  - `CONSTRAINT`: Environmental, API, performance, or security constraints.
  - `FAILURE`: Recorded failure signatures, stack traces, and error outputs.
  - `REJECTED_APPROACH`: Disproven tactics, failed strategies, and antipatterns (`DO NOT REPEAT`).
  - `DISCOVERY`: New findings during agent execution.
  - `TASK_CONTEXT`: Context specific to a mission or task execution.
  - `VERIFICATION_RESULT`: Audit results from the Independent Verification Engine.

* **Deterministic Retrieval & Bounded Packaging**:
  - Keyword & scope matching without opaque vector embeddings.
  - Trust hierarchy sorting: verified ground truth prioritized over unverified claims.
  - Context packaging bounds token budgets and explicitly structures `DO NOT REPEAT` sections into handoff contexts.
  - Secret redaction sanitizes API tokens, SSH keys, and bearer tokens before storage.

### 4.4 Automated Agent Handoff & Second Opinions
When an agent is stuck (e.g. Claude fails 3 times on an encoding bug), the Supervisor halts execution and extracts a **Standardized Handoff Package**:

```json
{
  "handoff_id": "hnd_90f23a11",
  "original_agent": "claude-code",
  "target_agent": "openai-codex",
  "reason": "REPEATED_TEST_FAILURE_THRESHOLD (3 attempts)",
  "objective": "Fix CSV parser BOM encoding handling",
  "attempted_strategies": [
    "Regex strip on string content: re.sub(r'^\\ufeff', '', text)",
    "Encoding parameter utf-8-sig on open()"
  ],
  "failure_signature": "AssertionError: Expected 'user_id' header but found '\\ufeffuser_id'",
  "do_not_repeat": [
    "Do not attempt regex replacement on decoded string",
    "Do not modify database schema in db/schema.sql"
  ],
  "active_worktree_diff": "diff --git a/src/parser.py b/src/parser.py..."
}
```

### 4.5 Independent Verification Engine (Anti-Hallucination Gate)
The foundational principle: **Agent completion $\neq$ verified completion.**

When an agent signals completion:
```text
Agent: "I have completed the authentication feature and all tests pass."
Supervisor: "Prove it."
```

The Verifier executes an independent, out-of-process validation pass:
1. **Isolated Build**: Fresh compilation and test run in a clean worktree.
2. **Deterministic Test Execution**: `pytest`, `npm test`, `cargo test`, `go test`.
3. **Scope & Diff Audit**: `git diff main...HEAD` checked against declared file whitelist.
4. **Static Lint & Typecheck**: Zero new type errors or lint regressions allowed.
5. **Security Scan**: Secrets scan (`git-secrets`, regex scanner) preventing committed keys.

Only when all 5 checks pass does the task transition to `VERIFIED`.

---

## 5. Security & Isolation Architecture

### 5.1 Fine-Grained Permission Matrix
Every mission is governed by a strict capability policy:

| Permission | Default | Description |
| :--- | :--- | :--- |
| `READ` | `true` | Read files within project repository. |
| `WRITE` | `true` | Modify files matching task scope whitelist. |
| `EXECUTE` | `true` | Execute whitelisted build, test, and lint commands. |
| `NETWORK` | `false` | Access external Internet (disabled by default in sandboxes). |
| `GIT` | `true` | Create branches, commit to agent-specific worktree. |
| `DELETE` | `false` | Remove existing files (requires explicit human approval). |
| `DEPLOY` | `false` | Push to production or execute release scripts (requires human approval). |
| `SECRETS` | `false` | Read environment secrets or `.env` files (strictly blocked). |

### 5.2 Isolated Git Worktrees
To allow concurrent agents to work safely without corrupting each other's workspaces:

```text
/Users/moiz/projects/myapp/                  [Main Working Tree - Operator]
└── .supervisor/
    └── worktrees/
        ├── claude-msn_001-task_002/         [Isolated Worktree A]
        ├── codex-msn_001-task_003/          [Isolated Worktree B]
        ├── gemini-msn_001-task_004/         [Isolated Worktree C]
        └── verifier-staging/                [Clean Validation Staging]
```

* Each agent operates in its own worktree on an isolated branch: `supervisor/{mission_id}/{agent_id}`.
* When tasks are verified, the Supervisor cleanly rebases and merges validated commits into the mission branch.
* If an agent fails or acts maliciously, its worktree is discarded with zero damage to the operator's working files.

---

## 6. The Desktop UX: Cockpit & Always-On Floating HUD

### 6.1 Form Factor
* **Primary Shell**: Local-first Desktop Application built with **Electron + React 19 + TypeScript** (with future migration path to **Tauri + Rust**).
* **Dual-Surface Interface**:
  1. **Main Cockpit Window**: Full overview (Mission graph, agent fleet, memory browser, permission rules, historical audits).
  2. **Floating Supervisor HUD**: Compact, always-on-top, ambient status widget (collapsible, lives in corner of screen or system tray).

### 6.2 Ambient Floating HUD Specification

```text
┌───────────────────────────────────────────────┐
│ ● AI SUPERVISOR                           ─ □ │
├───────────────────────────────────────────────┤
│ Mission: Build Stripe Checkout Integration    │
│                                               │
│ ● Claude   [Backend]     RUNNING  (2.4m, $0.12)│
│ ● Gemini   [Frontend]    RUNNING  (1.1m, $0.04)│
│ ● Qwen     [Security]    WAITING  (Queued)     │
│                                               │
│ ───────────────────────────────────────────── │
│ Supervisor Notice:                            │
│ ⚠ Claude failed test 3 times (Encoding Error) │
│ Supervisor paused Claude. Delegated to Codex. │
│                                               │
│ [ Review Handoff ]      [ Dismiss / Continue ] │
└───────────────────────────────────────────────┘
```

* **Zero-Nag Policy**: When tasks proceed normally within parameters, the HUD remains silent.
* **Notification Taxonomy**:
  - `INFO`: Task started, agent swapped, milestone achieved.
  - `WARNING`: Anomaly detected, loop detected, iteration budget approaching 80%.
  - `APPROVAL`: Agent requested destructive action (delete file, modify config).
  - `CRITICAL`: Scope violation blocked, security credential exfiltration attempt caught.
  - `COMPLETE`: Mission independently verified and ready for review.

### 6.3 Absence Mode ("I'm going to sleep. Finish this.")

When the operator engages **Absence Mode**:

```text
ABSENCE MODE CONFIGURATION
─────────────────────────────────────────────
Mission: "Migrate database to PostgreSQL and fix all broken tests"

Auto-Approved:
  ✓ Edit files within src/ and tests/
  ✓ Run tests and linters
  ✓ Commit to agent worktrees
  ✓ Swap agents on repeated failures
  ✓ Spend up to: $15.00 total budget

Strict Pause Conditions (Halts & Queues for Morning Review):
  ⚠ File deletion requests
  ⚠ Modifying infrastructure files (.github/workflows, docker-compose.yml)
  ⚠ 3 consecutive unresolvable test failures
  ⚠ Total mission cost reaches $15.00

Morning Summary Report:
  [ Generated in Project Memory with full diff audit & JUnit proofs ]
```

---

## 7. Local-First Database Architecture (SQLite Schema)

All state is stored locally in an embedded SQLite database (`supervisor.db`) using WAL mode for high concurrency.

```sql
-- Agents Registry
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,          -- claude-code, openai-codex, etc.
    name TEXT NOT NULL,
    runtime TEXT NOT NULL,           -- sdk, cli, mcp, local
    model TEXT NOT NULL,
    capabilities TEXT NOT NULL,      -- JSON array of tags
    status TEXT NOT NULL DEFAULT 'IDLE',
    cost_usd REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Missions
CREATE TABLE missions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    repository_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',
    mode TEXT NOT NULL DEFAULT 'INTERACTIVE', -- INTERACTIVE, ABSENCE
    budget_limit_usd REAL DEFAULT 10.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Task DAG
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    title TEXT NOT NULL,
    dependencies TEXT NOT NULL,      -- JSON array of task IDs
    assigned_agent_id TEXT REFERENCES agents(id),
    allowed_files TEXT NOT NULL,     -- JSON array of globs
    status TEXT NOT NULL DEFAULT 'PENDING',
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Immutable Work Protocol Event Store
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    task_id TEXT,
    agent_id TEXT,
    event_type TEXT NOT NULL,
    action_type TEXT,
    payload TEXT NOT NULL,           -- JSON payload
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Shared Project Memory with Provenance
CREATE TABLE memory_records (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    fact TEXT NOT NULL,
    category TEXT NOT NULL,          -- architecture, constraint, verified_fact, rejected_approach
    source_agent TEXT NOT NULL,
    status TEXT NOT NULL,            -- OBSERVED, INFERRED, DECIDED, VERIFIED, REJECTED
    proof_reference TEXT,            -- commit hash, test ID, diff hash
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Approvals & Safety Queue
CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, APPROVED, DENIED
    timeout_seconds INTEGER DEFAULT 60,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

-- Verification Audit Records
CREATE TABLE verifications (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    verifier_agent TEXT NOT NULL,
    tests_passed INTEGER NOT NULL,
    tests_failed INTEGER NOT NULL,
    lint_clean BOOLEAN NOT NULL,
    scope_valid BOOLEAN NOT NULL,
    status TEXT NOT NULL,            -- PASSED, FAILED
    evidence TEXT NOT NULL,          -- JSON proof bundle
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. Product Development Roadmap

```text
PHASE 01 ──► PHASE 02 ──► PHASE 03 ──► PHASE 04 ──► PHASE 05 ──► PHASE 06
Product      Real Agent   Supervisor   Independent  Second Agent Multi-Agent
Kernel       Adapter      Engine       Verifier     (Codex)      Routing
(Desktop/DB) (Claude)     Watchdogs    Gate         Handoff      Registry

    │
    ▼
PHASE 07 ──► PHASE 08 ──► PHASE 09 ──► PHASE 10 ──► PHASE 11 ──► PHASE 12
Shared       Floating     Absence      5+ Agent     IDE          Cloud Layer
Memory       Supervisor   Mode         Fleet        Integration  (Sync & Team)
Provenance   Window HUD   Safety Gate  Ecosystem    (VS Code)
```

### Phase 1: Product Kernel
* Build desktop application shell (Electron / TypeScript).
* Implement SQLite database initialization and schema migration.
* Implement core `WorkProtocol` parser and event bus.
* Implement `WorkspaceManager` with Git worktree isolation.

### Phase 2: First Production Adapter (Claude Code)
* Implement `ClaudeCodeAdapter` supporting Claude Agent SDK and local CLI process.
* Normalize tool calls (read, write, bash) into Work Protocol events.
* End-to-end task execution in isolated worktree.

### Phase 3: Supervisory Watchdogs
* Port deterministic Layer A watchdogs:
  - Repeated failure / loop detection ($\ge 3$ consecutive errors).
  - Scope guard (rejects modifications outside whitelisted file boundaries).
  - Dangerous command interceptor (blocks destructive filesystem actions).
  - Execution iteration and token budget caps.

### Phase 4: Independent Verification Gate
* Implement standalone `VerifierEngine` decoupled from worker agent.
* Execute unit test suites, check linter outputs, inspect git diffs.
* Invariant: Worker self-reported completion is strictly rejected without verifier stamp.

### Phase 5: Second Agent & Automated Handoff (The MVP Target)
* Implement `CodexAdapter` (OpenAI Agents SDK / Codex).
* Demonstrate **Automatic Agent Handoff**:
  - Claude encounters repeated failure.
  - Supervisor halts Claude.
  - Handoff package dispatched to Codex for root-cause diagnosis.
  - Recovery context packaged into Claude or Codex to resolve the bug.
  - Independent Verifier confirms fix.

### Phase 6: Dynamic Multi-Agent Router
* Implement Agent Capability Registry.
* Multi-factor task scoring ($C_{\text{match}}, P_{\text{hist}}, C_{\text{cost}}, L_{\text{lat}}, W_{\text{ctx}}$).
* Concurrent multi-agent DAG execution across independent Git worktrees.

### Phase 7: Shared Project Memory with Provenance (COMPLETE)
* Implemented structured Memory Store enforcing 6-tuple provenance and epistemic status machine (`VERIFIED`, `INFERRED`, `UNVERIFIED`, `REJECTED`, `OBSERVED`, `DECIDED`, `STALE`).
* Rejection caching permanently blocks disproven hypotheses (`DO NOT REPEAT`).
* Deterministic trust hierarchy retrieval and bounded context packaging without opaque embeddings.
* Complete integration with Handoff Engine, Routing Engine, and Independent Verification Engine.

### Phase 8: Signature Floating Supervisor HUD
* Compact, ambient, always-on-top status widget.
* System tray integration and desktop notifications.
* Zero-nag background mode.

### Phase 9: Absence Mode & Safety Gates
* Configurable mission policies for unattended execution.
* Explicit human approval queue with default `DENIED` timeout.
* Morning summary generation.

### Phase 10: 5+ Agent Ecosystem
* Expand adapters: Google Gemini CLI, Qwen Local (Ollama/vLLM), Kimi, Cursor MCP.
* Rigorous compliance testing verifying all adapters adhere to identical Work Protocol contract.

### Phase 11: IDE Integration
* Lightweight VS Code and Cursor extension streaming live HUD state into editor status bar.

### Phase 12: Cloud Sync & Team Collaboration
* Optional encrypted sync of project memory across developer workstations.
* Team policies, remote mission status, and mobile notifications.

---

## 9. The Target Commercial MVP (Phase 1–5 Deliverable)

The commercial MVP demonstrates one killer, undeniable workflow in 60 seconds:

```text
1. Developer opens AI Supervisor Desktop and selects a repository.
2. Developer clicks: "Fix all failing authentication tests."
3. Supervisor decomposes task and assigns Worker (Claude Code).
4. Claude attempts naive fix -> Tests fail with encoding mismatch.
5. Claude attempts regex fix -> Tests fail with encoding mismatch.
6. Claude attempts third attempt -> Tests fail identically.
7. Supervisor Watchdog detects anomaly: 3 Consecutive Identical Failures.
8. Supervisor halts Claude.
9. Supervisor extracts Handoff Package and queries second opinion (OpenAI Codex).
10. Codex analyzes error trace & diff -> Identifies UTF-8 BOM byte-order marker flaw.
11. Supervisor stores finding in Project Memory (VERIFIED_FACT) and disproven regex (REJECTED_APPROACH).
12. Supervisor dispatches targeted Recovery Context back to Claude.
13. Claude applies byte-level BOM strip -> Sandbox tests pass!
14. Claude signals "Done".
15. Supervisor intercepts claim -> Invokes Independent Verifier.
16. Verifier independently executes test suite, lint checks, and file diff audit.
17. Verifier confirms: 42/42 tests pass, zero regressions, zero out-of-scope edits.
18. Supervisor merges worktree and marks Mission COMPLETED.
```

**Result**: Zero human debugging required. Total trust established through independent verification.
