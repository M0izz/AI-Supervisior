# AI Supervisor — Desktop Application & Floating HUD Specification (Phase 8)

> *"The agents are replaceable. The Supervisor is the product."*  
> *"Agent completion ≠ verified completion."*

---

## 1. Overview & Architectural Role

Phase 8 elevates AI Supervisor from a browser-bound Web Control Room into a persistent, local-first **Desktop Supervisor**.

The desktop layer is explicitly an **interface / client** to the authoritative Supervisor backend, **not** a secondary supervisor implementation.

```text
┌────────────────────────────────────────────────────────┐
│                   DESKTOP APPLICATION                  │
│                                                        │
│  ┌───────────────────────┐   ┌──────────────────────┐  │
│  │  Control Room Window  │   │   Floating HUD       │  │
│  │  (Full Supervision)   │   │ (Ambient Status Bar) │  │
│  └───────────┬───────────┘   └──────────┬───────────┘  │
│              │                          │              │
│              └────────────┬─────────────┘              │
│                           │ window.supervisor (Preload)│
│                           ▼                            │
│                 Electron Main Process                  │
│           (Lifecycle / Tray / Zero-Nag IPC)            │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP + WebSocket (/ws/events)
                            ▼
┌────────────────────────────────────────────────────────┐
│                 SUPERVISOR BACKEND                     │
│               (FastAPI / EventBus / WAL)               │
│                                                        │
│  • Mission / Task DAG   • Watchdogs & Interventions    │
│  • Dynamic Router       • Independent Verification     │
│  • Agent Adapters       • Shared Project Memory        │
└────────────────────────────────────────────────────────┘
```

---

## 2. Electron Security Baseline

The Electron shell adheres to strict security defaults:

- `contextIsolation: true`: Isolates preload script execution context from the web renderer.
- `nodeIntegration: false`: Strictly blocks Node.js core modules (`fs`, `child_process`, `os`, `process`, etc.) from the renderer environment.
- `sandbox: true`: Runs renderers in chromium-sandboxed processes where compatible.
- `webSecurity: true`: Enforces same-origin policy and blocks cross-origin script injection.
- **External Navigation Guard**: All `will-navigate` and `setWindowOpenHandler` calls are intercepted to prevent arbitrary external URL redirection.

### Typed Preload Bridge (`window.supervisor`)

Renderers interact with the desktop layer through a narrow, typed contract:

```typescript
export interface SupervisorDesktopBridge {
  getStatus: () => Promise<DesktopStatus>;
  openControlRoom: () => Promise<boolean>;
  hideControlRoom: () => Promise<boolean>;
  showHud: () => Promise<boolean>;
  hideHud: () => Promise<boolean>;
  toggleHud: () => Promise<boolean>;
  minimizeToTray: () => Promise<boolean>;
  notify: (options: DesktopNotificationOptions) => Promise<boolean>;
  getConfig: () => Promise<DesktopConfig>;
  quit: () => Promise<void>;
  onHudToggle?: (callback: () => void) => () => void;
  onBackendStateChange?: (callback: (state: string) => void) => () => void;
}
```

---

## 3. Dual-Window Architecture

### A. Control Room Window
- **Form Factor**: Standard desktop application window (1280x820, min 1024x600).
- **Purpose**: Deep inspection and control.
- **Contents**:
  - Live Task DAG visualization
  - Mission status and metrics
  - Multi-agent registry and heartbeats
  - Supervisory event timeline
  - Shared Project Memory with 6-tuple provenance
  - Human-in-the-loop approval queue
- **Window Lifecycle**: Closing the window hides it to the system tray rather than killing the supervisory process.

### B. Floating Supervisor HUD
- **Form Factor**: Compact, ambient, always-on-top widget (380x240, frameless).
- **Purpose**: Persistent, glanceable status while the developer works in their IDE or terminal.
- **Information Hierarchy**:
  1. **Supervisor Health**: Status dot (`● LIVE` in emerald vs `○ OFFLINE` in crimson) + latency.
  2. **Active Mission & Agent**: Mission title, objective, active model badge (e.g. `Claude Code`, `OpenAI Codex`).
  3. **Supervisory State**: Working, Waiting, Blocked, Recovering, Verifying, Completed, Failed.
  4. **Watchdogs Status**: `✓ Watchdogs clear` vs `⚠ Intervention: {rule}`.
  5. **Independent Verification**: `◌ Verifying ground truth...` vs `✓ Verified ({n}/{n})` vs `✕ Rejected`.
  6. **Active Handoff**: `⇄ Handoff: Claude ➔ Codex`.
  7. **Approval Gate**: Inline `[Approve]` and `[Deny]` action buttons.
  8. **Action Bar**: Direct button to launch Control Room or pause/resume the mission.

---

## 4. Zero-Nag Notification Model

The desktop layer treats developer attention as a scarce resource:

- **Silent Normal Events**:
  - Task started / completed normally
  - Commands executed
  - Files created / modified
  - Heartbeats and benign events
- **Actionable Surfaced Events**:
  - `APPROVAL_REQUIRED`: Agent requires human permission to execute a privileged action.
  - `CRITICAL_INTERVENTION`: Watchdog intervened to halt a loop, scope violation, or dangerous command.
  - `VERIFICATION_FAILED`: Independent verifier rejected an agent's completion claim.
  - `MISSION_FAILED`: Mission aborted due to unrecoverable errors.
  - `MISSION_COMPLETED`: Mission fully verified and committed to git ground truth.
- **Debounce & Rate Limiting**:
  - Identical notifications within a 5-second sliding window are automatically suppressed to prevent alert storms.

---

## 5. Backend Connection & Reconnection Lifecycle

The desktop shell connects to the local FastAPI backend via HTTP and WebSocket (`/ws/events`).

```text
CONNECTING ──► LIVE ──► DEGRADED ──► DISCONNECTED
     ▲                                    │
     └──────── Exponential Backoff ───────┘
```

- When the backend is offline, the UI unambiguously displays `OFFLINE / DISCONNECTED`.
- **Zero Mock Data Policy**: The production desktop shell never falls back to phantom demo missions when disconnected.
- Upon reconnecting, the desktop shell triggers a full state refresh to reconcile missed events.

---

## 6. System Tray Integration

- Persistent tray icon with connection status indicator.
- Context Menu:
  - `● AI Supervisor: LIVE` (status header)
  - `Show / Hide Floating HUD`
  - `Open Control Room`
  - `Quit AI Supervisor`
- Interactions:
  - Single click toggles Floating HUD visibility.
  - Double click restores and focuses the Control Room.

---

## 7. Running Locally

### Development Mode

1. **Start the FastAPI Backend**:
   ```bash
   python -m uvicorn apps.api.main:app --port 8000 --reload
   ```

2. **Start the Vite Frontend**:
   ```bash
   cd apps/control-room
   npm run dev
   ```

3. **Start the Desktop Shell**:
   ```bash
   cd apps/desktop
   npm start
   ```

### Production Build

1. Build the frontend bundle:
   ```bash
   cd apps/control-room
   npm run build
   ```

2. Launch Desktop pointing to production assets:
   ```bash
   cd apps/desktop
   npm start
   ```

### Automated Tests

- **Node Desktop Tests**:
  ```bash
  node --test apps/desktop/tests/desktop.test.cjs
  ```

- **Python Backend & Scenario Tests**:
  ```bash
  python -m pytest tests/test_desktop.py -v
  ```
