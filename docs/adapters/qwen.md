# Qwen / Local Runtime Adapter

## Overview

The `QwenAdapter` brings local open-weights model supervision to AI Supervisor. It enables the Supervisor to supervise local or on-premise execution models (such as `Qwen2.5-Coder` running via local inference runtimes, Ollama, vLLM, llama.cpp, or local CLI wrappers) without relying on external hosted APIs.

---

## Local Security Boundary: Untrusted Execution

**Core Principle**: Local does not mean trusted.

Code emitted or executed by a local model is treated as completely untrusted. AI Supervisor enforces:
- Worktree containment: No access to the primary repository root.
- Scope restrictions: Watched file boundaries.
- Dangerous command interception: Blocked destructive shell operations.
- Supervisory watchdogs: Infinite loop detection and budget constraints.
- Independent verification: Verification must pass before task completion is accepted.

---

## Architecture & Lifecycle

The adapter implements the standard `AgentAdapter` contract:

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
- **Provider**: `alibaba` (Qwen local runtime)
- **Adapter ID**: `qwen`
- **Display Name**: `Qwen Local Runtime`
- **Capabilities**:
  - `code_execution`
  - `filesystem_read`
  - `filesystem_write`
  - `terminal_execution`
  - `git`
  - `test_execution`
  - `local_model`

### 2. Workspace Isolation
Worktree checks prevent any execution outside `.supervisor/worktrees`.

### 3. Execution Safety & Process Model
- Executed via `asyncio.create_subprocess_exec` with `shell=False`.
- Output bounded to prevent buffer bloat.
- Work Protocol v1 events normalized identically to remote providers.

### 4. Cancellation & Timeouts
- Supported via async process group termination.

---

## Availability Probing & Diagnostics

The adapter probes:
1. `executable_override` (for deterministic test mocks).
2. `QWEN_EXECUTABLE` or system `PATH` (`qwen`, `ollama`).
3. If using HTTP/OpenAI-compatible inference server: probes `QWEN_BASE_URL` health endpoint.
4. If unavailable, returns `AdapterAvailability(available=False, status=NOT_INSTALLED)`.

---

## Environment Configuration

| Variable | Description | Default |
|---|---|---|
| `QWEN_COMMAND` / `QWEN_EXECUTABLE` | Local executable or CLI tool | `qwen` on PATH |
| `QWEN_MODEL` | Target local model | `qwen2.5-coder` |
| `QWEN_BASE_URL` | Local OpenAI-compatible server URL | `http://localhost:11434/v1` |
| `RUN_REAL_QWEN_TESTS` | Flag to enable live local smoke test | Unset (skipped) |
