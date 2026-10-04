# AI Supervisor — 12-Phase Product Execution Roadmap

> *"AI agents are becoming abundant. The scarce resource is reliable coordination."*

---

## 1. Provider Capability & Integration Matrix

This matrix tracks the real operational status of every agent adapter. An adapter is marked **Implemented** only when backed by reproducible automated tests and real task execution.

| Provider / Agent | Adapter Module | Integration Mechanism | Authentication | Execution Isolation | Event Streaming | Test Coverage | Current Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Claude Code** | `adapters/claude_code.py` | Universal AgentAdapter / CLI | `ANTHROPIC_API_KEY` | Git Worktree | Work Protocol v1 | Unit + Mock E2E (14 Tests) | **Implemented (Phase 2)** |
| **OpenAI Codex** | `adapters/codex/` | OpenAI Agents SDK / CLI | `OPENAI_API_KEY` | Git Worktree | Work Protocol v1 | Unit + Mock E2E | **Planned (Phase 5 Target)** |
| **Google Gemini** | `adapters/gemini/` | Gemini CLI / SDK | `GEMINI_API_KEY` / Google ADC | Git Worktree | Work Protocol v1 | Planned | **Planned (Phase 10 Target)** |
| **Qwen / Local** | `adapters/qwen/` | Ollama / vLLM / llama.cpp HTTP | Local Loopback (No Auth) | Git Worktree | Work Protocol v1 | Planned | **Planned (Phase 10 Target)** |
| **Kimi / OpenCode** | `adapters/kimi/` | Moonshot API / CLI Process | API Key | Git Worktree | Work Protocol v1 | Planned | **Planned (Phase 10 Target)** |
| **Cursor / MCP** | `adapters/cursor/` | Model Context Protocol (MCP) | Local Process Bridge | Git Worktree | Work Protocol v1 | Planned | **Planned (Phase 10 Target)** |
| **Internal Worker** | `agents/worker/` | Python In-Process Runtime | Local Sandbox | Workspace Jail / Docker | Native EventBus | 124 Passing Tests | **Implemented (Prior Baseline)** |
| **Nebius Nemotron** | `integrations/nebius/`| Nebius AI Studio REST API | `NEBIUS_API_KEY` (Optional) | Cloud API | Structured JSON | 124 Passing Tests | **Implemented (Optional Cloud)**|
| **Jenkins CI** | `integrations/jenkins/`| Jenkins REST API / Mock | API Token (Optional) | External Runner | JUnit Telemetry | 124 Passing Tests | **Implemented (Optional CI)** |

---

## 2. The 12-Phase Roadmap

```text
PHASE 00 ──► PHASE 01 ──► PHASE 02 ──► PHASE 03 ──► PHASE 04 ──► PHASE 05
Audit &      Product      Claude Code  Supervisory  Independent  Codex Handoff
Roadmap      Kernel       Adapter      Watchdogs    Verifier     (MVP Milestone)
(COMPLETE)   (COMPLETE)   (COMPLETE)   (COMPLETE)   (COMPLETE)



    │
    ▼
PHASE 06 ──► PHASE 07 ──► PHASE 08 ──► PHASE 09 ──► PHASE 10 ──► PHASE 11 ──► PHASE 12
Capability   Shared       Floating     Absence      5+ Agent     IDE          Cloud Layer
Router       Memory       HUD Window   Mode Gate    Ecosystem    Extensions   (Team Sync)
```

---

### Phase 0: Repository Audit & Technical Baseline
* **Objective**: Complete architectural audit of the hackathon repository against the product specification.
* **Deliverables**:
  - `docs/migration-audit.md` (Answers to 10 architectural questions).
  - `docs/roadmap.md` (12-phase execution plan and provider matrix).
* **Acceptance Criteria**: Audit complete, zero code modifications, clean test baseline (124 passed, 2 skipped).
* **Status**: ✅ **COMPLETE**

---

### Phase 1: Product Kernel & Foundation
* **Objective**: Build the local-first kernel with SQLite persistence, Work Protocol schema, and Git worktree isolation.
* **Deliverables**:
  - `core/protocol/`: `WorkProtocolEvent`, `TaskDispatchPackage`, `ActionInfo`, `TelemetryInfo`, and Pydantic validators.
  - `storage/sqlite/`: SQLite WAL database initialization, foreign-key schema DDL, async CRUD repositories for missions, tasks, agents, events, memory, approvals, and verifications.
  - `execution/worktree.py`: `GitWorktreeManager` creating isolated branches and directories for agent tasks, protecting the main working tree, with strict Git enforcement (no silent fallback).
  - Integration: SQLite persistence connected to `EventBus`, `MissionManager`, `TaskManager`, `AgentRegistry`, and `AppState`.
  - Tests: `tests/test_kernel.py` (16 automated tests).
* **Acceptance Criteria**:
  - [x] Work Protocol v1 exists and is schema validated.
  - [x] Task dispatch structure exists.
  - [x] SQLite WAL persistence works.
  - [x] Mission/task/agent/event state can survive process restart.
  - [x] Git worktrees can be created and isolated.
  - [x] Main working tree is protected from autonomous task execution.
  - [x] Existing EventBus remains functional.
  - [x] Existing internal Worker remains functional.
  - [x] New Phase 1 tests pass (16/16).
  - [x] Existing baseline tests pass (124 passed, 2 skipped, 0 failed). Total suite: 140 passed, 2 skipped, 0 failed.
  - [x] No provider integrations are falsely represented as implemented.
  - [x] Documentation updated.
  - [x] Security review completed.
* **Status**: ✅ **COMPLETE**

---

### Phase 2: First Production Agent Adapter (Claude Code)
* **Objective**: Implement the `AgentAdapter` interface for Anthropic Claude Code using Work Protocol v1 and Git worktree isolation.
* **Deliverables**:
  - `adapters/base.py`: Universal `AgentAdapter` abstract base class consuming `TaskDispatchPackage` and emitting `WorkProtocolEvent`.
  - `adapters/models.py`: `AdapterIdentity`, `AdapterCapability`, `AdapterAvailability`, and `AdapterExecutionResult`.
  - `adapters/claude_code.py`: `ClaudeCodeAdapter` with worktree isolation verification, argument arrays (`shell=False`), stdout/stderr streaming, timeout, cancellation, and event normalization.
  - `adapters/registry.py`: `AdapterRegistry` integrated into `AgentRegistry`.
  - `tests/test_adapters.py`: Deterministic test suite with mock Claude process layer (13 passed, 1 skipped).
  - `docs/adapters/claude-code.md`: Complete adapter reference documentation.
* **Acceptance Criteria**:
  - [x] Generic AgentAdapter contract exists (`adapters/base.py`).
  - [x] Claude implementation conforms to it (`ClaudeCodeAdapter`).
  - [x] Claude-specific logic is isolated from Supervisor core.
  - [x] Agent Registry can discover Claude (`AgentRegistry.get_adapter`).
  - [x] Claude can receive a `TaskDispatchPackage`.
  - [x] Claude executes inside a Supervisor Git worktree; main repository is strictly protected.
  - [x] Process lifecycle is controlled (start, stdout/stderr stream, timeout, cancellation, completion).
  - [x] Claude execution emits `WorkProtocolEvent` objects onto EventBus and persists to SQLite.
  - [x] Zero `shell=True` used; path traversal blocked; secrets not persisted.
  - [x] Deterministic mock-process adapter tests pass.
  - [x] Complete regression suite passes (153 passed, 3 skipped, 0 failed).
* **Status**: ✅ **COMPLETE**

---

### Phase 3: Supervisory Watchdogs on Live Protocol
* **Objective**: Connect the deterministic watchdog engine to live Work Protocol streams emitted by external adapters and enact automated interventions.
* **Deliverables**:
  - `supervisor/watchdogs.py`: `WatchdogEngine`, `WatchdogDecision`, `WatchdogAction`, `InterventionRecord`, and `InterventionController`.
  - Integrated rules: `DANGEROUS_COMMAND`, `SCOPE_VIOLATION`, `LOOP_DETECTED` (threshold = 3, normalized signatures), `BUDGET_EXCEEDED`, and `TIMEOUT_EXCEEDED`.
  - Intervention actuation: Decoupled invocation of `AgentAdapter.cancel(task_id)` with strict idempotency guards against teardown cascades.
  - EventBus & SQLite persistence: Structured `supervisor.intervention` events with audit records.
  - Test Suite: `tests/test_watchdogs.py` (19 tests covering evaluation, loop detection, scope, dangerous commands, budgets, idempotency, and end-to-end killer scenario).
  - Documentation: `docs/supervision/watchdogs.md`.
* **Acceptance Criteria**:
  - [x] WorkProtocolEvent reaches watchdog engine.
  - [x] Watchdogs evaluate live external-agent events deterministically without LLMs.
  - [x] Claude execution remains provider-independent from watchdog logic.
  - [x] Repeated failure loop detection with normalized error signatures triggers cancellation.
  - [x] Scope violation detection stops out-of-scope modifications, path traversal, and protected file edits.
  - [x] Prohibited dangerous commands intercepted safely.
  - [x] Execution budgets (turn caps and duration timeouts) enforced.
  - [x] InterventionController dispatches adapter cancellation and integrates with approvals.
  - [x] Idempotency guards prevent duplicate cancellations.
  - [x] All 19 Phase 3 tests pass; full regression suite passes with 172 passed, 3 skipped, 0 failed.
* **Status**: ✅ **COMPLETE**


---

### Phase 4: Independent Verification Engine
* **Objective**: Build an independent verification authority that validates claims without trusting the worker.
* **Deliverables**:
  - `core/verification/models.py`: `VerificationDecision` (`ACCEPT`, `REJECT`, `REQUIRE_REVIEW`), `VerificationCheck`, `VerificationContext`, and `VerificationResult`.
  - `core/verification/checks.py`: Modular checks covering Git integrity, scope boundary enforcement, path traversal protection, independent test execution (`shell=False`, bounded output, timeout ceilings), and regression detection.
  - `core/verification/engine.py`: Standalone `VerificationEngine` executing tests in clean worktrees, persisting records into SQLite `verifications` table, and integrating with `TaskManager`.
  - `tests/test_verification.py`: 12 automated verification tests covering all check outcomes, restart persistence, and the killer false-claim scenario.
  - `docs/verification.md`: Complete specification and architecture documentation for independent verification.
* **Acceptance Criteria**:
  - [x] Worker signals completion (`task.completed`), which is treated strictly as an unverified claim.
  - [x] Verifier runs independent test checks in isolated worktrees (`shell=False`, timeout bounded).
  - [x] Task transitions to `VERIFIED` only if empirical proofs succeed (`ACCEPT`).
  - [x] If tests fail, scope is violated, or regressions occur, task is REJECTED and reopened.
  - [x] Missing verifiable criteria produce `REQUIRE_REVIEW`.
  - [x] Verification reports survive process restart in SQLite WAL storage.
  - [x] All 12 Phase 4 tests pass; full regression suite passes with 184 passed, 3 skipped, 0 failed.
* **Status**: ✅ **COMPLETE**


---

### Phase 5: Second Agent & Automated Handoff (Commercial MVP Milestone)
* **Objective**: Integrate OpenAI Codex and prove automated failure diagnosis and agent handoff.
* **Deliverables**:
  - `adapters/codex/`: `CodexAdapter` supporting OpenAI Agents SDK / Codex CLI.
  - `core/handoff/engine.py`: Generates structured Handoff Packages (failure signatures, attempted approaches, diffs, constraints) without dumping full raw conversations.
* **Acceptance Criteria**:
  - **The 60-Second MVP Demo**:
    1. Claude attempts task $\to$ encounters 3 consecutive test failures.
    2. Supervisor pauses Claude.
    3. Handoff Package sent to Codex for second-opinion diagnosis.
    4. Codex diagnoses root cause (e.g. UTF-8 BOM encoding mismatch).
    5. Supervisor generates recovery context $\to$ Claude resumes and fixes code.
    6. Independent Verifier validates all tests pass $\to$ Mission COMPLETED.

---

### Phase 6: Dynamic Capability Router
* **Objective**: Implement intelligent task routing across multiple connected agents.
* **Deliverables**:
  - `core/routing/registry.py`: Agent Capability Registry with static tags and dynamic performance metrics.
  - `core/routing/scorer.py`: Multi-factor suitability scoring ($C_{\text{match}}, P_{\text{hist}}, C_{\text{cost}}, L_{\text{lat}}, W_{\text{ctx}}$).
* **Acceptance Criteria**:
  - Given a multi-task mission, the Router assigns backend tasks to Codex, frontend tasks to Gemini, and private/offline tasks to Qwen based on policy.

---

### Phase 7: Shared Project Memory with 6-Tuple Provenance
* **Objective**: Implement cross-agent empirical project memory backed by SQLite.
* **Deliverables**:
  - `core/memory/store.py`: Persistent memory store enforcing provenance (`OBSERVED`, `INFERRED`, `DECIDED`, `VERIFIED`, `REJECTED`).
  - Rejection caching preventing subsequent agents from repeating failed hypotheses.
* **Acceptance Criteria**:
  - Fact discovered by Agent A is saved as `VERIFIED` and immediately injected into the context of Agent B without human copy-pasting.

---

### Phase 8: Signature Floating Supervisor HUD & Desktop Shell
* **Objective**: Build the ambient, always-on desktop user experience.
* **Deliverables**:
  - `apps/desktop/`: Electron application shell packaging the React cockpit.
  - `apps/desktop/hud/`: Lightweight, collapsible, always-on-top floating HUD window.
  - System tray icon and native OS notification integration.
* **Acceptance Criteria**:
  - User can minimize main cockpit; floating HUD stays visible, remaining silent during normal execution and surfacing only actionable alerts (`APPROVAL`, `WARNING`, `COMPLETE`).

---

### Phase 9: Absence Mode & Safety Policies
* **Objective**: Enable safe unattended execution ("I'm going to sleep. Finish this.").
* **Deliverables**:
  - `core/policies/absence.py`: Absence Mode policy configuration.
  - Approval queue with configurable budgets, timeouts, and automatic pause triggers.
* **Acceptance Criteria**:
  - In Absence Mode, safe edits and tests proceed automatically; file deletions or spending spikes immediately pause execution and queue for operator review.

---

### Phase 10: 5+ Agent Fleet Expansion
* **Objective**: Expand adapter ecosystem to Gemini CLI, Qwen Local, Kimi, and Cursor MCP.
* **Deliverables**:
  - `adapters/gemini/`, `adapters/qwen/`, `adapters/kimi/`, `adapters/cursor/`.
* **Acceptance Criteria**:
  - All 6 providers pass the unified Work Protocol conformance test suite.

---

### Phase 11: IDE Integration
* **Objective**: Integrate AI Supervisor status and controls directly into developer IDEs.
* **Deliverables**:
  - VS Code Extension streaming mission status, active agents, and approvals into the status bar.
* **Acceptance Criteria**:
  - Operator can trigger missions and approve actions without leaving their code editor.

---

### Phase 12: Optional Cloud Sync & Team Collaboration
* **Objective**: Add optional cloud synchronization for team memory and remote mission monitoring.
* **Deliverables**:
  - Encrypted sync of project memory across developer workstations.
  - Mobile web view for remote mission observation and push notifications.
* **Acceptance Criteria**:
  - Local-first architecture functions 100% offline; cloud features activate only when account sync is explicitly enabled.
