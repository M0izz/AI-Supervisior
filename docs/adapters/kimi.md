# Moonshot Kimi Adapter

## Overview

The `KimiAdapter` connects the Moonshot Kimi CLI runtime to AI Supervisor, allowing Kimi to be supervised as a first-class execution provider.

Like all AI Supervisor adapters, Kimi is untrusted and strictly isolated from the primary repository.

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
- **Provider**: `moonshot`
- **Adapter ID**: `kimi`
- **Display Name**: `Moonshot Kimi CLI`
- **Capabilities**:
  - `code_execution`
  - `filesystem_read`
  - `filesystem_write`
  - `terminal_execution`
  - `git`
  - `test_execution`
  - `documentation`

### 2. Workspace Isolation
Strict worktree isolation enforced during `prepare()`.

### 3. Execution Safety & Process Model
- Subprocess invocation using `asyncio.create_subprocess_exec` with `shell=False`.
- Output streaming bounded by line count and maximum length.
- Normalized Work Protocol events:
  - `agent.started`
  - `command.started`
  - `file.edited`
  - `command.completed`
  - `agent.completed` / `agent.failed`

### 4. Cancellation & Timeouts
- Immediate cancellation and graceful SIGTERM -> SIGKILL tree termination.

---

## Availability Probing & Diagnostics

The adapter determines availability:
1. `executable_override` (for deterministic mock fixtures).
2. `KIMI_EXECUTABLE` or system `PATH` resolution (`kimi`, `kimi.cmd`, `kimi.exe`).
3. Authentication probing: verifies `MOONSHOT_API_KEY` or `KIMI_API_KEY` is present.
4. If missing, reports `AdapterAvailability(available=False, status=NOT_INSTALLED or NOT_CONFIGURED)`.

---

## Environment Configuration

| Variable | Description | Default |
|---|---|---|
| `KIMI_EXECUTABLE` | Path to `kimi` executable | `kimi` on PATH |
| `MOONSHOT_API_KEY` | Moonshot Kimi API token | None |
| `KIMI_MODEL` | Target Kimi model | `moonshot-v1-auto` |
| `RUN_REAL_KIMI_TESTS` | Flag to enable live Kimi smoke test | Unset (skipped) |
