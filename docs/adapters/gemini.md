# Google Gemini CLI Adapter

## Overview

The `GeminiAdapter` provides production-grade integration with Google's Gemini CLI runtime, conforming strictly to the universal `AgentAdapter` interface in `adapters/base.py`.

It enables AI Supervisor to orchestrate Gemini alongside Claude Code, Codex, and other providers without modifying core supervisory business logic.

---

## Architecture & Lifecycle

The adapter implements the universal lifecycle contract:

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
- **Provider**: `google`
- **Adapter ID**: `gemini`
- **Display Name**: `Google Gemini CLI`
- **Capabilities**:
  - `code_execution`
  - `filesystem_read`
  - `filesystem_write`
  - `terminal_execution`
  - `git`
  - `test_execution`
  - `documentation`
  - `web_access`
  - `multimodal`

### 2. Workspace & Worktree Isolation
Like all adapters managed by AI Supervisor:
- Execution is strictly contained within isolated Git worktrees (`.supervisor/worktrees/...`).
- Attempts to target primary repository roots or traverse outside the designated worktree are immediately rejected during `prepare()`.

### 3. Execution Safety & Process Model
- Executed via `asyncio.create_subprocess_exec` with `shell=False`.
- Output streaming from stdout/stderr is bounded (`MAX_OUTPUT_BUFFER_LINES = 1,000`, `MAX_LINE_LENGTH = 4,000`) to prevent runaway log flooding.
- Emits normalized Work Protocol v1 events:
  - `agent.started`
  - `command.started`
  - `file.edited`
  - `command.completed`
  - `agent.completed` / `agent.failed`

### 4. Cancellation & Timeouts
- Timeout-bounded via `asyncio.wait_for`.
- Clean process tree teardown on Windows (`taskkill /F /T /PID`) and POSIX (`SIGKILL`).
- Prevents orphaned processes on cancellation or watchdog intervention.

---

## Availability Probing & Diagnostics

The adapter determines availability truthfully:
1. `executable_override` (for deterministic mock testing).
2. `GEMINI_EXECUTABLE` or system `PATH` resolution (`gemini`, `gemini.cmd`, `gemini.exe`).
3. Authentication checks (`GEMINI_API_KEY` or Google Application Default Credentials via `GOOGLE_APPLICATION_CREDENTIALS`).
4. If missing, reports `AdapterAvailability(available=False, status=NOT_INSTALLED or NOT_CONFIGURED)` with diagnostic messages.

---

## Environment Configuration

| Variable | Description | Default |
|---|---|---|
| `GEMINI_EXECUTABLE` | Explicit path to `gemini` executable | `gemini` on PATH |
| `GEMINI_API_KEY` | Gemini API key | None |
| `GOOGLE_APPLICATION_CREDENTIALS` | ADC service account path | None |
| `GEMINI_MODEL` | Target Gemini model | `gemini-1.5-pro` |
| `RUN_REAL_GEMINI_TESTS` | Flag to enable live provider smoke test | Unset (skipped) |
