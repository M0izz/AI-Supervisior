# AI Work Supervisor — Phase 5: Docker-Isolated Agent Execution Layer

## 1. Overview

Phase 5 introduces a unified **Execution Layer** that decouples agent tool dispatching from the underlying host execution environment. Worker and tool operations can seamlessly alternate between:
- **LocalExecutionProvider**: Fast, lightweight development mode using WorkspaceJail and command whitelisting.
- **DockerExecutionProvider**: Hardened container isolation with restricted Linux capabilities, memory/CPU quotas, process limits, and disabled networking.

```text
WorkerAgent / VerifierAgent
           │
           ▼
    Tool Dispatcher
           │
           ▼
    ExecutionManager
           │
  ┌────────┴───────────────────────────┐
  ▼                                    ▼
LocalExecutionProvider        DockerExecutionProvider
(Development / Fallback)       (Production Container Sandbox)
  │                                    │
  ▼                                    ▼
Workspace Subprocess          Ephemeral Container (/workspace)
                              • network: none
                              • cap-drop: ALL
                              • no-new-privileges
                              • limits: CPU, RAM, PIDs
```

The WorkerAgent remains completely agnostic to whether its commands execute locally or within an ephemeral Docker container.

---

## 2. Security Model & Container Hardening

The Docker execution layer guarantees container confinement:

1. **Workspace Boundary Confinement**:
   - The provider mounts **ONLY** the intended task directory (`demo/sample-project`) to `/workspace`.
   - **Host Root Rejection**: Attempts to mount `/`, `C:\`, `C:/`, user home directories (`~`), or system paths (`/etc`, `/var`, `/usr`, Windows system roots) are actively detected and rejected with `PermissionError`.
   - **Docker Socket Isolation**: The host Docker socket (`/var/run/docker.sock` or `//./pipe/docker_engine`) is strictly blocked from container access.

2. **Network Isolation**:
   - By default, `DOCKER_NETWORK_DISABLED=true` enforces `network_mode="none"`. Agents cannot initiate external outbound or inbound network connections.

3. **Least Privilege Enforcement**:
   - Linux capabilities are stripped (`cap_drop=["ALL"]`).
   - Privilege escalation is disabled (`security_opt=["no-new-privileges:true"]`).
   - The container operates as an unprivileged user (`worker`).

4. **Resource Quotas & Exhaustion Protection**:
   - `mem_limit`: Configurable container RAM ceiling (e.g. `512m`).
   - `nano_cpus`: CPU core limit (e.g. `1.0` cores).
   - `pids_limit`: Maximum process/thread creation limit (e.g. `128`) preventing fork bombs.
   - `timeout_seconds`: Hard execution cutoff. Timeouts emit `CONTAINER_LIMIT_EXCEEDED` and terminate the container.

5. **Ephemeral Lifecycle & Automatic Cleanup**:
   - Containers are created per command execution and forcefully destroyed in a `finally:` block upon completion or failure.
   - Emits observable lifecycle events: `container.created`, `container.started`, `container.stopped`, `container.destroyed`.

---

## 3. Configuration & Environment Variables

Configure execution behavior via environment variables or `.env`:

```env
# Execution Backend: 'local' (default) or 'docker'
EXECUTION_BACKEND=local

# Docker Container Settings
DOCKER_IMAGE=ai-work-supervisor-worker:latest
DOCKER_MEMORY_LIMIT=512m
DOCKER_CPU_LIMIT=1.0
DOCKER_PIDS_LIMIT=128
DOCKER_NETWORK_DISABLED=true
DOCKER_TIMEOUT_SECONDS=120

# Safe Fallback: if 'true', falls back to LocalExecutionProvider when Docker daemon is offline
EXECUTION_ALLOW_FALLBACK=false
```

### Fallback Behavior:
- When `EXECUTION_BACKEND=docker` and Docker is unavailable:
  - If `EXECUTION_ALLOW_FALLBACK=false` (default): Returns a structured `ExecutionStatus.ERROR` and emits `execution.failed`. It does **NOT** silently pretend Docker was used.
  - If `EXECUTION_ALLOW_FALLBACK=true`: Emits an `execution.started` event with fallback warning metadata, logs the transition, and executes via `LocalExecutionProvider`.

---

## 4. Building the Worker Docker Image

Build the official reproducible worker image using Docker:

```bash
docker build -t ai-work-supervisor-worker:latest docker/worker
```

### Dockerfile Summary:
- Base: `python:3.11-slim`
- User: Dedicated non-root `worker` user (UID/GID 1000)
- Dependencies: `pytest>=8.0.0`, `git`
- Workdir: `/workspace`

---

## 5. Running the End-to-End Demo

The killer demo (`demo/scenarios/scenario_01_loop_recovery.py`) supports both execution backends:

### Local Execution Mode (Default):
```bash
python demo/scenarios/scenario_01_loop_recovery.py
```

### Docker Execution Mode:
```bash
EXECUTION_BACKEND=docker python demo/scenarios/scenario_01_loop_recovery.py
```

---

## 6. Telemetry & Observable Container Events

All container lifecycle transitions emit structured events to the central `EventBus`:

| Event Type | Trigger | Key Payload Attributes |
| :--- | :--- | :--- |
| `container.created` | Ephemeral container created | `container_id`, `image`, `workspace` |
| `container.started` | Container process launched | `container_id`, `memory_limit`, `network_disabled` |
| `execution.started` | Command dispatched to provider | `backend`, `command`, `container_id` |
| `execution.completed` | Command finished successfully (exit code 0) | `backend`, `container_id`, `duration_ms` |
| `execution.failed` | Non-zero exit code or error | `backend`, `error`, `duration_ms` |
| `container.limit_exceeded` | Timeout or resource ceiling breached | `container_id`, `reason` (`TIMEOUT`/`CRASH`) |
| `container.destroyed` | Container removed from host | `container_id` |

---

## 7. Limitations & Prerequisites

1. **Docker Engine Requirement**:
   - To use `EXECUTION_BACKEND=docker`, Docker Engine (or Docker Desktop on macOS/Windows) must be running.
   - When Docker is stopped, tests and executions fall back cleanly or skip integration suites without crashing.
2. **Volume Mount Permissions**:
   - On Linux systems with SELinux, mount flags may require `:z` or appropriate user namespace mapping.
