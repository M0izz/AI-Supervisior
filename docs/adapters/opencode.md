# OpenCode Adapter

## Overview

The `OpenCodeAdapter` integrates the OpenCode agent CLI runtime with AI Supervisor's supervisory architecture.

It conforms strictly to the `AgentAdapter` contract, ensuring that OpenCode can participate in capability-based dynamic routing, live watchdog supervision, handoffs, and independent verification.

---

## Architecture & Lifecycle

The adapter implements:

```text
identity()
capabilities()
check_availability()
prepare()
execute()
cancel()
status()
cleanup()
```

### 1. Identity & Capabilities
- **Provider**: `opencode`
- **Adapter ID**: `opencode`
- **Display Name**: `OpenCode CLI`
- **Capabilities**:
  - `code_execution`
  - `filesystem_read`
  - `filesystem_write`
  - `terminal_execution`
  - `git`
  - `test_execution`

### 2. Workspace Isolation
Executes strictly within `.supervisor/worktrees`.

### 3. Execution Safety & Process Model
- Executed via `asyncio.create_subprocess_exec` with `shell=False`.
- Output is bounded (`MAX_OUTPUT_BUFFER_LINES = 1,000`).
- Translates runtime progress into normalized Work Protocol v1 events.

### 4. Cancellation & Timeouts
- Strict process cleanup to eliminate orphan processes.

---

## Availability Probing & Diagnostics

The adapter determines availability:
1. `executable_override` (for deterministic mock fixtures).
2. `OPENCODE_EXECUTABLE` or system `PATH` resolution (`opencode`, `opencode.cmd`, `opencode.exe`).
3. If absent, returns `AdapterAvailability(available=False, status=NOT_INSTALLED)`.

---

## Environment Configuration

| Variable | Description | Default |
|---|---|---|
| `OPENCODE_EXECUTABLE` | Path to `opencode` CLI | `opencode` on PATH |
| `OPENCODE_MODEL` | Target underlying model | Default CLI model |
| `RUN_REAL_OPENCODE_TESTS` | Flag to enable live OpenCode smoke test | Unset (skipped) |
