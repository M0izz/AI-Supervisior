# AI Supervisor

> **The control plane for your AI workforce.**
>
> *"Your AI agents work. Your Supervisor makes sure they finish the job."*

[![Live Demo](https://img.shields.io/badge/Live%20Demo-ai--supervisior.vercel.app-blueviolet?style=for-the-badge&logo=vercel)](https://ai-supervisior.vercel.app/)
[![Tests](https://img.shields.io/badge/tests-274%20passed%20%7C%207%20skipped%20%7C%200%20failed-success?style=for-the-badge)](tests/)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI%20%2B%20Python%203.11%2B-009688?style=for-the-badge&logo=fastapi)](apps/api/)
[![Frontend](https://img.shields.io/badge/frontend-React%2019%20%2B%20TypeScript-61DAFB?style=for-the-badge&logo=react)](apps/control-room/)
[![License](https://img.shields.io/badge/license-MIT-blue?style=for-the-badge)](LICENSE)

[🚀 Live Demo](https://ai-supervisior.vercel.app/) • [GitHub Repository](https://github.com/M0izz/AI-Supervisior) • [Documentation Index](#10-documentation-index) • [Production Deployment](#6-production-deployment)

---

## 1. What is AI Supervisor?

Autonomous coding agents (Claude Code, OpenAI Codex, Gemini CLI, Qwen, OpenCode, Kimi) write code rapidly, but left unsupervised they can loop on identical errors, hallucinate test passes, drift out of scope, perform dangerous terminal commands, or silently give up.

**AI Supervisor** provides a unified supervisory nervous system that routes tasks to the best agent, observes execution traces in real time, intervenes deterministically on failure loops, coordinates seamless handoffs, and **independently verifies** that the work actually works before accepting it.

> **Core Axiom**: *Worker completion ≠ verified completion.* No agent is permitted to certify its own success.

```
Goal ──► Plan ──► Route ──► Execute ──► Observe ──► Intervene ──► Handoff ──► Verify ──► Remember ──► Complete
```

---

## 2. Product Cockpit Preview

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  AI SUPERVISOR  ::  CONTROL ROOM                                    CLOUD: SYNCED  ●  WATCHDOGS: ARMED │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  ACTIVE MISSION: Add CSV Import with UTF-8 BOM Support [MSN-042]                                       │
│  Objective: Support \ufeff marker in CSV ingestion without breaking database schema                   │
│                                                                                                        │
│  [TASK-001] Analyze Schema ──────► [TASK-002] Implement Parser ──────► [TASK-003] Independent Verify   │
│   ✓ Claude Code (Completed)         ▲ Hermes Agent (PAUSED)             ○ Pending Verification          │
│                                     │                                                                  │
│  SUPERVISORY INTERVENTION TIMELINE  │                                                                  │
│  ├─ 10:14:02  [OBSERVE]    Hermes failed 3x on same encoding assertion (45 passed / 2 failed)          │
│  ├─ 10:14:03  [WATCHDOG]   LOOP_DETECTED threshold triggered (failure signature identical)             │
│  ├─ 10:14:04  [INTERVENE]  Execution token revoked; agent process paused safely in git worktree        │
│  ├─ 10:14:05  [REASONING]  Gemma 4 + Nebius diagnosis: UTF-8 BOM byte marker prefix (\ufeff)           │
│  ├─ 10:14:06  [MEMORY]     Recorded VERIFIED_FACT (BOM marker) & REJECTED_APPROACH (regex stripping)   │
│  ├─ 10:14:08  [HANDOFF]    Context packaged with diffs & constraints ──► Routed to OpenAI Codex       │
│  ├─ 10:14:19  [EXECUTE]    Codex applies codecs.BOM_UTF8 byte strip in isolated worktree               │
│  ├─ 10:14:24  [VERIFY]     Independent Verification Suite: 47/47 passed, 0 regressions, 0 scope leaks  │
│  └─ 10:14:26  [COMPLETE]   Mission verified and accepted into main repository                          │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The Three-Layer Architecture

AI Supervisor explicitly decouples the control plane into three distinct layers:

```
                                  AI SUPERVISOR
                     (Control Plane & Supervisory Nervous System)
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           ▼                            ▼                            ▼
     AGENT RUNTIMES            INTELLIGENCE / MODELS          INFRASTRUCTURE
  (Who does the work)           (Who reasons & plans)      (Where execution runs)
           │                            │                            │
   • Claude Code (Anthropic)    • Google Gemma 4             • DigitalOcean
   • OpenAI Codex               • Google Gemini API            - Droplets & MicroVMs
   • Google Gemini CLI          • Nebius Models                - Serverless Inference
   • Qwen 2.5 Coder               - NVIDIA Nemotron            - Action Gateway Tools
   • OpenCode                     - Nous Hermes              • Nebius AI Studio
   • Moonshot Kimi                - Qwen 2.5                   - Token Factory
   • Nous Hermes Agent            - DeepSeek R1              • Local Workstation
   • Block Goose                • Local Models                 - Git Worktrees
   • Cline                        - Ollama / llama.cpp         - Docker Sandboxes
```

### Layer Breakdown

1. **Agent Runtimes (Execution Workers)**:
   External autonomous agents executed inside isolated Git worktrees with strict file scope boundaries. They communicate through the standardized **Work Protocol**.
2. **Intelligence / Models (Cognitive Layer)**:
   - **Google Gemma 4**: Lightweight supervisory intelligence for bounded goal decomposition, task planning, invariant extraction, failure classification, and decision explanation.
   - **Google Gemini API**: Deep diagnostic reasoning, multimodal analysis, complex failure diagnosis, and architectural boundary review.
   - **Nebius AI Studio**: High-throughput inference gateway hosting NVIDIA Nemotron, Nous Hermes, Qwen, and DeepSeek models.
   - **Local Models**: Offline fallback support via Ollama and llama.cpp.
3. **Infrastructure & Providers**:
   - **DigitalOcean**: Backing cloud infrastructure providing droplet hosting, serverless inference for Gemma 4, managed agent runtimes, and the Action Gateway tool security gatekeeper.
   - **Nebius**: Inference substrate providing low-latency token factory access to open weights models.
   - **Render**: Production cloud backend hosting the FastAPI control plane and WebSocket broadcaster.
   - **Vercel**: Global edge CDN hosting the React 19 Control Room web cockpit.
   - **Local Machine**: Developer host processes with isolated Git worktrees and Docker sandboxes.

---

## 4. Supervisory Control Flow

```
User Goal
   │
   ▼
[ 1. PLAN ] ───────► Gemma 4 & Gemini decompose goal into sequential DAG with strict file scopes
   │
   ▼
[ 2. ROUTE ] ──────► Dynamic Router selects best available agent based on capability & verified history
   │
   ▼
[ 3. EXECUTE ] ────► Agent runs inside isolated Git worktree or sandboxed container
   │
   ▼
[ 4. OBSERVE ] ────► Auditable event stream logs every tool call, file write, and test run
   │
   ▼
[ 5. INTERVENE ] ──► Watchdogs catch loops (3x fail), scope leaks, dangerous commands, or budget drains
   │
   ▼
[ 6. HANDOFF ] ────► Supervisor packages verified facts & failed attempts, transfers context to fallback agent
   │
   ▼
[ 7. VERIFY ] ─────► Independent Verification tests code in clean sandbox (Tests + Git Diffs + Invariants)
   │
   ▼
[ 8. REMEMBER ] ───► Project Memory stores verified facts and rejected approaches to prevent repeated errors
   │
   ▼
[ 9. COMPLETE ] ───► Mission completed with cryptographic proof of independent verification
```

---

## 5. Multi-Agent Fleet Status & Availability

AI Supervisor truth-reports the operational readiness of every agent adapter. An adapter existing in code does not mean it is marked live:

| Agent Runtime | Adapter ID | Supported Interface | Runtime Status Requirements | Untrusted Boundary |
|---|---|---|---|---|
| **Anthropic Claude Code** | `claude_code` | CLI Process (`asyncio`) | `claude` executable in local `PATH` | Isolated Git Worktree |
| **OpenAI Codex** | `codex` | CLI Process (`asyncio`) | `codex` binary or fallback mock | Isolated Git Worktree |
| **Google Gemini CLI** | `gemini` | Gemini CLI / API | `gemini` executable or `GEMINI_API_KEY` | Isolated Git Worktree |
| **Qwen Local Runtime** | `qwen` | Ollama / vLLM / CLI | Local Ollama endpoint or `qwen` CLI | Isolated Git Worktree |
| **OpenCode** | `opencode` | OpenCode CLI Process | `opencode` binary in `PATH` | Isolated Git Worktree |
| **Moonshot Kimi** | `kimi` | Kimi CLI Process | `kimi` executable or Nebius endpoint | Isolated Git Worktree |
| **Nous Hermes** | `hermes` | Persistent Session CLI | `hermes` binary or DigitalOcean/Nebius | Worktree / Session |
| **Block Goose** | `goose` | Developer CLI Process | `goose` executable in local `PATH` | Isolated Git Worktree |
| **Cline** | `cline` | CLI / Extension Agent | `cline` binary or node process | Isolated Git Worktree |
| **DigitalOcean Managed**| `digitalocean_managed` | Cloud Agent API | `DIGITALOCEAN_TOKEN` configured | MicroVM Container |

### Status Indicators in the Control Room

* **`CONNECTED`**: API credentials authenticated and live remote endpoint active.
* **`AVAILABLE`**: Adapter registered, executable detected on system, and ready for worktree assignment.
* **`INSTALLED LOCALLY`**: CLI binary discovered in host `$PATH`.
* **`CONFIGURED`**: Environment variables detected, awaiting health verification.
* **`UNAVAILABLE`**: CLI not installed or required API key missing.
* **`OFFLINE FALLBACK`**: Offline development mode using deterministic mock reasoning and verified local fallbacks.

---

## 6. Production Deployment

AI Supervisor is designed for a hybrid cloud architecture: the **Supervisor Control Plane** lives in the cloud for team observability, while **Agent Execution** runs securely where your code lives (on developer machines, isolated CI nodes, or private Droplets).

```
                      PRODUCTION TOPOLOGY
                      
     ┌──────────────────────────────────────────────────┐
     │                FRONTEND (Vercel)                 │
     │        https://ai-supervisior.vercel.app/        │
     │             React 19 + TypeScript + Vite         │
     └────────────────────────┬─────────────────────────┘
                              │ HTTPS / WSS
                              ▼
     ┌──────────────────────────────────────────────────┐
     │                BACKEND (Render)                  │
     │            FastAPI Control Plane Engine          │
     │        EventBus · Dynamic Router · Watchdogs     │
     └──────────────┬───────────────────┬───────────────┘
                    │                   │
         REST / WSS │                   │ AI Inference
                    ▼                   ▼
     ┌────────────────────────┐  ┌────────────────────────────────────┐
     │  LOCAL WORKSTATIONS    │  │    CLOUD AI & INFRASTRUCTURE       │
     │  • Developer Machine   │  │  • DigitalOcean                    │
     │  • Git Worktrees       │  │    - Serverless Gemma 4 Inference  │
     │  • Local CLI Agents    │  │    - Managed Droplets / MicroVMs   │
     │  • Docker Sandboxes    │  │    - Action Gateway Security       │
     │  • Offline Outbox Sync │  │  • Nebius AI Studio (Token Factory)│
     └────────────────────────┘  │  • Google Gemini API (Multimodal)   │
                                 └────────────────────────────────────┘
```

### Cloud Supervisor vs. Local Agent Execution

* **Cloud Supervisor (Vercel + Render)**: Provides the centralized dashboard, mission tracking, historical memory, and team coordination.
* **Local Agent Execution**: Agents run on your local workstation with direct access to local compilers, test runners, and private Git branches. Sensitive credentials and private keys never leave the workstation.

---

## 7. Independent Verification

Verification is an autonomous, evidence-based gate that is completely independent of the agent implementing the fix:

```
                    Agent Claims Completion
                               │
                               ▼
               INDEPENDENT VERIFICATION PERIMETER
                               │
     ┌─────────────────────────┼─────────────────────────┐
     ▼                         ▼                         ▼
Test Sandbox Scope Bounds    Git Worktree Integrity    Regression Proofs
• Clean execution env      • No files touched outside • All pre-existing
• Fresh dependency state     declared task scope        tests continue to pass
• Exit code == 0           • No secrets added         • No performance drop
     │                         │                         │
     └─────────────────────────┼─────────────────────────┘
                               │
                               ▼
               Decision: [ ACCEPT | REJECT | REVIEW ]
```

*(External CI systems like Jenkins can be connected as an additional verification evidence source via `JENKINS_URL`, but verification is fundamentally autonomous and does not require external CI).*

---

## 8. Quickstart & Local Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Git 2.30+

### 1. Clone & Configure Environment
```bash
git clone https://github.com/M0izz/AI-Supervisior.git
cd AI-Supervisior

# Copy configuration template
cp .env.example .env
```

### 2. Configure Model Credentials (Optional for Cloud Mode)
To connect live cloud intelligence:
```ini
# Google Gemini API (Multimodal reasoning)
GEMINI_API_KEY=your_gemini_api_key

# Nebius AI Studio (High throughput open models)
NEBIUS_API_KEY=your_nebius_api_key
NEBIUS_BASE_URL=https://api.studio.nebius.ai/v1

# DigitalOcean (Cloud infrastructure & Serverless Gemma 4)
DIGITALOCEAN_TOKEN=your_digitalocean_token
DO_INFERENCE_KEY=your_do_inference_key
GEMMA_MODEL=gemma-4-31B-it
```
*(If cloud credentials are not supplied, the system operates in offline-first mode with deterministic local fallbacks).*

### 3. Launch Backend (FastAPI)
```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server on port 8000
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify backend health:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### 4. Launch Frontend (Control Room)
```bash
cd apps/control-room
npm install
npm run build    # Compiles production distribution to dist/
npm run dev      # Launches local dev server on http://localhost:5173
```
Open [http://localhost:5173](http://localhost:5173) in your browser (or use the [Live Hosted Demo](https://ai-supervisior.vercel.app/)).

---

## 9. Verified Test Suite Results

Test numbers are verified directly against the current repository execution:

```bash
python -m pytest tests/ -v
```

```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.1.1
collected 281 items

tests/test_absence.py ................................................... PASSED
tests/test_adapters.py .................................................. PASSED
tests/test_api.py ....................................................... PASSED
tests/test_core.py ...................................................... PASSED
tests/test_desktop.py ................................................... PASSED
tests/test_end_to_end_recovery.py ....................................... PASSED
tests/test_fleet.py ..................................................... PASSED
tests/test_handoff.py ................................................... PASSED
tests/test_kernel.py .................................................... PASSED
tests/test_memory.py .................................................... PASSED
tests/test_phase10_deployment.py ........................................ PASSED
tests/test_phase2_worker.py ............................................. PASSED
tests/test_phase3_supervisor.py ......................................... PASSED
tests/test_phase4_recovery.py ........................................... PASSED
tests/test_phase5_docker.py ............................................. PASSED
tests/test_phase5_hardening.py .......................................... PASSED
tests/test_phase6_jenkins.py ............................................ PASSED
tests/test_phase7_control_plane.py ...................................... PASSED
tests/test_phase8_reliability_adversarial.py ............................ PASSED
tests/test_provider_contracts.py ........................................ PASSED
tests/test_routing.py ................................................... PASSED
tests/test_sync.py ...................................................... PASSED
tests/test_verification.py .............................................. PASSED
tests/test_watchdogs.py ................................................. PASSED

============ 274 passed, 7 skipped, 0 failed in 163.14s (0:02:43) ============
```

### Frontend Build & Lint Verification
- **Build**: `tsc -b && vite build` — 1,916 modules transformed, production distribution compiled in `apps/control-room/dist/` in 4.83s.
- **Lint**: `oxlint` — 27 files evaluated across 116 rules: **0 errors**.

---

## 10. Documentation Index

- [Live Web App](https://ai-supervisior.vercel.app/) — Hosted production Control Room cockpit on Vercel.
- [Architecture Guide](docs/architecture.md) — Comprehensive technical design, state machines, and data flows.
- [Cloud Sync Architecture](docs/sync-architecture.md) — Local-first synchronization engine design.
- [Multi-Device Continuity](docs/multi-device.md) — Workstation pairing and outbox replication guide.
- [IDE Integration Guide (VS Code)](docs/ide-integration.md) — Visual Studio Code extension architecture.
- [Absence Mode Specification](docs/absence-mode.md) — Bounded autonomy policy, approval timeouts, and safety invariants.
- [Claude Code Adapter Guide](docs/adapters/claude-code.md) — Anthropic Claude Code adapter specification.
- [Codex Adapter Guide](docs/adapters/codex.md) — OpenAI Codex adapter specification.
- [Gemini Adapter Guide](docs/adapters/gemini.md) — Google Gemini CLI adapter specification.
- [Qwen Local Adapter Guide](docs/adapters/qwen.md) — Qwen local runtime & untrusted boundary guide.
- [OpenCode Adapter Guide](docs/adapters/opencode.md) — OpenCode CLI adapter specification.
- [Kimi Adapter Guide](docs/adapters/kimi.md) — Moonshot Kimi CLI adapter specification.
- [Deployment Guide](docs/deployment.md) — Nebius, DigitalOcean, Vercel, and Render deployment specifications.
- [Docker Execution Hardening](docs/docker-execution.md) — Sandbox security profiles and privilege isolation.
- [Reliability & Adversarial Report](docs/reliability-report.md) — 24-scenario adversarial failure test matrix.

---

## 11. Security & Safety Principles

1. **Zero Implicit Approval**: High-risk actions (e.g., destructive terminal commands, out-of-scope modifications) require explicit human approval. Approval timeouts strictly default to `DENIED`.
2. **Credential Sanitization**: Bearer tokens, API keys, passwords, and private URLs are scrubbed from tool execution traces, event payloads, and UI streams before emission.
3. **Worktree & Container Isolation**: Agent code executes inside isolated Git worktrees and single-host Docker sandboxes (`cap_drop=["ALL"]`, `network_mode="none"`, memory limits `512MB`).
4. **Append-Oriented Event Stream**: All actions, interventions, and watchdog triggers are recorded in an auditable event stream for forensic playback.
5. **Epistemic Provenance**: Knowledge in Project Memory is tagged by proof (`OBSERVED`, `INFERRED`, `DECIDED`, `VERIFIED`, `REJECTED`), preventing agents from repeating known failed strategies.

---

## 12. Repository Metadata

For repository settings and public listing:

* **Repository Description**: `Supervisory control plane for AI coding agents — routing, monitoring, recovery, handoffs, and independent verification.`
* **Website**: `https://ai-supervisior.vercel.app/`
* **Topics**: `ai-agents`, `ai-agent`, `agent-orchestration`, `agent-supervisor`, `coding-agents`, `multi-agent`, `llm`, `gemma`, `gemini`, `nebius`, `digitalocean`, `fastapi`, `react`, `developer-tools`

---

## 13. License

This project is open-source software licensed under the [MIT License](LICENSE).
