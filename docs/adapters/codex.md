# OpenAI Codex Adapter

## Overview

The `CodexAdapter` provides production-grade integration with OpenAI's Codex CLI, conforming strictly to the universal `AgentAdapter` interface defined in `adapters/base.py`.

It functions as the second production-ready worker runtime in AI Supervisor alongside `ClaudeCodeAdapter`, enabling multi-agent handoffs, fault isolation, and task recovery.

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
- **Provider**: `openai`
- **Adapter ID**: `codex`
- **Display Name**: `OpenAI Codex`
- **Capabilities**:
  - `code_execution`
  - `filesystem_read`
  - `filesystem_write`
  - `terminal_execution`
  - `git`
  - `test_execution`

### 2. Workspace Isolation
Like all adapters managed by AI Supervisor, Codex is strictly forbidden from running directly against the primary repository root:
- The adapter validates that `dispatch.workspace` is an isolated Git worktree managed by `GitWorktreeManager`.
- If an attempt is made to execute in the repository root or outside `.supervisor/worktrees`, `prepare()` immediately raises a `ValueError`, resulting in a safe `AdapterExecutionResult(status=FAILED)`.

### 3. Execution Safety & Process Model
- Executed via `asyncio.create_subprocess_exec` with `shell=False`.
- Output streaming from stdout/stderr is bounded to `MAX_OUTPUT_BUFFER_LINES` (1,000 lines) and `MAX_LINE_LENGTH` (4,000 characters) to prevent memory exhaustion from runaway loops.
- Emits normalized Work Protocol v1 events:
  - `agent.started`
  - `command.started`
  - `file.edited`
  - `command.completed`
  - `agent.completed` / `agent.failed`

### 4. Cancellation & Timeouts
- Strict per-task timeout enforcement via `asyncio.wait_for`.
- Process tree termination on Windows via `taskkill /F /T /PID <pid>` and POSIX `SIGTERM`/`SIGKILL` process group signalling.

---

## Availability Probing

The adapter detects CLI presence dynamically:
1. Respects `executable_override` (e.g. for deterministic mock/fake testing).
2. Inspects `CODEX_EXECUTABLE` environment variable.
3. Searches system `PATH` for `codex` or `codex.exe`.
4. If unavailable, returns `AdapterAvailability(available=False, status=NOT_INSTALLED)`. The system degrades safely without crashing.

---

## Handoff Context Ingestion

When Codex receives a task transferred from Claude Code, the `TaskDispatchPackage` injects the structured `HandoffContextPackage` into `dispatch.context["handoff"]`:
- `objective`: Clean definition of remaining goals.
- `verified_facts`: Established empirical facts from prior runs and worktree inspections.
- `rejected_attempts`: Approaches proven to fail (e.g. error signatures from the previous agent).
- `allowed_scope`: Whitelist of permitted files.

Codex builds directly upon the existing worktree state without corrupting or restarting from scratch.
