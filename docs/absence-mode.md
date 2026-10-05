# Absence Mode Specification & Operational Guide

> *"Absence Mode expands continuity, not authority."*

AI Supervisor is a personal AI operations layer that manages, coordinates, supervises, recovers, and verifies the AI agents a developer already uses. In Normal Mode, the developer actively supervises operations. In **Absence Mode**, the developer may step away ("Continue working on this while I'm away"), permitting the Supervisor to autonomously advance work strictly within explicit, immutable, user-authorized policy boundaries.

The Supervisor does **not** become unrestricted autonomous AI. An agent completion is never treated as verified mission completion, and no agent is ever permitted to escalate its own permissions.

---

## 1. Mental Model & Core Invariant

```text
               User (Operator)
                     │
                     ▼ (Explicit Arm & Authorize)
               Absence Policy
                     │
                     ▼
           AI Supervisor Core
                     │
                     ▼
           Dynamic Agent Router
                     │
                     ▼
             Agent Execution
                     │
                     ▼
           Live Watchdog System (Loop, Scope, Dangerous Commands)
                     │
                     ▼
           Independent Verification Engine (Ground Truth Tests)
                     │
                     ▼
           Absence Policy Engine
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
Continue to Next Task       Pause / Emergency Stop / Notify
```

### Core Invariants:
1. **Continuity, Not Authority**: Absence Mode permits the system to advance planned tasks unattended, but never expands what the system is permitted to do beyond pre-authorized bounds.
2. **Deterministic Safety Over Autonomy**: If a lower-level safety watchdog (e.g. dangerous command guard, scope monitor, worktree jail) flags an action, Absence Mode cannot override it. Safety always wins.
3. **Deterministic Authority**: All authority checks are evaluated deterministically in code; no LLM is ever permitted to make final authorization decisions.
4. **Agent Completion ≠ Verified Completion**: An agent claiming completion never completes an absence mission until the Independent Verification Engine executes ground truth checks and produces an `ACCEPT` verdict.

---

## 2. Authority Hierarchy

The decision engine evaluates authority in strict hierarchical sequence:

```text
1. Hard Safety Restrictions (Dangerous commands, secret paths, system dirs)
       ↓
2. User Absence Policy (Explicit snapshot authorized by operator)
       ↓
3. Supervisor Engine Rules (Watchdog rules, worktree confinement)
       ↓
4. Task Constraints (Declared task scope and input constraints)
       ↓
5. Agent Capabilities (Registered adapter capability bounds)
       ↓
6. Agent Request (Command execution or file mutation)
```

**Zero Self-Escalation**: An agent request can never broaden any layer above it. If an agent attempts to execute commands such as `extend_absence_duration`, `disable_watchdog`, `bypass_verification`, or `modify_absence_policy`, the engine immediately issues a `DENY` decision with rule `security.self_escalation_blocked`.

---

## 3. Policy Model & Conservative Defaults

Absence Mode relies on a structured, immutable policy object (`AbsencePolicy`):

| Policy Field | Default Value | Description / Constraint |
| :--- | :--- | :--- |
| `enabled` | `True` | Whether autonomous operation is armed |
| `max_duration_seconds` | `7200` (2 hours) | Hard wall-clock expiration ceiling (max 24h) |
| `max_tasks` | `5` | Maximum number of verified tasks before pausing |
| `max_handoffs` | `2` | Maximum agent-to-agent handoffs before pausing |
| `max_retries` | `3` | Maximum task retry recovery attempts |
| `max_budget` | `None` | Measurable resource limit (if configured) |
| `allowed_capabilities` | `["code_editing", "testing", "git_operations"]` | Permitted agent capability tags |
| `allowed_paths` | `["*"]` | Path prefixes relative to worktree root |
| `prohibited_paths` | `[".env", ".git", "id_rsa", "credentials"]` | Sensitive paths strictly denied |
| `prohibited_commands` | `["rm -rf", "drop table", "chmod 777", ...]` | Dangerous destructive commands |
| `approval_policy` | `AUTO_APPROVE_WITHIN_POLICY` | Mode for operations inside authorized scope |
| `verification_policy` | `STRICT` | Requires independent verification on all completions |
| `failure_policy` | `PAUSE_AND_NOTIFY` | Action taken when unexpected supervisor fault occurs |
| `notification_policy` | `ACTIONABLE_ONLY` | Surfaces only critical interventions and completions |

---

## 4. Deterministic Lifecycle & State Machine

```text
DISABLED ──► ARMED ──► ACTIVE ──► COMPLETED
               │          │
               │          ├──────► PAUSED ──► ACTIVE
               │          │
               │          ├──────► EXPIRED
               │          │
               │          └──────► BLOCKED (Fail-Closed)
               │
               └───────────────► CANCELLED (Emergency Stop)
```

* **DISABLED**: Absence Mode is inactive; normal interactive mode.
* **ARMED**: User explicitly submitted an absence policy snapshot. Clock has not started.
* **ACTIVE**: Session started, expiration clock running, tasks and decisions permitted within policy.
* **PAUSED**: Autonomous continuation suspended (operator pause, retry limit, or handoff limit reached).
* **EXPIRED**: Current time exceeds `expires_at`. All running agents stopped safely.
* **COMPLETED**: All tasks verified and mission goals successfully achieved.
* **CANCELLED**: Operator triggered Emergency Stop, revoking autonomous continuation.
* **BLOCKED**: Safety integrity violation or critical subsystem missing; fails closed.

---

## 5. Decision Model & Audit Trail

Every authority evaluation generates a structured, immutable record stored in SQLite table `absence_decisions`:

```json
{
  "decision_id": "dec_8f3a921d",
  "absence_id": "abs_001",
  "mission_id": "msn_auth",
  "task_id": "tsk_01",
  "agent_id": "claude-code",
  "decision": "ALLOW",
  "rule_id": "policy.path_allowed",
  "reason": "Target path src/auth.py is within authorized repository scope",
  "action": "write_file",
  "metadata": {"path": "src/auth.py"},
  "timestamp": "2026-10-06T00:15:00Z"
}
```

### Decision Types:
* `ALLOW`: Action complies with safety restrictions and user policy.
* `DENY`: Action violates security boundaries, dangerous command rules, or prohibited paths.
* `PAUSE`: Session has reached a budget, retry, or handoff ceiling; execution halts safely.
* `REQUIRE_USER`: Action requires explicit operator approval before proceeding.

---

## 6. Budget, Retry, and Handoff Limits

Absence Mode integrates directly with Phase 3 Watchdogs, Phase 5 Handoffs, and Phase 6 Dynamic Routing:
1. **Loop & Retry Limit**: If an agent repeatedly fails and triggers watchdog loop detection, retries increment. When `retries_count >= max_retries`, the session immediately transitions to `PAUSED` with reason `"Retry ceiling reached"`.
2. **Handoff Limit**: When an agent fails and hands off context to a secondary agent (e.g. Claude Code ➔ Codex), handoffs increment. When `handoffs_count >= max_handoffs`, further autonomous handoffs halt, transitioning to `PAUSED` with reason `"Handoff limit reached"`.
3. **Hard Expiration Limit**: When `datetime.now() >= expires_at`, `is_expired()` evaluates to True. Any further action transitions status to `EXPIRED`. Running processes are sent safe SIGINT/SIGTERM termination signals.

---

## 7. Restart Durability & Fail-Closed Recovery

Absence state is persisted in SQLite with Write-Ahead Logging (WAL):
* `absence_sessions`: Tracks session state, policy snapshots, task counts, and timestamps.
* `absence_decisions`: Immutable audit trail of every evaluated action.

### Reconcile on Startup:
When the FastAPI backend restarts:
1. `AbsencePolicyEngine.reconcile_on_startup()` queries all active sessions.
2. If `expires_at` was breached during the downtime, the session immediately transitions to `EXPIRED`.
3. If the persisted policy snapshot is corrupted or unparseable, the session transitions to `BLOCKED`.
4. Valid active sessions retain their remaining time window and resume under their original snapshot.

---

## 8. Desktop HUD & Emergency Stop Integration

The Phase 8 Floating HUD and Control Room reflect Absence Mode in real-time:
* **Visual Status**: Shows `ABSENCE MODE` banner, remaining duration (e.g., `1h 45m remaining`), and active policy indicator.
* **Emergency Stop**: The HUD provides a prominent `Stop Absence` action button (`POST /api/missions/{id}/absence/cancel`). Clicking this:
  - Revokes autonomous continuation instantly.
  - Transitions the session to `CANCELLED`.
  - Emits `absence.cancelled`.
  - Halts active agent execution safely.
* **Zero-Nag Notifications**: Surfaces desktop system alerts on:
  - `absence.started`
  - `absence.paused` (e.g. retry or handoff limits hit)
  - `absence.expired`
  - `absence.completed`
  - `absence.blocked`
  Suppresses high-frequency benign file edits and routine command approvals.

---

## 9. Security Invariants (Tested & Verified)

1. **No Agent Self-Escalation**:
   - Agent cannot modify `AbsencePolicy`.
   - Agent cannot extend `expires_at` or `max_duration_seconds`.
   - Agent cannot disable or reconfigure supervisory watchdogs.
   - Agent cannot bypass or self-sign independent verification.
   - Agent cannot grant capabilities to itself or another agent.
2. **Protected Paths**:
   - Access to `.env`, `.git`, SSH keys, or parent directory traversal (`../`) is strictly denied.
3. **Dangerous Command Blacklist**:
   - `rm -rf`, `drop table`, `mkfs`, `dd`, `chmod 777` are blocked unconditionally.
4. **Independent Verification Mandatory**:
   - `Agent says COMPLETE` is untrusted telemetry. Ground truth verification tests must execute independently and return `ACCEPT`.

---

## 10. Known Limitations (Phase 9 Scope)
* **Single Active Session per Mission**: A mission may have only one active absence session at a time.
* **No Fleet Beyond Phase 5**: Phase 9 works with existing Claude Code and OpenAI Codex adapters; future provider adapters belong to Phase 10.
* **No Remote Cloud Override**: Autonomous execution runs locally on the host machine; multi-device cloud synchronization is reserved for Phase 12.
