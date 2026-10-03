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



