# AI Supervisor — Implementation Audit & Architectural Baseline

## 1. Executive Summary
This document fulfills **Phase 1 (Audit & Baseline)** of the Master Implementation Prompt for AI Supervisor. It provides an honest, empirical analysis of the codebase, distinguishing live operational components from simulated or mocked behaviors, identifies architectural gaps (notably the absence of a mandatory, versioned plan approval barrier prior to task dispatch), and outlines the exact implementation sequence for Phases 2 through 7.

---

## 2. Existing Architecture

### 2.1 Backend Architecture
- **Framework**: FastAPI application running with Uvicorn (`apps/api/main.py`), using dependency injection and modular routers:
  - `/api/missions`: Mission lifecycle management, drafting, execution.
  - `/api/events`: Event queries, WebSocket streaming (`/ws/events`).
  - `/api/agents`: Agent registry, capabilities, and status.
  - `/api/providers`: Provider configurations (OpenRouter, Backboard, Nebius, Hugging Face, Gemini, DigitalOcean).
  - `/api/absence`: Operator absence delegation mode and policy management.
  - `/api/jenkins`: Jenkins CI integration for build triggers and verification.
  - `/api/watchdog`: Health monitoring, heartbeat tracking, anomaly alerts.
  - `/api/memory`: Structured project and mission memory storage.
  - `/api/telemetry`: Token, cost, and tool call tracking.
- **Persistence Layer**: SQLite with Write-Ahead Logging (WAL) enabled (`storage/sqlite/db.py`, `storage/sqlite/schema.sql`, `storage/sqlite/repositories.py`).
  - Tables: `missions`, `tasks`, `agents`, `events`, `memory_records`, `approvals`, `verifications`, `handoffs`, `routing_decisions`, `absence_sessions`, `absence_decisions`.
- **Event Engine**: In-memory async event bus (`core/events/bus.py`) with append-only persistence to `events` table and optional `supervisor_events.jsonl`.
- **Execution & Orchestration**:
  - `execution/mission_runner.py`: Mission execution orchestration with task dispatch, worktree management, step verification, and watchdog checks.
  - `execution/worktree.py`: Git worktree isolation per mission to avoid dirtying operator working trees.
  - `adapters/`: Adapters for Claude Code CLI, Hermes, OpenCode, Codex, Gemini CLI.
  - `integrations/`: Provider adapters for OpenRouter, Backboard, Hugging Face, Nebius, DigitalOcean, Gemini API.

### 2.2 Frontend Architecture
- **Framework**: React 18, TypeScript, Vite, TailwindCSS (`apps/control-room/`).
- **Core Views**:
  - `Dashboard.tsx`: High-level operational overview, active missions, system health.
  - `Missions.tsx`: Mission list, mission creator dialog, state transitions.
  - `MissionControl.tsx`: Live mission inspector with task tree, log stream, intervention controls.
  - `Agents.tsx`: Agent registry, runtime capabilities, provider links.
  - `Settings.tsx`: Provider configuration, API key setup, environment testing.
  - `Absence.tsx`: Absence mode settings, approval delegation policies.

---

## 3. Existing Features & Verified Status

| Component / Feature | Implementation State | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **SQLite WAL Storage** | Real SQLite database (`supervisor.db`) with schema initialization, foreign keys, and indexes. | Repository tests (`tests/test_storage_repositories.py`) passing. | **OPERATIONAL** |
| **Event Bus & WebSocket** | Async event publishing with broadcast to active WebSocket clients. | Contract tests (`tests/test_event_bus.py`, `tests/test_websocket.py`) passing. | **OPERATIONAL** |
| **OpenRouter Provider** | Live API client with model listing (`openrouter/client.py`) and provider abstraction. | Authenticated with live key, pytest passing. | **OPERATIONAL** |
| **Backboard.io Provider** | Client and provider integration (`integrations/backboard/`). | Contract tests (`tests/test_backboard_integration.py`) passing. | **OPERATIONAL** |
| **Hugging Face Provider** | Account and model validation client (`integrations/huggingface/`). | Contract tests (`tests/test_huggingface_integration.py`) passing. | **OPERATIONAL** |
| **Worktree Isolation** | Git worktree creation, status inspection, and branch cleanup. | `tests/test_worktree.py` passing. | **OPERATIONAL** |
| **Mission Runner** | Sequential task runner with step-level command execution and watchdog hooks. | `tests/test_mission_runner.py` passing. | **OPERATIONAL** |
| **Plan Approval Gate** | Partial / Simulated. Currently drafting creates a mission, but execution can be triggered without an explicit, versioned, transactional user approval step. | Code inspection of `/api/missions/draft` and `apps/control-room/src/pages/Missions.tsx`. | **PARTIAL / NEEDS REFACTOR** |
| **Plan Review UI** | Missing dedicated review screen. Tasks are displayed in a basic list without structured intent extraction (in-scope vs exclusions, assumptions, blocking questions). | Inspection of `apps/control-room/src/`. | **MISSING** |
| **Provider Discovery vs Runtimes** | Providers (e.g. Hugging Face, OpenRouter) and Agent Runtimes (e.g. Claude Code, Hermes) were conflated in UI cards. | Inspection of `Agents.tsx`. | **PARTIAL** |
| **Independent Verification** | Exit-code checks and basic git diff exist, but full multi-step acceptance verification against criteria is incomplete. | Code inspection of `core/verification/`. | **PARTIAL** |

---

## 4. Mocked or Incomplete Functionality Identified

1. **Premature Task Execution / Weak Approval Gate**:
   - Missions could be started directly from draft without an enforced check that:
     1. The plan is in `AWAITING_APPROVAL` status.
     2. There are 0 unresolved blocking clarification questions.
     3. An explicit approval record was recorded for the exact `plan_version`.
     4. Required agent runtimes are actually available and configured.
2. **Conflation of LLM Providers and Agent Runtimes**:
   - Hugging Face or OpenRouter endpoints were displayed in some views as runnable autonomous coding agents. An LLM API endpoint provides text generation/tools, but is NOT an autonomous coding-agent runtime with shell execution, file editing, and worktree control.
3. **Standby Default Agents**:
   - Several agent tiles in `Agents.tsx` defaulted to "idle" or "ready" without verifying whether CLI binaries (`claude`, `hermes`, `gemini`) exist in the host PATH.
4. **Structured Plan & Intent Extraction**:
   - The planning step lacked a structured output contract:
     - `original_request`
     - `interpreted_goal`
     - `deliverables`
     - `in_scope`
     - `exclusions`
     - `constraints`
     - `assumptions`
     - `blocking_questions`
     - `non_blocking_assumptions`
     - `risks`
     - `definition_of_success`
     - `verification_methods`

---

## 5. Critical Bugs & Security Concerns

1. **Execution Race Conditions / Double Dispatch**:
   - Need transactional state validation and locking in `apps/api/main.py` and `core/missions/manager.py` to prevent duplicate task dispatches if an operator clicks "Approve & Start" multiple times.
2. **Secret Leakage Prevention**:
   - API keys (OpenRouter, Backboard, Hugging Face, etc.) must NEVER be returned in `/api/providers` responses, logs, or WebSocket payloads. Provider models must only expose masked keys (e.g. `sk-or-v1-...***`).
3. **Workspace Boundary Enforcement**:
   - Shell command execution must remain strictly restricted to the mission worktree or target project path, preventing path traversal into parent directories or operator credentials.

---

## 6. Implementation Sequence

### Phase 2 — Mission & Plan State (Backend)
- Expand `MissionStatus` enum in `core/missions/models.py`:
  - `DRAFT`, `PLANNING`, `AWAITING_APPROVAL`, `APPROVED`, `RUNNING`, `VERIFYING`, `COMPLETED`, `NEEDS_CLARIFICATION`, `REJECTED`, `CANCELLED`, `FAILED`.
- Introduce `PlanVersion` data model in `core/missions/models.py` and SQLite schema migration (`storage/sqlite/schema.sql` and `storage/sqlite/repositories.py`):
  - Structured interpretation, ordered tasks with acceptance criteria, version number, approval status, approver metadata.
- Implement Plan Management API endpoints in `apps/api/main.py`:
  - `GET /api/missions/{id}/plan`
  - `POST /api/missions/{id}/plan/edit`
  - `POST /api/missions/{id}/plan/regenerate`
  - `POST /api/missions/{id}/plan/clarify`
  - `POST /api/missions/{id}/plan/approve`
  - `POST /api/missions/{id}/plan/reject`
- Enforce strict dispatch barrier: `POST /api/missions/{id}/execute` or `/start` MUST reject if status is not `APPROVED` or if plan version does not match.

### Phase 3 — Plan Review Experience (Frontend)
- Build dedicated `PlanReviewModal` / `PlanReviewView` in `apps/control-room/src/components/PlanReview.tsx`.
- Sections rendered:
  - **A. Original Request** (verbatim).
  - **B. What I Understood** (interpreted goal, deliverables, scope, exclusions, assumptions).
  - **C. Proposed Execution Plan** (task order, dependencies, acceptance criteria).
  - **D. Agent Assignments** (genuine availability, reason, runtime capability).
  - **E. Risks & Clarifications** (blocking questions highlight, destructive command warnings).
  - **F. Expected Outcome & Verification Methods**.
  - **G. Action Controls** (Edit, Clarify, Regenerate, Reject, Approve & Start).
- Integrate seamlessly into `Missions.tsx` and `MissionControl.tsx`.

### Phase 4 — Real Execution Path & Observability
- Connect approved plan tasks to real execution in `execution/mission_runner.py`.
- Ensure real-time WebSocket events (`MISSION_STARTED`, `TASK_STARTED`, `TASK_COMPLETED`, `VERIFICATION_STARTED`, `MISSION_COMPLETED`) stream to UI without fake progress timers.

### Phase 5 — Provider Abstraction vs Agent Runtimes
- Clearly distinguish Infrastructure Providers (Inference / Memory) from Agent Runtimes (CLI / Worker).
- Standby agents marked honestly as `UNAVAILABLE` or `NOT_INSTALLED` if host binary is absent.

### Phase 6 — Independent Verification & Evidence Collection
- Execute post-run verification checks (git diff, test suite runs, expected file checks).
- Persist evidence in `verifications` table and display in Mission Control.

### Phase 7 — Testing, Hardening & Final Report
- Run backend pytest suite, frontend TypeScript build check, and write the comprehensive Final Report.

---

## 7. Existing Functionality That Must Be Preserved
1. **SQLite WAL Database & Repositories**: Existing schema and transaction model must be preserved and extended backward-compatibly.
2. **WebSocket Real-Time Event Architecture**: Existing client reconnection and event streaming contracts.
3. **Git Worktree Isolation**: The ability to isolate agent runs into temporary worktrees.
4. **Provider Integrations**: OpenRouter, Backboard, Hugging Face, Nebius, and Gemini integrations.
