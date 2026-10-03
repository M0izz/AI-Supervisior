# Claude Code Agent Adapter

## 1. Overview

The **Claude Code Adapter** ([`adapters/claude_code.py`](file:///c:/Users/Moiz/Desktop/AI%20Supervisior/adapters/claude_code.py)) is the first production-grade external agent adapter in AI Supervisor. It implements the universal [`AgentAdapter`](file:///c:/Users/Moiz/Desktop/AI%20Supervisior/adapters/base.py) contract, enabling the Supervisor to dispatch work to Anthropic's Claude Code while maintaining complete filesystem isolation, observable event streaming, and process lifecycle supervision.

```
                    AI SUPERVISOR
                          │
                 TaskDispatchPackage
                          │
                          ▼
                     AgentAdapter
                          │
                          ▼
                  ClaudeCodeAdapter
                          │
                 ┌────────┴────────┐
                 │                 │
            Git Worktree      Claude Code
          (.supervisor/...)   (Subprocess)
                 │                 │
                 └────────┬────────┘
                          │
                          ▼
                  WorkProtocolEvent
                          │
                          ▼
                  EventBus / SQLite
```

---

## 2. Universal Adapter Contract

The Claude Code adapter conforms strictly to the generic [`AgentAdapter`](file:///c:/Users/Moiz/Desktop/AI%20Supervisior/adapters/base.py) abstraction:

```python
class AgentAdapter(ABC):
    @property
    def identity(self) -> AdapterIdentity: ...

    @property
    def capabilities(self) -> List[str]: ...

    async def check_availability(self) -> AdapterAvailability: ...
    async def prepare(self, dispatch: TaskDispatchPackage) -> bool: ...
    async def execute(self, dispatch: TaskDispatchPackage) -> AdapterExecutionResult: ...
    async def cancel(self, task_id: str) -> bool: ...
    async def status(self, task_id: str) -> AdapterProcessStatus: ...
    async def cleanup(self, task_id: str) -> None: ...
```

---

## 3. Capability Model

The adapter declares its supported execution capabilities via [`AdapterCapability`](file:///c:/Users/Moiz/Desktop/AI%20Supervisior/adapters/models.py):

| Capability | Supported | Notes |
| :--- | :--- | :--- |
| `code_execution` | Yes | Claude Code autonomously writes and executes code |
| `filesystem_read` | Yes | Reads files within assigned worktree |
| `filesystem_write` | Yes | Modifies files within declared task scope |
| `terminal_execution` | Yes | Executes shell commands, builders, and scripts |
| `git` | Yes | Uses Git status, diff, and commit commands |
| `test_execution` | Yes | Executes unit tests (pytest, jest, etc.) |

---

## 4. Worktree Isolation & Protection

The worktree boundary is **non-negotiable**:
1. **Primary Repository Protection**: The adapter strictly verifies that the task workspace does NOT match the primary repository root (`repo_root`). Any execution targeting the primary working tree is rejected immediately.
2. **Containment Verification**: The workspace must resolve strictly inside the supervisor worktree base directory (`.supervisor/worktrees/`).
3. **Strict Git Enforcement**: If Git isolation cannot be established or the worktree directory is missing, the adapter fails explicitly with a detailed diagnostic rather than falling back to an unisolated directory sandbox.

---

## 5. Process Lifecycle & Execution

Processes are launched using `asyncio.create_subprocess_exec` with explicit argument arrays:
- **No Shell Injection**: `shell=False` is enforced unconditionally; user objectives and parameters are never concatenated into shell strings.
- **Asynchronous Output Streaming**: `stdout` and `stderr` are consumed line-by-line via asynchronous stream readers.
- **Bounded Buffer**: Output is capped at 500 lines / 64KB in memory to prevent unbounded memory growth during verbose builds or infinite loops.
- **Timeout Management**: Tasks exceeding `dispatch.timeout` are gracefully signaled with `SIGTERM`, escalated to `SIGKILL` if uncooperative after 2 seconds, and assigned `AdapterProcessStatus.TIMED_OUT`.
- **Cancellation**: Explicit supervisor cancellations signal the active subprocess and transition status to `CANCELLED` while preserving the worktree for debugging.

---

## 6. Work Protocol Event Normalization

Process actions and milestones are mapped to canonical [`WorkProtocolEvent`](file:///c:/Users/Moiz/Desktop/AI%20Supervisior/core/protocol/schema.py) types:

| Process Milestone | Work Protocol Event | Payload Content |
| :--- | :--- | :--- |
| Task Launch | `agent.started` | Prompt preview, target executable |
| Subprocess Spawn | `command.started` | Executable command array |
| File Write Detected | `file.changed` | Target path, action type `file_write` |
| Successful Exit (0) | `task.completed` + `command.completed` | Exit code 0, duration, affected files |
| Non-Zero Exit | `test.failed` | Exit code, stderr excerpt |
| Process Timeout | `agent.stopped` | Reason, duration, exit status `timeout` |
| Cancellation | `agent.stopped` | Exit status `cancelled` |

---

## 7. Security Boundaries & Limitations

### What is Enforced
1. **No Command Injection**: All arguments passed via argument arrays to the OS subprocess API without shell interpretation.
2. **Filesystem Containment**: Dispatches outside `.supervisor/worktrees/` are rejected before process spawn.
3. **No Credential Persistence**: Claude Code tokens and `ANTHROPIC_API_KEY` are not written to SQLite tables or event logs.
4. **Untrusted Process Output**: Raw stdout/stderr is treated as untrusted text, truncated, and never executed as commands.

### Transparent Limitations
1. **Network Gating**: Host-level subprocess execution does not enforce kernel network boundaries if `allow_network=False`. For strict network blocking, execution must be paired with Docker container isolation (Phase 5).
2. **Structured Claude Telemetry**: The Claude CLI emits human-oriented console output; deep token accounting relies on provider API receipts or future Claude Agent SDK hooks.

---

## 8. Configuration & Availability Probe

### Environment Variables
- `ANTHROPIC_API_KEY`: Required for real Claude Code API authentication.
- `CLAUDE_CODE_EXECUTABLE`: Optional override path to the `claude` binary.

### Availability Check
`await adapter.check_availability()` executes a lightweight probe:
1. Resolves `claude` binary via `shutil.which`.
2. Inspects `ANTHROPIC_API_KEY` presence without making external network calls.
3. Returns `AdapterAvailability(status, available, message)`.

---

## 9. Testing & Smoke Tests

### Automated Mock Tests
The test suite in [`tests/test_adapters.py`](file:///c:/Users/Moiz/Desktop/AI%20Supervisior/tests/test_adapters.py) executes deterministic fake Claude processes across all platforms (Windows, Linux, macOS) without requiring Anthropic API keys or internet access.

### Optional Real Smoke Test
To run a manual smoke test against an actual installed Claude Code CLI:
```powershell
$env:ANTHROPIC_API_KEY="your-key"
python -m pytest tests/test_adapters.py -k test_real_claude_smoke_test -v
```
If credentials or the CLI are not detected, the test automatically skips safely.
