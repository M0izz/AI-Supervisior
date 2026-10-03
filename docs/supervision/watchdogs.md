# Supervisory Watchdogs Architecture (Phase 3)

## 1. Overview & Core Product Invariant

> **The agent is not allowed to supervise itself. The Supervisor observes and controls the agent independently.**

In Phase 3, AI Supervisor connects deterministic supervisory watchdogs directly to the live external-agent execution stream (`WorkProtocolEvent`). The external agent runtime (e.g. Claude Code CLI) executes within an isolated Git worktree and emits protocol events. The Supervisor passively intercepts these events, evaluates deterministic safety and reliability rules without LLM non-determinism, generates structured `WatchdogDecision` records, and directs the `InterventionController` to halt rogue or looping execution.

```text
Supervisor Dispatch
        ↓
 Claude Code CLI (in Git worktree)
        ↓
  WorkProtocolEvent
        ↓
     EventBus
        ↓
   WatchdogEngine (Deterministic Evaluation)
        ↓
  WatchdogDecision (ALLOW / WARN / CANCEL / REQUIRE_APPROVAL)
        ↓
InterventionController (Idempotent Action Dispatch)
        ↓
 AgentAdapter.cancel() (Graceful / Escalated Subprocess Kill)
        ↓
  Audit Trail & SQLite WAL Persistence (supervisor.intervention)
```

---

## 2. Watchdog Rules & Evaluation Pipeline

The watchdog evaluation layer operates **deterministically** without calling LLMs for safety decisions:

| Rule ID | Monitored Event | Condition / Pattern | Recommended Action |
| :--- | :--- | :--- | :--- |
| `DANGEROUS_COMMAND` | `command.started` | Matches prohibited destructive CLI or SQL patterns (e.g. `rm -rf /`, `DROP TABLE`, `mkfs`, `kill -9`) | `CANCEL` or `REQUIRE_APPROVAL` |
| `SCOPE_VIOLATION` | `file.changed` | File path outside authorized task scope, path traversal attempt (`..`), or protected files (`.git/`, `.env`) | `CANCEL` |
| `LOOP_DETECTED` | `test.failed`, `task.failed` | 3 consecutive failures with identical normalized error signature | `CANCEL` |
| `BUDGET_EXCEEDED` | `command.started`, `agent.action` | Tool execution count exceeds task's configured `max_iterations` | `CANCEL` |
| `TIMEOUT_EXCEEDED` | All events | Monotonic elapsed task execution time exceeds timeout budget | `CANCEL` |
| `PERMITTED` | All events | Action satisfies all policy constraints | `ALLOW` |

---

## 3. Normalized Error Signature Loop Detection

Loop detection does not perform naive raw string comparison. It abstracts dynamic runtime artifacts such as hexadecimal memory addresses (`0x7fff5fbff...`) and file line numbers (`auth.py:42` vs `auth.py:99`) using `DeterministicRuleEngine.normalize_signature()`:

```text
Attempt 1: AssertionError: Token validation returned 403 Forbidden at auth.py:101
Attempt 2: AssertionError: Token validation returned 403 Forbidden at auth.py:245
Attempt 3: AssertionError: Token validation returned 403 Forbidden at auth.py:310
                             ↓
              Normalized: Token validation returned 403 Forbidden
                             ↓
                   3 Consecutive Failures
                             ↓
                     LOOP_DETECTED
                             ↓
                 Claude Code Process Cancelled
```

---

## 4. Intervention Controller & Idempotency

The `InterventionController` separates policy evaluation from adapter process manipulation:

- **Decoupled Architecture**: Watchdog rules never directly reference `subprocess` or `ClaudeCodeAdapter`. They produce an abstract `WatchdogDecision`.
- **Idempotency Guard**: Once a task receives a terminal intervention (`CANCEL`), subsequent events emitted during process teardown are ignored to prevent recursive cancellation cascades.
- **Audit Persistence**: Every intervention generates an `InterventionRecord` with unique `intervention_id`, timestamp, rule violated, and evidence, published to the `EventBus` and saved to SQLite WAL storage.

---

## 5. Critical Distinction: Detection vs. Prevention

| Dimension | Architecture Reality |
| :--- | :--- |
| **Worktree File Operations** | **Detected upon stream arrival**. The agent runs inside an isolated Git worktree; file changes are observed as emitted events. If unauthorized, the agent is cancelled immediately to prevent further modification. Host repositories remain protected. |
| **Command Execution** | **Detected at process start**. Observed commands are inspected as untrusted strings. Destructive patterns trigger immediate cancellation and operator approval gates. |
| **Cancellation vs True Pause** | **Cooperative stop / process cancellation**. Claude Code CLI does not expose an OS freeze/resume primitive; interventions gracefully terminate the subprocess (`SIGINT` then `SIGKILL` on POSIX, `taskkill /T /F` on Windows). |

---

## 6. What Phase 3 Intentionally Does NOT Implement

To maintain strict architectural boundaries:
- **No LLM-based Safety Decisions**: Watchdogs are strictly rule-based and deterministic.
- **No Hand-off Engine**: Interventions halt the task; they do NOT automatically route to OpenAI Codex or Gemini (Phase 5).
- **No Independent Verifier**: Phase 3 detects failures and loops; it does not verify solution correctness (Phase 4).
- **No UI Redesign**: Interventions flow through existing event subscriptions and SQLite repositories.
