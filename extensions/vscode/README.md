# AI Supervisor — VS Code Extension

> **A personal AI operations layer that manages, coordinates, supervises, recovers, and independently verifies the AI agents a developer already uses.**

*The agents are replaceable. The Supervisor is the product.*

---

## Overview

The **AI Supervisor VS Code Extension** connects your local editor workspace to the authoritative AI Supervisor backend control plane.

### Core Invariant
> **The IDE extension is an interface to the Supervisor, NOT another Supervisor, NOT an agent runtime, and NOT the source of truth.**

All mission planning, dynamic agent routing, live watchdog interventions, cross-provider handoffs, project memory, and independent verification remain strictly owned and executed by the Supervisor backend.

---

## Features

### 1. Activity Bar Sidebar
- **Missions & Execution**: Live status of active and recent missions, assigned agents, and DAG task progress.
- **Fleet Providers & Agents**: Real-time status of all registered providers (`Claude Code`, `Codex`, `Gemini`, `Qwen Local`, `OpenCode`, `Kimi`) with truthful availability badges (`AVAILABLE`, `UNAVAILABLE`, `NOT_CONFIGURED`) and declared capabilities.
- **Attention & Approvals**: Surfaces pending operator approvals and active Absence Mode sessions with remaining countdowns.

### 2. Status Bar Item
- Compact, low-distraction status indicator:
  - `$(shield) Supervisor: 2 Active` — Nominal operations with running missions.
  - `$(warning) Supervisor: Attention` — Pending high-risk actions requiring operator approval.
  - `$(circle-slash) Supervisor: Offline` — Graceful offline degradation when backend is unreachable.

### 3. Native Commands (Command Palette: `Ctrl/Cmd + Shift + P`)
- `AI Supervisor: Start Mission` — Prompts for an engineering objective, attaches repository context, and delegates to the Supervisor router.
- `AI Supervisor: Work on Selection` — Packages the active editor code selection and line numbers as untrusted context for targeted task creation.
- `AI Supervisor: Investigate Current Diagnostics` — Collects active file errors/warnings and initiates a diagnostic mission.
- `AI Supervisor: Pause Mission` / `Resume Mission` / `Cancel Mission` — Full mission lifecycle controls.
- `AI Supervisor: Approve Action` / `Deny Action` — Operator gate for high-risk actions.
- `AI Supervisor: Arm Absence Mode` / `Emergency Stop` — Bounded unattended execution controls.
- `AI Supervisor: Open Control Room Dashboard` — Launches the rich web control room at `http://localhost:5173`.
- `AI Supervisor: Refresh Fleet State` — Manually queries backend health and updates all tree views.

### 4. Zero-Nag Notification Policy
Routine operational telemetry (files modified, commands started, tests passing) is suppressed. Notifications appear only for actionable moments:
- Operator approvals required
- Watchdog interventions (infinite loop detected, scope breach)
- Independent verification rejections
- Cross-provider handoffs
- Mission completions & failures

---

## Installation & Setup

### Prerequisites
- VS Code 1.85.0+
- AI Supervisor backend running (`http://127.0.0.1:8000`)

### Local Installation (.vsix)
```bash
cd extensions/vscode
npm run package
code --install-extension ai-supervisor-vscode-1.0.0.vsix
```

### Development Setup
```bash
cd extensions/vscode
npm install
npm run build
npm test
```
Press `F5` in VS Code to launch the Extension Development Host.

---

## Extension Settings

| Setting | Type | Default | Description |
|---|---|---|---|
| `aiSupervisor.apiUrl` | `string` | `http://127.0.0.1:8000` | Authoritative FastAPI backend URL |
| `aiSupervisor.websocketUrl` | `string` | `ws://127.0.0.1:8000/ws/events` | Live supervisory event WebSocket |
| `aiSupervisor.controlRoomUrl` | `string` | `http://localhost:5173` | Control Room web cockpit URL |
| `aiSupervisor.autoConnect` | `boolean` | `true` | Connect automatically on editor launch |
| `aiSupervisor.showNotifications` | `boolean` | `true` | Enable zero-nag actionable notifications |
| `aiSupervisor.showStatusBar` | `boolean` | `true` | Show status bar item |

---

## Security Boundary & Workspace Trust

- **Untrusted Input**: Selected code and diagnostic messages are treated as untrusted input data.
- **Path Traversal Protection**: Filesystem targets are validated using `PathValidator.isWithinWorkspace`. Directory traversal (`../`) and external filesystem access are strictly blocked.
- **No Secret Storage**: No API tokens, keys, or credentials are stored in extension settings.
- **Workspace Trust**: In untrusted workspaces, AI Supervisor functions in read-only mode and restricts mission creation and file modifications.
