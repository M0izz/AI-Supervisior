# Work Protocol v1 Specification

## Overview

**Work Protocol v1** establishes the canonical, typed communication contract for AI Supervisor. It provides a model-agnostic, runtime-independent boundary between the Supervisor control plane and diverse agent execution engines (internal Worker, future Claude Code, OpenAI Codex, Gemini CLI, local models, etc.).

All protocol definitions are located under [`core/protocol/`](file:///c:/Users/Moiz/Desktop/AI%20Supervisior/core/protocol).

---

## 1. Package Structure

```
core/protocol/
├── __init__.py         # Package exports
├── schema.py           # WorkProtocolEvent and TaskDispatchPackage models
├── events.py           # ProtocolEventType enumeration
├── actions.py          # ActionType, ActionInfo, and TelemetryInfo models
└── validators.py       # Pydantic validation utilities and error classes
```

---

## 2. Event Envelope (`WorkProtocolEvent`)

The standard envelope captures event identity, actor attribution, structured action data, resource telemetry, and contextual payloads:

```python
class WorkProtocolEvent(BaseModel):
    schema_version: str = "1.0.0"
    event_id: str                          # Format: evt_<12 hex chars>
    mission_id: str                        # Mandatory mission identifier
    task_id: Optional[str] = None          # Scoped task identifier
    agent_id: Optional[str] = None         # Executing agent identifier
    provider: str = "internal"             # internal, claude, codex, gemini, etc.
    timestamp: datetime                    # UTC timestamp
    event_type: str                        # Canonical lifecycle event type
    action: Optional[ActionInfo] = None    # Action details (if action executed)
    telemetry: Optional[TelemetryInfo] = None # Resource usage, tokens, duration
    payload: Dict[str, Any] = {}           # Flexible structured metadata
```

---

## 3. Typed Lifecycle Events (`ProtocolEventType`)

Work Protocol v1 defines typed lifecycle milestones across core subsystems:

| Category | Event Types |
| :--- | :--- |
| **Mission** | `mission.created`, `mission.completed`, `mission.failed` |
| **Task** | `task.created`, `task.started`, `task.completed` |
| **Agent Lifecycle** | `agent.connected`, `agent.disconnected`, `agent.started`, `agent.paused`, `agent.resumed`, `agent.stopped` |
| **Agent Action** | `agent.action.executed`, `agent.tool_called` |
| **Filesystem** | `file.changed` |
| **Command Execution** | `command.started`, `command.completed` |
| **Testing** | `test.started`, `test.passed`, `test.failed` |
| **Supervision & Recovery** | `supervisor.intervened`, `handoff.created`, `recovery.started`, `recovery.completed` |
| **Verification** | `verification.started`, `verification.passed`, `verification.failed` |
| **Human Approvals** | `approval.requested`, `approval.granted`, `approval.denied` |

---

## 4. Action & Telemetry Models

### `ActionInfo`
Represents an action performed by an agent:
- `action_type`: Category (`tool_call`, `file_read`, `file_write`, `file_delete`, `command_execute`, `api_call`, `human_prompt`, `handoff`, `custom`).
- `target`: Action target (path, command line, or tool name).
- `parameters`: Arguments supplied to the action.
- `result`: Execution result or error snippet.
- `exit_code`: Numeric exit code (if applicable).
- `affected_files`: List of modified or created file paths.

### `TelemetryInfo`
Tracks operational and cost metrics across provider backends:
- `input_tokens`: Prompt token count.
- `output_tokens`: Completion token count.
- `cost`: Estimated monetary cost in USD.
- `duration`: Execution duration in seconds.
- `exit_status`: Operational status (`success`, `error`, `timeout`, `aborted`).

---

## 5. Task Dispatch Package (`TaskDispatchPackage`)

The task dispatch package defines the strict isolation boundary between the Supervisor and any agent runtime:

```python
class TaskDispatchPackage(BaseModel):
    schema_version: str = "1.0.0"
    dispatch_id: str                      # Format: dsp_<12 hex chars>
    task_id: str                          # Target task identifier
    mission_id: str                       # Mission identifier
    objective: str                        # Clear, verifiable objective prompt
    dependencies: List[str] = []          # Completed prerequisite task IDs
    workspace: str                        # Isolated task directory / worktree
    allowed_files: List[str] = []         # Whitelist file patterns for scope
    permissions: Dict[str, Any] = {       # Sandboxing permissions
        "read_filesystem": True,
        "write_filesystem": True,
        "execute_terminal": True,
        "allow_network": False,
    }
    budget: Optional[Dict[str, float]]    # Optional token/cost/iteration limits
    timeout: Optional[float] = 300.0      # Task execution timeout in seconds
    context: Dict[str, Any] = {}          # Injected instructions and memory
    verification_requirements: List[str]  # Verification commands (e.g. pytest)
```

---

## 6. Validation Rules

All protocol models are validated using [`core.protocol.validators`](file:///c:/Users/Moiz/Desktop/AI%20Supervisior/core/protocol/validators.py):
1. **Schema Version Compatibility**: Major version must match `1.x.x`.
2. **Identity Integrity**: `mission_id` and `event_type` (for events) or `task_id` and `workspace` (for dispatch) must be non-empty strings.
3. **Extensibility**: Models allow additional metadata keys via `extra="allow"` to accommodate future provider-specific payloads without breaking deserialization.

---

## 7. External Agent Adapter Normalization (Phase 2)

External agent runtimes (Claude Code, OpenAI Codex, etc.) are decoupled from the Supervisor core via [`AgentAdapter`](file:///c:/Users/Moiz/Desktop/AI%20Supervisior/adapters/base.py).

When an external adapter runs:
1. It receives a validated `TaskDispatchPackage`.
2. It executes inside an isolated Git worktree (`.supervisor/worktrees/`).
3. It normalizes observed process milestones into standard `WorkProtocolEvent` envelopes:
   - Process launch: `agent.started` + `command.started`
   - File edits: `file.changed` with `ActionInfo(action_type="file_write")`
   - Successful completion: `task.completed` + `command.completed` with `TelemetryInfo(exit_status="success")`
   - Failure: `test.failed` with exit code and error diagnostics
   - Timeout/Cancel: `agent.stopped` with `exit_status="timeout"` / `"cancelled"`
4. Events stream to the live `EventBus` and are durably persisted into SQLite WAL tables.

---

## 8. Live Supervisory Watchdogs Integration (Phase 3)

The Supervisor consumes the canonical `WorkProtocolEvent` stream passively via `WatchdogEngine` without coupling to adapter internals:

```text
ClaudeCodeAdapter
       ↓
WorkProtocolEvent (file.changed, command.started, test.failed)
       ↓
  EventBus
       ↓
WatchdogEngine
       ↓
WatchdogDecision (ALLOW / CANCEL / REQUIRE_APPROVAL)
       ↓
InterventionController
       ↓
ClaudeCodeAdapter.cancel() (if violated)
```

1. **Passive Evaluation**: Events are inspected as untrusted data without triggering recursive command executions or arbitrary shell evaluations.
2. **Deterministic Rules**: `LOOP_DETECTED` (normalized error signatures $\times 3$), `SCOPE_VIOLATION` (out-of-bounds files or directory traversal), `DANGEROUS_COMMAND` (prohibited shell/SQL commands), and `BUDGET_EXCEEDED` / `TIMEOUT_EXCEEDED`.
3. **Structured Intervention**: Generates `supervisor.intervened` events with audit records, published onto the `EventBus` and persisted to SQLite WAL storage.


