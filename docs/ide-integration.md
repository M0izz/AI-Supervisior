# IDE Integration — Visual Studio Code

## Overview

The AI Supervisor VS Code extension brings the supervisory control plane directly into the developer's everyday editor workspace.

### Core Architectural Principle
> **The IDE extension is an interface to the Supervisor, NOT another Supervisor, NOT an agent runtime, and NOT the source of truth.**

```text
Developer in VS Code
        ↓
Supervisor Extension
        ↓ HTTP & WebSocket (/ws/events)
Supervisor Backend (FastAPI :8000)
        ↓
Universal AgentAdapter
        ↓
Fleet Providers (Claude Code, Codex, Gemini, Qwen Local, OpenCode, Kimi)
        ↓
Live Supervisory Watchdogs
        ↓
Independent Verification
        ↓
Shared Project Memory / Handoff Engine / Absence Mode
```

The underlying Supervisor backend remains the authoritative single source of truth for:
- Mission and task lifecycles
- Dynamic capability routing and cold-start priors
- Real-time watchdog interventions
- Isolated Git worktrees
- Evidence-based Independent Verification
- Absence Mode policies and ceiling enforcement

---

## Extension Architecture

The extension is structured in `extensions/vscode/`:

```text
extensions/vscode/
├── package.json                   # Extension manifest, contributes views, commands, settings
├── tsconfig.json                  # TypeScript build configuration (target: ES2022)
├── .vscodeignore                  # Packaging filter (excludes test files and sources from .vsix)
├── media/
│   └── icon.svg                   # Shield icon for Activity Bar
├── src/
│   ├── extension.ts               # Activation entry point and lifecycle orchestration
│   ├── client/
│   │   └── supervisorClient.ts    # Bounded HTTP & WebSocket client with reconnect and backoff
│   ├── commands/
│   │   └── index.ts               # Palette commands and contextual editor actions
│   ├── notifications/
│   │   └── notificationManager.ts # Zero-Nag notification manager (debouncing, actionable filtering)
│   ├── providers/
│   │   ├── missionsTreeProvider.ts  # Native TreeView for Missions & DAG execution
│   │   ├── agentsTreeProvider.ts    # Native TreeView for Fleet Providers & availability
│   │   └── attentionTreeProvider.ts # Native TreeView for Pending Approvals & Absence Mode
│   ├── status/
│   │   └── statusBar.ts           # Compact status bar health item
│   ├── types/
│   │   └── models.ts              # Strongly typed backend domain models
│   └── utils/
│       └── pathValidator.ts       # Workspace containment and path traversal protection
└── tests/
    └── extension.test.cjs         # Node test runner suite (14 automated contract tests)
```

---

## User Experience & Views

### 1. Activity Bar Sidebar (`AI Supervisor`)
Dedicated container in the VS Code Activity Bar providing three compact native tree views:
- **Missions & Execution**:
  - Lists running, planning, verifying, paused, and completed missions.
  - Expands to show active agent assignment, task status, and execution progress.
  - When backend is unreachable, displays `Supervisor Offline` with reconnect prompt; never fabricates phantom running state.
- **Fleet Providers & Agents**:
  - Discovers all registered `AgentAdapter` providers through the Supervisor registry.
  - Shows truthful availability badges: `AVAILABLE` (green), `UNAVAILABLE` (red), `NOT_CONFIGURED` (yellow).
  - Expands to display declared capabilities (`code_execution`, `git`, `test_execution`, `local_model`, `multimodal`) and binary paths.
- **Attention & Approvals**:
  - Surfaces high-risk approval requests with action type, target, and risk level.
  - Provides one-click `[Approve]` and `[Deny]` action buttons.
  - Displays active Absence Mode sessions with remaining countdown timer.

### 2. Status Bar Item
- Right-aligned, compact status indicator:
  - `$(shield) Supervisor: 2 Active` — Missions running under supervision.
  - `$(warning) Supervisor: 1 Attention` — Pending operator approval required.
  - `$(circle-slash) Supervisor: Offline` — Backend disconnected.
- Clicking the status item navigates directly to the AI Supervisor Activity Bar view.

### 3. Contextual Editor & Selection Actions
- **Right-Click Selection → `AI Supervisor: Work on Selection`**:
  - Captures the exact selected code snippet, line numbers, language ID, and file path.
  - Validates that the file resides strictly within the active workspace.
  - Prompts developer for the targeted instruction.
  - Dispatches mission to the Supervisor router; code is treated strictly as untrusted input.
- **Right-Click Editor → `AI Supervisor: Investigate Current Diagnostics`**:
  - Collects active file errors and warnings via `vscode.languages.getDiagnostics`.
  - Prompts developer to confirm launch of supervisory diagnostic mission.

---

## Zero-Nag Notification Policy

In accordance with AI Supervisor design principles, routine telemetry is silenced:
- **Suppressed Events**: Command starts, file modifications, test executions, agent heartbeats, periodic metric updates.
- **Actionable Surfaced Events**:
  - High-risk approval requests (with Approve/Deny buttons).
  - Supervisory Watchdog interventions (infinite loop detected, scope breach).
  - Independent Verification rejections (ground truth tests failed).
  - Cross-provider handoffs started.
  - Mission completions and terminal failures.
  - Absence Mode pauses and expirations.
- **Debounce Protection**: Duplicate notifications within a 5-second sliding window are automatically suppressed.

---

## Security & Safety Boundaries

1. **Untrusted Input**:
   - Code snippets, editor selections, and diagnostic traces sent from VS Code are treated as untrusted data.
   - They cannot modify Supervisor policies, disable watchdogs, or grant agent capabilities.
2. **Path Traversal Protection**:
   - Every file navigation or context extraction is verified via `PathValidator.isWithinWorkspace`.
   - Any path referencing parent directories (`../`), absolute paths outside roots, or system directories is rejected.
3. **Workspace Trust Integration**:
   - In Untrusted Workspaces, the extension operates in restricted read-only mode.
   - Mission creation, action approvals, and editor-based execution are blocked until the operator explicitly trusts the workspace.
4. **Zero Secret Storage**:
   - No API keys, model tokens, or credentials are stored in VS Code configuration.
   - Credentials remain managed through host environment variables and operating system credential stores.
5. **No Local Agent Execution**:
   - The extension never spawns agent processes (`claude`, `gemini`, `qwen`, `codex`) locally or executes arbitrary shell scripts. Execution occurs solely via the backend's worktree-isolated adapter architecture.

---

## Development & Packaging

### Running Tests
```bash
cd extensions/vscode
npm test
```
Executes 14 automated unit and contract tests verifying PathValidator containment, HTTP/WebSocket client resilience, notification debouncing, multi-provider killer scenario, and negative degradation handling.

### Packaging Local `.vsix`
```bash
cd extensions/vscode
npm run package
```
Generates `ai-supervisor-vscode-1.0.0.vsix` ready for local installation via `code --install-extension`.
