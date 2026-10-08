# AI Work Supervisor

> **A supervisory control plane for autonomous AI engineering work that detects failures, prevents unsafe actions, diagnoses problems, coordinates recovery, and independently verifies results.**
> 
> *"Agent completion ≠ verified completion."*

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/tests-263%20Python%20%7C%207%20Desktop%20%7C%2014%20VS%20Code-success.svg)]()
[![Model](https://img.shields.io/badge/model-NVIDIA%20Nemotron--4--340B-76B900.svg)]()
[![Cloud](https://img.shields.io/badge/inference-Nebius%20AI%20Studio-0052FF.svg)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 1. What is AI Work Supervisor? (In 30 Seconds)

* **What is it?** A supervisory control plane and nervous system for autonomous AI engineering agents.
* **Why does it exist?** AI coding agents can loop on errors, drift out of scope, make unsafe changes, exhaust compute budgets, or falsely claim that tasks are complete and tests pass.
* **What does it do?** It observes agent actions through an immutable event stream, detects anomalies via deterministic watchdogs, invokes NVIDIA Nemotron on Nebius for causal reasoning, records empirical facts in project memory, recovers agents with targeted context, and independently verifies code in sandboxed execution and CI.
* **Why is it different?** The architecture is built around the core axiom: **Worker completion ≠ verification.** No agent is permitted to certify its own success.

```
GOAL ──► PLAN ──► ACT ──► OBSERVE ──► VERIFY ──► SUPERVISE ──► RECOVER ──► VERIFY
```

> **Note**: AI Work Supervisor is neither a generic AI agent dashboard, an agent marketplace, a chatbot, a Zapier-like automation platform, nor a generic multi-agent framework. It is an engineering control plane designed specifically to enforce safety, truthfulness, and independent verification over autonomous engineering work.

---

## 2. Demo Preview

```
[ Control Room — Live Supervisory Intervention & Recovery Flow ]
Mission: Add CSV Import with UTF-8 BOM Support
Step 05: Worker fails 3x on encoding (45 passed / 2 failed)
Step 07: Supervisor Watchdog detects anomaly: LOOP_DETECTED
Step 08: Supervisor pauses Worker execution token
Step 09: Nemotron causal reasoning on Nebius Studio: DELEGATE -> Reviewer
Step 10: Reviewer diagnoses causal flaw: UTF-8 BOM marker (\ufeff)
Step 11: Project Memory records verified fact and rejected hypothesis
Step 13: Worker resumes with structured Recovery Context
Step 14: Sandbox executes byte-level fix (47 passed / 0 failed)
Step 15: Jenkins CI independently confirms: Build #482 SUCCESS
Step 16: Independent Verifier agent validates zero regressions -> COMPLETED
```

---

## 3. Technology Roles

Each technology in the stack fulfills an explicit, specialized role:

| Technology | Role | Description |
| :--- | :--- | :--- |
| **Nemotron** | **Supervisory Reasoning** | Open-source NVIDIA Nemotron-4-340B-Instruct evaluates complex failure context, performs causal reasoning, and decides whether to pause, delegate, or terminate. |
| **Supervisor** | **Intervention Decisions** | Deterministic engine combining rule-based watchdogs (loop detection, budget ceilings, scope boundaries) with cognitive decisions to control agent execution tokens. |
| **Worker** | **Autonomous Implementation** | Coding agent equipped with read, write, and bash tools to implement features and bug fixes within its assigned file scope. |
| **Docker** | **Isolated Execution** | Sandboxed single-host container runtime with dropped Linux capabilities (`ALL`), memory limits (`512MB`), CPU quotas (`1.0`), and zero-network isolation (`none`). |
| **Jenkins** | **Independent CI Verification** | Independent Jenkins CI verification using build identifiers, nonces, and parsed JUnit evidence. |
| **Reviewer** | **Failure Diagnosis** | Specialized read-only diagnostic agent that analyzes execution diffs, error traces, and git logs to isolate root causes without modifying code. |
| **Memory** | **Persistent Project Knowledge** | Empirical knowledge store retaining verified facts with provenance tags (`OBSERVED`, `INFERRED`, `DECIDED`, `VERIFIED`, `REJECTED`) to prevent repeating failed strategies. |
| **Verifier** | **Final Validation** | Independent verification agent that reviews test results, confirms acceptance criteria, and issues final sign-off before a mission completes. |
| **EventBus** | **Real-Time Coordination** | Real-time event backbone connecting agents, supervisor watchdogs, WebSocket broadcasting, and audit logging. |
| **Nebius** | **AI Infrastructure** | Nebius hosts the model used for supervisory reasoning; deterministic rules remain the safety layer and model output is constrained to structured supervisory decisions. |

---

## 4. Architecture Diagram

```
                        ┌────────────────────────────────────────┐
                        │      Human Operator / Control Room     │
                        │    (React 19 + TypeScript Cockpit)     │
                        └───────────────────┬────────────────────┘
                                            │ HTTP / WebSocket (:8000)
                                            ▼
                        ┌────────────────────────────────────────┐
                        │      FastAPI Control Plane Engine      │
                        │  (/health, /ready, /ws/events, State)  │
                        └───────────────────┬────────────────────┘
                                            │
                        ┌───────────────────┴────────────────────┐
                        ▼                                        ▼
           ┌──────────────────────────┐             ┌──────────────────────────┐
           │    SUPERVISOR ENGINE     │             │        EVENT BUS         │
           │ • Deterministic Watchdog │             │ • Real-time coordination │
           │ • Scope & Budget Guard   │             │ • Persistent event log   │
           │ • Zero-Implicit-Approval │             │ • WebSocket broadcast    │
           └────────────┬─────────────┘             └──────────────────────────┘
                        │
       ┌────────────────┼────────────────┬────────────────┐
       ▼                ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│Nebius Cloud  │ │Docker Sandbox│ │  Jenkins CI  │ │Project Memory│
│(NVIDIA       │ │(Containers,  │ │(Independent  │ │(Verified     │
│ Nemotron)    │ │ No Network,  │ │ JUnit Proof, │ │ Facts, Diffs,│
│              │ │ 512MB Limit) │ │ Nonce Gate)  │ │ Hypotheses)  │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │                │
       └────────────────┼────────────────┴────────────────┘
                        ▼
       ┌──────────────────────────────────────────────────┐
       │             AUTONOMOUS AGENT FLEET               │
       │  Planner  •  Worker  •  Reviewer  •  Verifier    │
       └──────────────────────────────────────────────────┘
```

---

## 5. The Killer Demo Scenario

The system features a deterministic end-to-end recovery scenario using the project's execution, supervision, recovery, and verification pipeline:

```
Worker Failure
   ▼
Supervisor Detection (Loop Detected: 3 consecutive failures)
   ▼
Nemotron Decision (Causal reasoning on Nebius: DELEGATE)
   ▼
Reviewer Diagnosis (Read-only analysis: UTF-8 BOM encoding bug)
   ▼
Memory (Records verified fact and rejected hypothesis)
   ▼
Recovery (Context packager generates targeted instructions)
   ▼
Docker Execution (Worker resumes, executes byte-level fix in sandbox)
   ▼
Jenkins Verification (Build #482 confirms 47/47 tests passed)
   ▼
Verifier (Independent confirmation: zero regressions)
   ▼
SUCCESS (Mission completed)
```

### Complete 18-Step Execution Path

1. **User creates mission**: `Add CSV Import with UTF-8 BOM Support` in `demo/sample-project`.
2. **Planner creates tasks**: Generates 6-node DAG with strict file scope boundaries.
3. **Worker starts**: `worker_01` assigned to `TASK-002` (`src/parser.py`).
4. **Docker executes worker**: Inspects code within sandboxed environment (or local process sandbox fallback).
5. **Worker encounters repeated failure**: Tests fail 3 consecutive times on byte order mark (`45 passed / 2 failed`).
6. **Jenkins independently confirms failure**: Build #481 confirms `FAILURE` via JUnit test reports. *(In default offline test mode, the deterministic Mock Jenkins provider simulates the CI execution and JUnit proofs; if connected to a live server via `JENKINS_URL`, real builds are triggered via the REST API).*
7. **Supervisor detects anomaly**: Watchdog flags `LOOP_DETECTED` threshold reached ($\ge 3$ identical failures).
8. **Worker pauses**: Supervisor revokes execution token and halts agent.
9. **Nemotron reasons**: NVIDIA Nemotron on Nebius evaluates failure context and issues structured `DELEGATE` decision.
10. **Reviewer diagnoses**: Read-only Reviewer isolates UTF-8 BOM encoding issue (`\ufeff` prefix).
11. **Memory records diagnosis**: Saved as `VERIFIED_FACT` in Project Memory; regex approach recorded as `REJECTED_APPROACH`.
12. **Recovery context is generated**: Context packager bundles diagnosis, constraints, and verified facts.
13. **Worker resumes**: Worker receives recovery package.
14. **Docker executes fix**: Worker modifies `src/parser.py` using `codecs.BOM_UTF8` strip; re-runs sandbox tests.
15. **Jenkins passes**: Build #482 independently verifies `47 passed / 0 failed`.
16. **Verifier confirms**: Verifier agent inspects JUnit proofs and signs off.
17. **Supervisor completes mission**: Mission lifecycle transitions to `COMPLETED`.
18. **Control Room shows complete timeline**: Dynamic story timeline renders the end-to-end causal trace.

---

## 6. Reproducibility & Exact Commands

### Integration Environments & Status
Judges can immediately distinguish what runs live vs offline fallback:

* **LIVE / REAL**:
  * FastAPI Control Plane backend (`http://localhost:8000`)
  * Control Room Web Cockpit (`http://localhost:5173`)
  * Local filesystem execution sandbox (`LocalExecutionProvider`)
  * Docker container sandbox (`DockerExecutionProvider`, when Docker daemon is active)
  * Nebius / NVIDIA Nemotron cloud inference (`NebiusNemotronProvider`, when `NEBIUS_API_KEY` is provided)
* **OPTIONAL EXTERNAL DEPENDENCY**:
  * Remote Jenkins CI Server (REST API integration via `JenkinsHttpClient`)
* **OFFLINE FALLBACK**:
  * Offline Jenkins simulation / fallback provider (`MockJenkinsProvider`, dynamically inspects workspace fixes)
  * Deterministic Nemotron reasoning fallback (`MockReasoningProvider`, offline deterministic decisions)

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Docker (optional, for container execution)
- Jenkins (optional external dependency, for remote CI verification)

### 1. Clone & Configure Environment
```bash
git clone https://github.com/M0izz/AI-Supervisior.git
cd AI-Supervisior

# Copy sample configuration (preconfigured with local deterministic fallbacks)
cp .env.example .env
```

### 2. Configure Nebius API Key (Optional for Cloud Mode)
To connect to NVIDIA Nemotron on Nebius AI Studio:
```ini
NEBIUS_API_KEY=your_nebius_api_key_here
NEBIUS_BASE_URL=https://api.studio.nebius.ai/v1
NEBIUS_MODEL=nvidia/nemotron-4-340b-instruct
```
*(If `NEBIUS_API_KEY` is omitted, the supervisor automatically uses the built-in deterministic local reasoning mock).*

### 3. Install Dependencies & Launch Backend
```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI Control Plane on port 8000
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify backend health:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### 4. Build & Launch Control Room UI
```bash
cd apps/control-room
npm install
npm run build    # Compiles production distribution
npm run dev      # Launches dev server on http://localhost:5173
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

### 5. Reset Demo Environment
Before running demonstrations, reset the demo workspace to a clean baseline:
```bash
python -m demo.reset
```

### 6. Execute the Killer Demo
Run the complete 18-step killer demonstration in your terminal:
```bash
python -m demo.scenarios.killer_scenario
```
*(Or alternatively: `python -m demo.scenarios.scenario_01_loop_recovery`)*

### 7. Run Complete Automated Test Suite
```bash
python -m pytest tests/ -v
```

> **Exact Test Result**: 256 tests collected: 249 passed, 7 skipped, 0 failed.
> 
> *The 7 skipped tests include 3 environment-dependent external integration tests and 4 optional real-provider smoke tests (`RUN_REAL_GEMINI_TESTS`, `RUN_REAL_QWEN_TESTS`, `RUN_REAL_OPENCODE_TESTS`, `RUN_REAL_KIMI_TESTS`).*

---

## 7. Multi-Agent Provider Fleet

AI Supervisor manages a heterogeneous fleet of autonomous engineering agents through a unified supervisory protocol:

| Provider | Adapter ID | Supported Interface | Untrusted Boundary | Docs |
|---|---|---|---|---|
| **Anthropic Claude Code** | `claude-code` | CLI Process (`asyncio`, `shell=False`) | Isolated Git Worktree | [Docs](docs/adapters/claude-code.md) |
| **OpenAI Codex** | `codex` | CLI Process (`asyncio`, `shell=False`) | Isolated Git Worktree | [Docs](docs/adapters/codex.md) |
| **Google Gemini** | `gemini` | Gemini CLI / SDK | Isolated Git Worktree | [Docs](docs/adapters/gemini.md) |
| **Qwen / Local Runtime** | `qwen` | Ollama / vLLM / llama.cpp / CLI | Isolated Git Worktree | [Docs](docs/adapters/qwen.md) |
| **OpenCode** | `opencode` | OpenCode CLI Process | Isolated Git Worktree | [Docs](docs/adapters/opencode.md) |
| **Moonshot Kimi** | `kimi` | Kimi CLI Process | Isolated Git Worktree | [Docs](docs/adapters/kimi.md) |

---

---

## 8. Control Room User Interface

The Control Room provides dense, real-time observability across 6 purpose-built pages:

| Page | Purpose |
| :--- | :--- |
| **Control Room** | Central operations dashboard with active mission matrix, multi-agent fleet availability badges, real-time interventions, live Cloud Sync status, and watchdog readiness. |
| **Mission Detail** | Mission objectives, interactive visual Task DAG, Jenkins JUnit build history, and Docker execution audit log. |
| **Agent Detail** | Agent profile, assigned DAG task, live tool execution trace, and exclusive file lock monitoring. |
| **Supervisor Events** | Live WebSocket event stream with dynamic story timeline and raw payload inspector. |
| **Project Memory** | Empirical facts with test proof IDs, rejected hypotheses, reviewer diagnoses, and full provenance badges (`OBSERVED`, `INFERRED`, `DECIDED`, `VERIFIED`, `REJECTED`). |
| **Approval Queue** | High-risk action approvals table with strict **Zero Implicit Approval** gate (timeouts automatically default to `DENIED`). |

---

## 9. Cloud Sync & Multi-Device Continuity (Phase 12)

AI Supervisor features an optional, secure, local-first synchronization engine enabling seamless project continuity between developer workstations (e.g. laptop to office desktop):
- **Local Authority Invariant**: Cloud sync replicates state but is never a higher authority than the local Supervisor. Local safety policy always wins.
- **Offline-First Outbox/Inbox**: Full supervisory execution operates 100% offline; changes queue locally and flush asynchronously when online.
- **Zero-Secret Data Boundary**: All API keys, private keys, passwords, and machine-specific host paths are scrubbed into redactions and relative tokens before leaving the workstation.
- **Deterministic Conflict Resolution**: Epistemic promotion rules protect verified facts from stale downgrades; task and verification outcomes never regress.

---

## 10. Documentation Index

- [Architecture Guide](docs/architecture.md) — Comprehensive technical design and data flows.
- [Cloud Sync Architecture](docs/sync-architecture.md) — Local-first synchronization engine design.
- [Sync Protocol v1 Specification](docs/sync-protocol.md) — Versioned request/response sync protocol models.
- [Device Security & Data Boundary](docs/device-security.md) — Cryptographic auth, instant revocation, and sanitizer guarantees.
- [Multi-Device Continuity Guide](docs/multi-device.md) — Multi-workstation project continuity and pairing guide.
- [IDE Integration Guide (VS Code)](docs/ide-integration.md) — Visual Studio Code extension architecture, views, commands, and security.
- [Absence Mode Specification](docs/absence-mode.md) — Bounded autonomy policy, authority hierarchy, and safety invariants.
- [Multi-Agent Provider Fleet](docs/roadmap.md#phase-10-multi-agent-provider-fleet) — Heterogeneous fleet architecture and test coverage.
- [Claude Code Adapter Guide](docs/adapters/claude-code.md) — Anthropic Claude Code adapter specification.
- [Codex Adapter Guide](docs/adapters/codex.md) — OpenAI Codex adapter specification.
- [Gemini Adapter Guide](docs/adapters/gemini.md) — Google Gemini CLI adapter specification.
- [Qwen Local Adapter Guide](docs/adapters/qwen.md) — Qwen local runtime & untrusted boundary guide.
- [OpenCode Adapter Guide](docs/adapters/opencode.md) — OpenCode CLI adapter specification.
- [Kimi Adapter Guide](docs/adapters/kimi.md) — Moonshot Kimi CLI adapter specification.
- [Hackathon Requirements Mapping](docs/hackathon-requirements.md) — Feature-by-feature evaluation matrix.
- [3-Minute Demo Presentation Script](docs/demo-script.md) — Stage presentation script with timestamps and visual cues.
- [Killer Demo Detailed Guide](docs/demo.md) — Step-by-step demonstration walkthrough.
- [Deployment Guide](docs/deployment.md) — Nebius AI Studio and container deployment guide.
- [Docker Execution Hardening](docs/docker-execution.md) — Sandbox security profiles and privilege isolation.
- [Jenkins CI Integration](docs/jenkins-integration.md) — Independent continuous integration verification pipeline.
- [Mission Control Plane](docs/control-plane.md) — Agent registry, file locking, and multi-mission orchestration.
- [Reliability & Adversarial Report](docs/reliability-report.md) — 24-scenario adversarial failure test matrix.

---

## 9. Security & Safety Principles

1. **Zero Implicit Approval**: High-risk actions require explicit human operator approval. Any approval timeout strictly defaults to `DENIED`. Absence of response never grants permission.
2. **Credential Sanitization**: Bearer tokens, API keys, passwords, and private URLs are stripped from tool execution traces, event payloads, and UI streams before emission.
3. **Single-Host Container Sandboxing**: When Docker is active, untrusted agent code runs with dropped Linux capabilities (`cap_drop=["ALL"]`), disabled privilege escalation (`security_opt=["no-new-privileges:true"]`), zero network egress (`network_mode="none"`), non-root execution (`USER worker`), hard memory limits (`512MB`), CPU quotas (`1.0`), PID ceilings (`128`), and output truncation (50,000 characters). Host roots, home directories, and the Docker socket are strictly rejected.
4. **Independent Verification**: No agents is permitted to certify its own success. Passing is only awarded after external Jenkins CI execution and Verifier validation.

---

## 10. License

This project is open-source software licensed under the [MIT License](LICENSE).
