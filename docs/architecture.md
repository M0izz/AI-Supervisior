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
