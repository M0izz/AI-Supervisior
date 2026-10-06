# AI Work Supervisor — System Architecture

## 1. Vision & Core Value Proposition

Autonomous AI agents often drift, loop on failing strategies, make destructive changes, or prematurely claim success.
The **AI Work Supervisor** provides a reliable supervisory loop:
1. Gives agents an objective.
2. Observes actions through an event stream.
3. Employs a dual-layer supervisor:
   - **Layer A**: Fast, deterministic rules (loop detection, budget overflow, scope violations).
   - **Layer B**: **Nemotron reasoning hosted on Nebius** to evaluate complex context and decide on interventions.
4. Validates final claims through an independent **Verifier** with empirical evidence (tests, diffs, static analysis).
5. Maintains **Project Memory with Provenance** so context is structured, verified, and not hallucinated.
6. Streams state in real time to the **Control Room Dashboard**.

```
                ┌───────────────────────────────────┐
                │          CONTROL ROOM UI          │
                │  (Missions, Graphs, Live Events)   │
                └─────────────────▲─────────────────┘
                                  │ WebSockets
                                  │
┌──────────────┐          ┌───────┴───────┐          ┌──────────────┐
│   PLANNER    │          │   EVENT BUS   │◄─────────┤    WORKER    │
│  Creates DAG │─────────►│ & EVENT STORE │          │ Tools, Edits │
└──────────────┘          └───────┬───────┘          └──────────────┘
                                  │
                                  │ Events
                                  ▼
                         ┌─────────────────┐
                         │   SUPERVISOR    │
                         │ ─────────────── │
                         │ 1. Rule Engine  │
                         │ 2. Nemotron     │
                         └────────┬────────┘
                                  │
                 ┌────────────────┼────────────────┐
                 ▼                ▼                ▼
             CONTINUE         INTERVENE         ESCALATE
                          (Pause/Delegate/Fix)  (Human Approval)
```

## 2. Event System (The Nervous System)

Every action taken by any agent or tool is published as an immutable event to the `EventBus` and stored in the `EventStore`.
- Agents and tools do not talk directly to the Supervisor.
- The Supervisor subscribes to the stream and monitors metrics (attempt counts, test diffs, scope changes).
- The Dashboard receives live events over WebSockets.

## 3. The Dual-Layer Supervisor

### Layer A: Deterministic Rules
- **Loop Detector**: Identifies identical failure signatures repeated $\ge 3$ times.
- **Scope Violation Detector**: Flags edits to files outside the declared task boundary.
- **Dangerous Action Gate**: Intercepts destructive commands (e.g. `rm -rf`, database schema drops).
- **Budget Guard**: Tracks token and execution step ceilings.

### Layer B: Nemotron Reasoning (Nebius)
When an anomaly is flagged by Layer A or when high-confidence judgment is required:
- A compact **Agent Context Package** is formatted.
- Nemotron reasons over the mission goal, task history, and failure signature.
- Nemotron outputs a structured decision:
  - `action`: CONTINUE | RETRY | CHANGE_STRATEGY | DELEGATE | ROLLBACK | PAUSE | REQUEST_APPROVAL | COMPLETE
  - `severity`: LOW | MEDIUM | HIGH | CRITICAL
  - `reason`: Rationale
  - `confidence`: $0.0 - 1.0$

## 4. Independent Verification

Verification is strictly decoupled from the worker.
A worker saying *"I fixed the CSV parser"* is treated as an unverified claim.
The **Verifier** independently executes:
- Unit and integration tests
- Lint and type checks
- Git diff inspection against approved scope
Only when empirical evidence passes does the Supervisor emit `MISSION_COMPLETED`.

## 5. Execution Layer: Local & Docker Container Isolation (Phase 5)

All worker and tool executions pass through the unified `ExecutionManager`:
- **LocalExecutionProvider**: Fast developer mode using WorkspaceJail and command prefix whitelisting.
- **DockerExecutionProvider**: Container sandbox using ephemeral Docker containers with disabled networking (`network_mode="none"`), stripped capabilities (`cap_drop=["ALL"]`), process limits, and memory/CPU quotas.
- **Safety Boundary**: Only the task workspace is mounted to `/workspace`; host roots, home directories, and the Docker socket are strictly rejected.
- **Observable Lifecycle**: Container lifecycle events (`container.created`, `container.started`, `container.destroyed`, `container.limit_exceeded`) stream to the EventBus.

## 6. Independent CI/CD Verification Layer: Jenkins (Phase 6)

Worker completion is strictly decoupled from verification.
- **External CI Gate**: Jenkins operates as an external, independent verification authority that checks out and builds the workspace code.
- **Structured Test Evidence**: Consumes JUnit XML test reports, publishing structured telemetry (`tests_passed`, `tests_failed`, `error_signature`) to the `EventBus`.
- **False Completion Interception**: When a worker claims completion but Jenkins finds test failures, the Supervisor flags a `CI_FAILURE` anomaly, reopens the task, pauses the worker, and invokes Nemotron reasoning for targeted recovery.
- **Clean Provider Abstraction**: Supports production `JenkinsHttpClient` with CSRF and queue resolution, as well as a deterministic `MockJenkinsProvider` for offline testing.
- **Verifier Handoff**: CI success alone does not auto-complete the mission; it hands off to the independent `VerifierAgent` for final empirical confirmation.

## 7. Mission Control Plane & Multi-Agent Registry (Phase 7)

Phase 7 elevates the Supervisor from a single-agent monitor into a robust, multi-agent control plane:
- **Mission Control Hierarchy**: Human Operator → Mission → Supervisor Control Plane → (Planner, Workers A/B, Reviewer, Verifier).
- **Enforced Mission Lifecycle**: Full finite state machine (`CREATED` → `PLANNING` → `RUNNING` → `PAUSED` → `INVESTIGATING` → `RECOVERING` → `VERIFYING` → `COMPLETED`, with failure branches `FAILED`, `BLOCKED`, `WAITING_APPROVAL`, `CANCELLED`).
- **Agent Registry**: Central directory tracking all active agents by `agent_id`, `agent_type` (`PLANNER`, `WORKER`, `REVIEWER`, `VERIFIER`, `SUPERVISOR`), `status`, `health`, `model`, `iterations`, `tool_calls`, and supervisor `interventions`.
- **Zero Cross-Contamination**: Isolated per-mission state machines, scoped file locks to detect multi-worker contention, and isolated telemetry queries.
- **Human Supervisory Interventions**: Standardized operator actions (`REQUEST_APPROVAL`, `TAKE_CONTROL`, `PAUSE`, `RESUME`, `CANCEL`, `HUMAN_REQUIRED`). Strict invariant: absence of response is never treated as approval.
- **Four-Quadrant Telemetry**: Execution, Reliability, Risk, and CI metrics with dedicated per-agent breakdowns and strict zero-fabrication cost accounting.
- **Full REST & WebSocket Surface**: Live control and streaming endpoints at `/api/missions/{id}/state`, `/api/agents`, `/api/approvals`, `/api/supervisor/events`, and `/ws/events`.

## 8. Reliability, Failure Injection & Safety Invariants (Phase 8)

Phase 8 hardens the control plane against realistic autonomous-agent failure modes through deterministic fixtures, property-style invariants, and chaos testing:
- **24-Scenario Failure Matrix**: Deterministic handling for repeated failures, stagnation, infinite loops, timeouts, iteration/tool budget overflow, scope violations, dangerous commands, false completions, CI/Jenkins faults, container crashes, resource exhaustion (OOM), model reasoning failures/timeouts, reviewer/verifier rejections, mission cancellations, and concurrent worker contention.
- **Strict Safety Invariants**:
  - *Dangerous Actions Blocked*: Dangerous commands cannot execute autonomously without explicit operator approval.
  - *Worker Cannot Mark Work VERIFIED*: Verification is strictly segregated to the independent `VerifierAgent` or Supervisor.
  - *Reviewer Read-Only*: Reviewer is restricted to `ALLOWED_READONLY_TOOLS` and cannot mutate workspace files.
  - *Empirical Verification Invariant*: Tasks cannot enter `VERIFIED` state without verified empirical proof (passing CI/tests).
  - *Repeated Strategy Guard*: Previously rejected recovery approaches are blocked and escalated to `HUMAN_REQUIRED`.
  - *Sandbox Isolation*: Container engine strictly prohibits host-root, home directory, or unauthorized path mounts.
  - *Secret Redaction*: Sensitive credentials, bearer tokens, and keys are scrubbed from arguments and event payloads.
  - *Mission Segregation*: Complete event, state machine, and lock isolation ensures Mission A never contaminates Mission B.
- **Empirical Chaos Demo**: `demo/scenarios/scenario_03_failure_matrix.py` injects active faults across actual system components and renders a live reliability report without print-only simulation or arbitrary scores.

## 9. Product Kernel & Foundation (Phase 1)

Phase 1 establishes the local-first product kernel necessary to transform AI Supervisor into a desktop control plane managing multiple external agent ecosystems:

### 1. Work Protocol v1 (`core/protocol/`)
- **Canonical Envelope**: `WorkProtocolEvent` models identity (`event_id`, `mission_id`, `task_id`, `agent_id`, `provider`, `timestamp`, `event_type`, `schema_version`), structured action payloads (`ActionInfo`), and operational metrics (`TelemetryInfo`).
- **Standard Lifecycle Events**: Canonical typed events for missions, tasks, agents, filesystem mutations, command executions, independent tests, supervisor interventions, handoffs, recoveries, verifications, and human approvals.
- **Task Dispatch Package**: `TaskDispatchPackage` forms the formal boundary between the Supervisor and any `AgentAdapter`, specifying goals, file whitelists, fine-grained capability permissions, resource caps, and verification commands.

### 2. SQLite WAL Persistence (`storage/sqlite/`)
- **Durable Local-First Engine**: SQLite configured in `WAL` (Write-Ahead Logging) mode with `PRAGMA foreign_keys = ON;`, `PRAGMA synchronous = NORMAL;`, and busy timeouts.
- **Relational Domain Models**: Normalized schema covering `missions`, `tasks`, `agents`, `events`, `memory_records`, `approvals`, and `verifications`.
- **Append-Only Event Store**: Events are immutable, append-only, and independent of UI state.
- **Process Restart Durability**: Mission, task, and agent state persists across application crashes and restarts, reloaded cleanly by repository layers.
- **Non-Blocking Event Sink**: `attach_sqlite_persistence` subscribes to the live `EventBus` and records all stream traffic asynchronously without degrading dispatch latency.

### 3. Git Worktree Isolation (`execution/worktree.py`)
- **FILESYSTEM ISOLATION**: Multi-agent tasks execute inside dedicated Git worktrees on isolated branches (`supervisor/<mission_id>/<task_id>`).
- **Main Working Tree Protection**: Agents cannot mutate files in the user's primary working tree during task execution.
- **Strict Git Enforcement**: If Git is uninitialized or unavailable, the system explicitly refuses autonomous multi-agent execution with an actionable error. Silent fallback to shared directory sandboxes is strictly prohibited.
- **Safe Explicit Failure on Conflicts**: Merge conflict resolution is never performed automatically without verification; conflicts produce safe explicit failures requiring human or supervisory review.
- **Root Protection**: Worktree cleanup verifies that paths are strictly confined to `.supervisor/worktrees/` and can never delete the main repository root.

## 10. First Production Agent Adapter: Claude Code (Phase 2)

Phase 2 establishes the universal `AgentAdapter` contract and integrates Anthropic's Claude Code as the first production-grade external coding agent:

### 1. Universal AgentAdapter Contract (`adapters/base.py`)
- **Decoupled Boundary**: External agents implement `identity`, `capabilities`, `check_availability()`, `prepare()`, `execute()`, `cancel()`, `status()`, and `cleanup()`.
- **Zero Provider Leakage**: The Supervisor core remains agnostic of Claude-specific flags or internal CLI details. Future agents (Codex, Gemini CLI, Qwen) implement this exact same interface.

### 2. Worktree Execution Pipeline
- **Worktree Enforced**: Tasks execute exclusively inside dedicated Git worktrees on isolated task branches (`.supervisor/worktrees/<mission>_<task>`).
- **Primary Working Tree Guard**: Any execution attempt targeting the primary repository is strictly aborted before process invocation.

### 3. Observable Work Protocol Streaming
- **Process Lifecycle Control**: External processes are launched with `asyncio.create_subprocess_exec` using explicit argument arrays (`shell=False` invariant).
- **Work Protocol Normalization**: Stdout/stderr streams are parsed line-by-line and converted into canonical `WorkProtocolEvent` envelopes (`agent.started`, `command.started`, `file.changed`, `task.completed`, `agent.stopped`) and published onto the `EventBus`.
- **Supervisory Controls**: Transparent timeout enforcement with graceful SIGTERM escalation to SIGKILL, and manual supervisor cancellation hooks.

### 4. Adapter Discovery (`adapters/registry.py`)
- Integrated into `AgentRegistry` for dynamic capability querying (`find_by_capability`), availability probing, and multi-agent dispatch coordination.

## 11. Live Supervisory Watchdogs on the Work Protocol (Phase 3)

Phase 3 operationalizes the fundamental invariant: *the agent is not allowed to supervise itself*. The Supervisor observes external agents via canonical `WorkProtocolEvent` streams and intervenes deterministically:

### 1. Watchdog Engine (`supervisor/watchdogs.py`)
- **Deterministic-First Evaluation**: Zero LLM dependencies for safety-critical decisions. All rules evaluate synchronously or near-instantaneously from protocol events.
- **Provider-Independent Decisions**: Evaluates events into structured `WatchdogDecision` records containing `action` (`ALLOW`, `WARN`, `PAUSE`, `CANCEL`, `REQUIRE_APPROVAL`), `rule_id`, `severity`, and concrete evidence.
- **Integrated Rules**:
  - `DANGEROUS_COMMAND`: Intercepts prohibited destructive commands (`rm -rf /`, `DROP TABLE`, `kill -9`) before/during execution.
  - `SCOPE_VIOLATION`: Enforces authorized task file boundaries, flags traversal attempts (`../`), and protects system/secret paths (`.git/`, `.env`).
  - `LOOP_DETECTED`: Detects repeated failure loops using normalized error signatures (abstracting line numbers and pointers); halts after 3 consecutive identical failures.
  - `BUDGET_EXCEEDED` & `TIMEOUT_EXCEEDED`: Enforces action turn budgets and execution duration limits.

### 2. Intervention Controller & Idempotency
- **Decoupled Actuation**: Converts `WatchdogDecision` into adapter lifecycle actions (`AgentAdapter.cancel(task_id)`), human approval requests, and audit logs.
- **Idempotency Guard**: Guarantees that a task receives terminal cancellation at most once, preventing cascaded process kill attempts during shutdown.
- **Durable Audit Trail**: Persists every intervention to SQLite WAL storage and publishes `supervisor.intervention` events to the `EventBus`.

## 12. Independent Verification Engine (Phase 4)

Phase 4 operationalizes the core axiom: **Agent completion ≠ verified completion**. Worker claims are never trusted blindly; empirical verification gates certified completion:

### 1. Verification Engine (`core/verification/engine.py`)
- **Deterministic Check Pipeline**: Sequentially runs completion claim structure check, Git worktree integrity check, scope boundary check, independent test execution check, and regression check.
- **Decision Model**: Returns structured `VerificationDecision` (`ACCEPT`, `REJECT`, or `REQUIRE_REVIEW`).
- **Test Sandbox Isolation**: Executes verification commands strictly inside the task's isolated Git worktree using `shell=False`, bounded stdout/stderr buffers, and monotonic execution timeout limits.
- **Task Lifecycle Integration**:
  - `ACCEPT`: Transitions task to `VERIFIED` via `TaskManager.verify_task`.
  - `REJECT`: Reopens task to `IN_PROGRESS` or fails task, preventing false completion.
  - `REQUIRE_REVIEW`: Flags task for operator review when acceptance criteria are ambiguous.
- **Durable Verification History**: Persists all reports into SQLite WAL `verifications` table via `VerificationRepository`.

---

## 10. Phase 5: Handoff Engine & Second Production Adapter (Codex)

Phase 5 establishes multi-agent recovery and execution continuity:

- **Universal AgentAdapter Ecosystem**:
  - `adapters/claude_code.py`: Anthropic Claude Code adapter.
  - `adapters/codex.py`: OpenAI Codex adapter.
  - Both share the universal `AgentAdapter` contract (`identity`, `check_availability`, `prepare`, `execute`, `cancel`, `status`, `cleanup`).
- **Control Plane Invariant**: "A handoff transfers responsibility, not authority."
  - Agents never directly communicate or negotiate task transfers.
  - Supervisor halts failing agents, formulates structured context, and commands target agents.
- **Provenance-Tagged Context Packages**:
  - `HandoffContextBuilder` constructs packages categorizing facts into `VERIFIED` (empirical repo truths), `UNVERIFIED` (unproven agent claims), and `REJECTED` (failed approaches / error signatures).
- **Worktree Continuity**: Target agents are dispatched into the exact same isolated Git worktree without touching the primary repository.
- **Loop Protection & Verification Termination**:
  - Configurable ceiling (`max_handoffs_per_task`) stops ping-pong loops and triggers `SUPERVISOR_HUMAN_REQUIRED`.
  - Transferred tasks still terminate strictly via Phase 4 `VerificationEngine` (`ACCEPT`).

---

## 13. Dynamic Agent Router (Phase 6)

Phase 6 implements capability-based, empirical evidence-aware dynamic task routing:

- **Core Invariant**: "Routing is a Supervisor decision based on task requirements and available agent capabilities. Agents do not self-select."
- **Routing Engine (`core/routing/engine.py`)**:
  - Extracts deterministic `TaskRequirements` (required capabilities, preferred capabilities, scope, constraints).
  - Evaluates candidates against an **Eligibility Gate** (exclusion list, runtime availability probe, hard required capabilities).
  - Calculates deterministic multi-factor scores:
    $$\text{Score} = \text{Base Capability (10.0)} + \text{Preferred Bonus (2.0/each)} + \text{Availability (2.0)} + \text{Bounded Historical Reliability} \in [-10, 10]$$
  - Handles cold-start agents neutrally (reliability score 0.0) without penalty.
  - Deterministically breaks ties via capability footprint, fewest failures, fewest handoffs, and stable sorting.
  - Emits structured decisions (`ROUTE`, `NO_ELIGIBLE_AGENT`, `REQUIRE_REVIEW`) with human-readable rationales.
  - Persists all decisions into SQLite WAL table `routing_decisions`.
  - Emits real-time EventBus events (`routing.started`, `routing.candidate.evaluated`, `routing.completed`, `routing.failed`).
- **Handoff Engine Integration**:
  - Automatically resolves target agents during task handoffs (`target_agent_id="auto"`), strictly excluding the failing source agent to prevent ping-pong loops.

---

## 14. Shared Project Memory (Phase 7)

Phase 7 implements authoritative, cross-agent project memory:

- **Core Invariant**: "Agents are replaceable; project knowledge is not. Memory is not automatically truth; claims from agents remain UNVERIFIED until empirically proven."
- **Epistemic Model**:
  - `VERIFIED`: Proven by objective empirical evidence (passing tests, compiler output, git worktree verification).
  - `INFERRED`: Derived from observations but not directly tested.
  - `UNVERIFIED`: Agent-reported claims and hypotheses.
  - `REJECTED`: Disproven hypotheses retained permanently to prevent subsequent agents from repeating failed attempts.
- **Memory Store (`memory/store.py`)**:
  - Scoped by `project_id` to guarantee zero cross-project leakage.
  - Deterministic deduplication via normalized content keys.
  - Immutability of provenance: supersession tracking preserves audit trails.
  - Deterministic ranking: Trust Hierarchy Weight + Task Match + Keyword Overlap + Recency.
  - Automatic secret and API key scrubbing before SQLite persistence.
  - Persisted in SQLite WAL table `memory_records`.
- **System Integration**:
  - **Handoff Engine**: Packages verified facts, decisions, and `DO NOT REPEAT` rejected approaches into receiving agent context packages.
  - **Verification Engine**: Directly promotes verified facts on `ACCEPT` and records rejected approaches on `REJECT`.
  - **Routing Engine**: Leverages historical verified successes and failure records as reliability signals.

---

## 15. Desktop Product Shell & Floating HUD (Phase 8)

Phase 8 introduces the local-first desktop application shell and persistent ambient HUD:

- **Desktop-as-Client Invariant**:
  - The desktop application is strictly an interface and client to the authoritative FastAPI backend.
  - Electron owns application lifecycle, tray presence, windows, and notifications; it does NOT own business truth, DAG scheduling, routing, or memory state.
- **Electron Security Baseline**:
  - `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, and strict navigation filtering.
  - Narrow typed `window.supervisor` preload bridge via `contextBridge.exposeInMainWorld`.
  - Zero Node primitives (`fs`, `child_process`, `os`, `process`) exposed to renderers.
- **Dual-Window Model**:
  - **Control Room Window**: Full detailed mission dashboard, task DAG visualization, multi-agent metrics, and approval queue. Hides to tray on close to preserve background supervision.
  - **Floating HUD Window**: Compact (380x240), persistent, always-on-top, low-distraction status layer displaying active mission, current agent, watchdog interventions, verification progress, and approval gates.
- **Zero-Nag Notification Policy**:
  - Suppresses all routine operational events (commands executed, files written, tests passing).
  - Surfaces only actionable interventions, pending approvals, verification rejections, or mission failures.
  - Debounces duplicate notifications across a 5-second sliding window.
- **System Tray Integration**:
  - Dynamic status indicator (`LIVE` / `DISCONNECTED`), HUD toggling, and quick Control Room access.

---

## 16. Absence Mode & Bounded Autonomy (Phase 9)

Phase 9 introduces Absence Mode for safe, unattended operation ("Continue working on this while I'm away"):

- **Core Invariant**: "Absence Mode expands continuity, not authority."
- **Strict Authority Hierarchy**:
  ```text
  Hard Safety Restrictions > User Absence Policy > Supervisor Rules > Task Constraints > Agent Capabilities > Agent Request
  ```
- **Zero Agent Self-Escalation**:
  - Agents can never broaden their own authority, disable watchdogs, bypass independent verifiers, grant themselves capabilities, or extend duration ceilings.
  - Any self-escalation attempt is immediately denied with rule `security.self_escalation_blocked`.
- **Policy Snapshot Immutability**:
  - Arming Absence Mode freezes an explicit, persisted snapshot (`AbsencePolicy`). Modifying global configurations does not mutate a running session.
- **Hard Expiration & Bounded Ceilings**:
  - Sessions enforce hard wall-clock timeouts (`expires_at`). When elapsed, status transitions to `EXPIRED` and agents halt safely.
  - Hard retry ceilings (`max_retries`) and handoff limits (`max_handoffs`) transition session to `PAUSED` and notify user on failure loops.
- **Independent Verification Mandatory**:
  - Agent-reported completion is never treated as verified mission completion. Autonomous continuation to subsequent tasks occurs only when the Independent Verifier returns `ACCEPT`.
- **Fail-Closed Durability**:
  - Persisted in SQLite tables `absence_sessions` and `absence_decisions`.
  - Backend startup reconciliation marks expired sessions as `EXPIRED` and corrupted sessions as `BLOCKED`.
- **Desktop HUD & Emergency Stop**:
  - Ambient Floating HUD displays active status and remaining time countdown.
  - Operator can trigger immediate Emergency Stop (`cancel`), revoking autonomous continuation and halting running agents safely.

---

## 17. Multi-Agent Provider Fleet (Phase 10)

Phase 10 expands the AI Supervisor provider ecosystem through the existing `AgentAdapter` contract, demonstrating heterogeneous multi-agent operations under a single unified supervisory protocol:

- **Core Invariant**: "Adding a provider must not require modifying Supervisor business logic."
- **Architectural Boundary**:
  ```text
                      ┌─ Claude Code (Anthropic)
                      │
  Supervisor ─ Adapter├─ Codex (OpenAI)
                      │
                      ├─ Gemini (Google)
                      │
                      ├─ Qwen / Local (Open Weights)
                      │
                      ├─ OpenCode (CLI Agent)
                      │
                      └─ Kimi (Moonshot)
  ```
- **Unified Adapter Lifecycle**:
  - `identity()`, `capabilities()`, `check_availability()`, `prepare()`, `execute()`, `cancel()`, `status()`, `cleanup()`.
- **Capability Taxonomy**:
  - `code_execution`, `filesystem_read`, `filesystem_write`, `terminal_execution`, `git`, `test_execution`, `documentation`, `web_access`, `local_model`, `multimodal`.
  - Capabilities declare what the adapter actually enables, avoiding inflated claims.
- **Untrusted Local Execution Boundary**:
  - Local models (e.g. Qwen) are treated as untrusted execution providers. Worktree isolation, scope monitoring, dangerous command interception, and independent verification apply identically.
- **Unified Work Protocol Normalization**:
  - All providers map internal telemetry to canonical `WorkProtocolEvent` streams (`agent.started`, `command.started`, `file.edited`, `command.completed`, `agent.completed`).
- **Zero-Bypass Verification & Absence**:
  - No provider can bypass Independent Verification, Watchdogs, or Absence Mode policies.

---

## 18. IDE Integration — Visual Studio Code (Phase 11)

Phase 11 integrates the AI Supervisor control plane into developer IDEs, beginning with Visual Studio Code:

- **Core Architectural Invariant**:
  > *"The IDE extension is an interface to the Supervisor, NOT another Supervisor, NOT an agent runtime, and NOT the source of truth."*
- **Tri-Interface Model**:
  ```text
               ┌─ Floating HUD (Desktop ambient widget)
               │
  Supervisor ──┼─ Control Room (Web cockpit dashboard)
  Core Backend │
               └─ IDE Extension (VS Code Activity Bar, Status Bar & Commands)
  ```
- **Unified Communication Layer**:
  - Extension communicates exclusively through standard FastAPI HTTP REST (`/api/missions`, `/api/agents`, `/api/adapters`, `/api/approvals`, `/api/absence`) and WebSocket event streaming (`/ws/events`).
  - No Python logic embedded in extension; zero local agent process spawning from the editor.
- **Native Activity Bar & Views**:
  - `Missions View`: Live DAG progress, active agents, and independent verification status.
  - `Fleet Providers View`: Real-time truthfulness badges (`AVAILABLE`, `UNAVAILABLE`) and capability chips.
  - `Attention & Approvals View`: Interactive operator approval queue and active Absence Mode countdowns.
- **Contextual Editor Integration**:
  - `Work on Selection`: Packages exact selection lines as untrusted task input.
  - `Investigate Diagnostics`: Gathers active compiler/linter diagnostics for supervisory investigation.
- **Security & Workspace Containment**:
  - `PathValidator` ensures all file navigations and context extractions stay strictly inside workspace roots, blocking traversal attacks.
  - Respects VS Code Workspace Trust: restricts autonomous mission dispatch in untrusted folders.
  - Zero-Nag notification manager debounces and surfaces only actionable interventions and approvals.

---

## 19. Cloud Sync + Multi-Device (Phase 12)

Phase 12 delivers the final roadmap capability: optional, local-first synchronization and multi-device project continuity:

- **Core Architectural Invariant**:
  > *"Cloud sync may replicate Supervisor state, but it must never become a higher authority than the local Supervisor."*
- **Replication Hierarchy**:
  ```text
  Developer Machine A (Laptop) ──[Outbox]──> Cloud Sync Service <──[Inbox]── Developer Machine B (Desktop)
             │                                                                         │
    100% Authoritative Local DB                                               100% Authoritative Local DB
  ```
- **Local-First & Offline-First**:
  - All missions, watchdogs, handoffs, verifications, and memories commit to local SQLite WAL tables first.
  - Outbox (`sync_outbox`) and Inbox (`sync_inbox`) queues handle asynchronous background sync without ever blocking operator commands.
- **Data Boundary & Sanitization**:
  - `sync.sanitizer.sanitize_payload()` strictly redacts all API keys, private keys, bearer tokens, passwords, and absolute host paths prior to transmission.
  - Zero secret or raw source code leaks across the network.
- **Path-Independent Identity**:
  - Projects are derived canonically from Git remote origin URLs (`repo:github.com/user/project`) or commit roots, ensuring cross-machine portability across Windows, Linux, and macOS.
- **Deterministic Conflict Resolution**:
  - Memory epistemic promotion (`VERIFIED` facts cannot be downgraded by stale writes).
  - Task and verification non-regression (terminal outcomes cannot revert to pending).
  - Tombstone precedence absorbs equal or lower revision resurrecting writes.
  - Local security policy always overrides remote suggestions.
- **Cryptographic Device Security**:
  - Devices authenticate using salted SHA-256 token hashes.
  - Instant one-click device revocation immediately blocks compromised hardware.






