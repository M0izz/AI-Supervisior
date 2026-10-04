# Agent Handoff Engine

## Overview

The **Handoff Engine** (`core/handoff/`) enables AI Supervisor to recover from agent failures, stalls, and verification rejections by transferring active task execution from a failing source agent (e.g. Claude Code) to an alternate compatible target agent (e.g. OpenAI Codex).

---

## Core Product Invariant

> **A handoff transfers responsibility, not authority.**

- Agents do not negotiate handoffs directly with each other.
- The Supervisor alone retains authority over task status, worktree boundaries, context packaging, and completion verification.
- A handoff **does not complete the task**. Upon transfer, task status remains `IN_PROGRESS`.
- Task completion **always** requires independent termination through the Phase 4 `VerificationEngine` (`ACCEPT`).

---

## Architecture Flow

```text
                  ┌────────────────────┐
                  │     SUPERVISOR     │
                  └─────────┬──────────┘
                            │
               ┌────────────┴────────────┐
               │                         │
           Agent A                  Handoff Engine
         Claude Code                     │
               │                         │
               └── Watchdog Anomaly ────┤
                   Verification Reject   │
                                         ↓
                                   Handoff Decision
                                         │
                                  Context Package
                                 (Provenance-Tagged)
                                         │
                                         ↓
                                      Agent B
                                    OpenAI Codex
                                         │
                                         ↓
                                  Independent Verification
                                  (ACCEPT / REJECT / REVIEW)
```

---

## Deterministic Handoff Triggers

AI Supervisor triggers handoffs based on objective conditions:

1. **Trigger A — Repeated Failure (`REPEATED_FAILURE`)**:
   Watchdog loop detection detects identical error signatures or stagnant progress repeating across multiple attempts.
2. **Trigger B — Verification Rejection (`VERIFICATION_FAILURE`)**:
   The primary agent claims completion, but the independent `VerificationEngine` rejects the claim due to failing tests, uncommitted changes, or scope violations.
3. **Trigger C — Agent Failure / Crash (`AGENT_FAILURE`)**:
   The agent process exits unexpectedly, crashes, or times out, but the supervisor determines the task remains recoverable.
4. **Trigger D — Operator Request (`MANUAL`)**:
   An operator manually reassigns the task to another agent runtime.

---

## Handoff Policy & Eligibility

Before executing a handoff, `HandoffEngine.can_handoff()` verifies:
1. **Loop Protection**: Sequential handoff count has not exceeded `max_handoffs_per_task` (default: 3).
2. **Registry Configuration**: `AdapterRegistry` is active.
3. **Target Availability**: Target agent adapter is registered and healthy (`check_availability().available == True`).
4. **Worktree Validity**: The isolated Git worktree exists and is intact.

If any check fails:
- The handoff is `REJECTED`.
- A critical `SUPERVISOR_HUMAN_REQUIRED` event is emitted.
- The task is flagged for human review or failed, preventing infinite agent-to-agent ping-pong loops.

---

## Provenance-Separated Context Package

A handoff context package (`HandoffContextPackage`) guarantees that the receiving agent receives only verified, actionable evidence rather than raw unverified logs:

```python
class FactProvenance(str, Enum):
    VERIFIED = "VERIFIED"        # Empirically proven by verifier or deterministic git status
    UNVERIFIED = "UNVERIFIED"    # Claimed by source agent without empirical proof
    REJECTED = "REJECTED"        # Strategies/signatures proven to fail
```

- **Verified Facts**: Git worktree path, verified modified files, established environmental constraints.
- **Unverified Claims**: Unverified self-assessment statements from the source agent.
- **Rejected Attempts**: Prior failure signatures, failed test outputs, and watchdog anomaly records.
- **Remaining Work**: Concise instructions focusing on unmet objectives and scope bounds.

---

## Worktree Continuity

The target agent operates in the **exact same isolated Git worktree** created for the task:
- No changes are leaked to the primary repository root.
- Uncorrupted partial edits made by the source agent are retained.
- The target agent inherits the same branch and scope restrictions.

---

## SQLite WAL Durability & Lifecycle Events

Every handoff is recorded in the `handoffs` table with full context payloads and timestamps:
- `handoff.requested`
- `handoff.prepared`
- `handoff.started`
- `handoff.completed`
- `handoff.failed`
