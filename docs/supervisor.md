# Supervisor Engine & Policy Specification

## 1. Supervisor State Machine

```
              ┌───────────────┐
              │    PENDING    │
              └───────┬───────┘
                      │ start_mission
                      ▼
              ┌───────────────┐
              │    RUNNING    │◄──────────────────────────┐
              └───────┬───────┘                           │
                      │                                   │
         ┌────────────┼───────────────┬────────────────┐  │
         │ progress   │ loop / drift  │ danger/policy  │  │ recovery
         ▼            ▼               ▼                │  │
    ┌─────────┐ ┌───────────────┐ ┌────────┐           │  │
    │ RUNNING │ │ INVESTIGATING │ │ PAUSED │           │  │
    └─────────┘ └───────┬───────┘ └────┬───┘           │  │
                        │              │ human approval│  │
                        ▼              ▼               │  │
                 ┌─────────────┐   ┌────────┐          │  │
                 │   DECISION  ├──►│ RESUME ├──────────┘  │
                 └──────┬──────┘   └────────┘             │
                        │                                 │
                        ├─► CHANGE_STRATEGY ──────────────┤
                        ├─► DELEGATE (Reviewer) ──────────┘
                        ├─► ROLLBACK
                        └─► ESCALATE (Human Approval)
```

## 2. Action Space

| Action | Description | When Triggered |
|---|---|---|
| `CONTINUE` | Worker proceeds normally | Normal progress, expected transitions |
| `RETRY` | Re-attempt action | Transient network or environment error |
| `CHANGE_STRATEGY`| Shift approach | Worker attempts same failed technique twice |
| `DELEGATE` | Assign diagnostic/subtask to Reviewer | Repeated failure signature ($\ge 3$ attempts) |
| `ROLLBACK` | Revert git diff to last known good state | Corrupting code edits or broken build |
| `PAUSE` | Halt autonomous execution | Safety violation or human intervention requested |
| `REQUEST_APPROVAL`| Wait for human confirmation | Destructive command or out-of-scope edits |
| `COMPLETE` | Conclude mission | Empirical verification confirmed |

## 3. Nemotron Structured Output Format

```json
{
  "decision": "DELEGATE",
  "severity": "medium",
  "reason": "The worker repeated the same approach without changing the failure signature.",
  "confidence": 0.91,
  "recommended_action": "Delegate diagnosis to reviewer agent with focus on UTF-8 BOM encoding.",
  "target_agent": "reviewer_01"
}
```
