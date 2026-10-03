# Nebius Production & Hackathon Deployment Guide

This document details the production, hackathon, and local deployment architecture for the **AI Work Supervisor** system, powered by **NVIDIA Nemotron** on **Nebius AI Studio** infrastructure.

---

## 1. Product Principle & Core Objective

The **AI Work Supervisor** is a **Control Room & Supervisory Nervous System for Autonomous AI Work**.

> *"AI agents are working, the Supervisor is watching them, and the system intervenes when they go wrong."*

It is engineered for real-world autonomous software development tasks where unmonitored agents loop infinitely, exceed budgets, corrupt files outside their assigned task boundaries, or falsely report success. The system provides real-time oversight, independent CI verification, safe container sandboxing, and autonomous recovery delegation.

---

## 2. Deployment Architecture & Infrastructure Topology

```
                          ┌───────────────────────────┐
                          │    Human Operator /       │
                          │   Control Room UI (Vite)  │
                          └─────────────┬─────────────┘
                                        │ HTTP / WebSocket (:8000)
                                        ▼
                          ┌───────────────────────────┐
                          │   FastAPI Control Plane   │
                          │  (/health, /ready, /ws)   │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │  Supervisor Engine Core   │
                          │(Deterministic Watchdogs & │
                          │ Empirical Memory Store)   │
                          └─────────────┬─────────────┘
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
┌──────────────────────────┐ ┌─────────────────────┐ ┌──────────────────────────┐
│   Nebius AI Cloud        │ │ Docker Sandbox      │ │ Independent Jenkins CI   │
│   (NVIDIA Nemotron)      │ │ Container Engine    │ │ Pipeline (JUnit Report)  │
│                          │ │                     │ │                          │
│ • Model:                 │ │ • Isolated Workdir  │ │ • Nonce validation       │
│   nemotron-4-340b        │ │ • No Network        │ │ • Regressions check      │
│ • Endpoint:              │ │ • Dropped Caps      │ │ • Empirical ground truth │
│   api.studio.nebius.ai/v1│ │ • Memory/CPU limits │ │ • Prevents false success │
└──────────────────────────┘ └─────────────────────┘ └──────────────────────────┘
             │                          ▲                          │
             │ Causal Diagnosis         │ Shell Execution          │ Independent
             │ & Recovery Decision      │                          │ Evidence
             ▼                          │                          │
┌───────────────────────────────────────┴──────────────────────────┴────────────┐
│                       Autonomous Agent Fleet                                 │
│          Planner  •  Worker_01  •  Reviewer_01  •  Verifier_01               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Component Placement: Nebius vs Local/External Infrastructure

To preserve engineering accuracy and honesty:

| Component | Execution Host / Provider | Description |
| :--- | :--- | :--- |
| **Supervisory Reasoning** | **Nebius AI Studio (Cloud)** | NVIDIA open-source `nvidia/nemotron-4-340b-instruct` hosted on Nebius AI Cloud for causal anomaly diagnosis, loop recovery strategy, and reviewer delegation. |
| **API & Control Plane** | Nebius Cloud VM / Local Host | FastAPI web server, EventBus, InMemoryEventStore, and `/ws/events` broadcaster. |
| **Control Room UI** | Client Browser / CDN / Vite Host | React + TypeScript developer cockpit running on desktop/tablet browsers. |
| **Execution Sandboxes** | Local Host / Docker Daemon | Isolated worker execution sandboxes (`docker run`) with disabled network, CPU/RAM quotas, and restricted workspace mounts. |
| **CI Verification** | Jenkins Server / Mock Service | Independent continuous integration runner executing automated test suites and providing empirical JUnit proofs. |

---

## 3. Environment Variables & Configuration Matrix

Configuration is strictly environment-driven. **Never commit secrets such as `NEBIUS_API_KEY` or `JENKINS_API_TOKEN` to version control.**

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PORT` | `8000` | FastAPI server listening port. |
| `HOST` | `0.0.0.0` | Binding interface address. |
| `ENVIRONMENT` | `development` | `production`, `staging`, or `development`. |
| **Nebius / Nemotron** | | |
| `NEBIUS_API_KEY` | *(None / Empty)* | Nebius Studio API key. When omitted, supervisor safely uses local deterministic mock. |
| `NEBIUS_BASE_URL` | `https://api.studio.nebius.ai/v1` | Nebius OpenAI-compatible API base URL. |
| `NEBIUS_MODEL` | `nvidia/nemotron-4-340b-instruct` | NVIDIA open-source foundation model on Nebius. |
| `SUPERVISOR_MODEL_TIMEOUT_SECONDS` | `20.0` | Timeout before fallback reasoning engages. |
| **Supervisor Runtime** | | |
| `SUPERVISOR_MAX_ITERATIONS` | `25` | Maximum agent iteration budget before intervention. |
| `SUPERVISOR_FAILURE_THRESHOLD` | `3` | Consecutive identical error threshold before triggering `LOOP_DETECTED`. |
| `SUPERVISOR_MAX_RECENT_EVENTS` | `20` | In-memory window size for causal timeline generation. |
| **Execution Sandbox** | | |
| `EXECUTION_BACKEND` | `local` | `local` (process isolation) or `docker` (container sandbox). |
| `EXECUTION_ALLOW_FALLBACK` | `false` | Fall back from Docker to local sandbox if daemon is offline. |
| `DOCKER_IMAGE` | `ai-work-supervisor-worker:latest` | Sandboxed worker container image. |
| `DOCKER_MEMORY_LIMIT` | `512m` | Hard RAM ceiling for worker tasks. |
| `DOCKER_CPU_LIMIT` | `1.0` | CPU allocation quota. |
| `DOCKER_NETWORK_DISABLED` | `true` | Restricts container egress to prevent exfiltration. |
| **Jenkins CI Integration** | | |
| `JENKINS_URL` | `http://localhost:8080` | Jenkins server base URL (or `mock` for deterministic test mode). |
| `JENKINS_JOB_NAME` | `ai-work-supervisor` | Job configured with test execution and JUnit reporting. |
| `JENKINS_USERNAME` | *(Optional)* | Service account username for Jenkins API. |
| `JENKINS_API_TOKEN` | *(Optional)* | API token for Jenkins authentication. |
| `JENKINS_TIMEOUT_SECONDS` | `30` | Build completion polling timeout. |
| **Control Room Frontend** | | |
| `VITE_API_URL` | `http://localhost:8000` | Backend API URL proxied by the frontend. |

---

## 4. Preserving Local Development & Fallback Modes

The system adheres strictly to the rule: **Local development must continue working without cloud credentials.**

1. **Zero-Secret Offline Mode**:
   - If `NEBIUS_API_KEY` is not present, `NebiusNemotronProvider` immediately falls back to `MockReasoningProvider`.
   - All 126 test suites, scenarios, and the Control Room UI work offline deterministically.
2. **Cloud Outage Resilience**:
   - If Nebius AI Studio experiences network latency, rate limits, or 5xx outages, the supervisor catches the error, logs a clean diagnostic message without crashing, and switches to safe fallback reasoning.
3. **Execution Graceful Degradation**:
   - If `EXECUTION_BACKEND=docker` is set on a machine without Docker running, setting `EXECUTION_ALLOW_FALLBACK=true` allows safe fallback to local process execution with warning events emitted to the timeline.

---

## 5. Step-by-Step Deployment Instructions

### Prerequisites
- Python 3.11+
- Node.js 18+ (for Control Room UI)
- Docker (optional, for container execution)
- Jenkins (optional, for independent CI verification)

### Step 1: Clone & Configure Environment
```bash
git clone https://github.com/M0izz/AI-Supervisior.git
cd AI-Supervisior

# Copy template and add your credentials
cp .env.example .env
```

Edit `.env` to supply your Nebius API key:
```ini
NEBIUS_API_KEY=your_nebius_studio_api_key_here
NEBIUS_BASE_URL=https://api.studio.nebius.ai/v1
NEBIUS_MODEL=nvidia/nemotron-4-340b-instruct
```

### Step 2: Install Python Backend Dependencies
```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Launch the Backend API & Control Plane
```bash
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify backend health:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### Step 4: Build & Launch the Control Room Frontend
```bash
cd apps/control-room
npm install
npm run build     # Compiles production distribution to apps/control-room/dist
npm run dev       # Starts dev server on http://localhost:5173
```

Navigate to `http://localhost:5173` to access the Control Room.

---

## 6. Health & Readiness Probes

The API exposes enterprise-grade health probes designed for Kubernetes, cloud load balancers, and observability agents:

### 1. Basic Liveness: `GET /health`
```json
{
  "status": "healthy",
  "service": "AI Work Supervisor",
  "version": "1.0.0",
  "subsystems": {
    "event_bus": "operational",
    "event_store": "operational",
    "missions": 1,
    "agents": 4,
    "supervisor_engine": "watching"
  }
}
```

### 2. Comprehensive Readiness: `GET /ready`
Checks all subsystems before accepting traffic. Returns `HTTP 200` when ready:
```json
{
  "status": "ready",
  "service": "AI Work Supervisor",
  "model_provider": {
    "status": "healthy",
    "provider": "nebius_nemotron",
    "model": "nvidia/nemotron-4-340b-instruct",
    "mode": "nebius_cloud",
    "base_url": "https://api.studio.nebius.ai/v1",
    "authenticated": true,
    "safe_fallback_active": true
  },
  "execution_backend": {
    "status": "healthy",
    "default_backend": "local",
    "allow_fallback": false,
    "local_backend": {"status": "healthy", "available": true, "sandbox_type": "restricted_process"},
    "docker_backend": {"status": "healthy", "available": true, "image": "ai-work-supervisor-worker:latest"}
  },
  "jenkins_ci": {
    "status": "healthy",
    "url": "http://localhost:8080",
    "job": "ai-work-supervisor",
    "mode": "jenkins_http"
  },
  "supervisor": {
    "status": "watching",
    "active_missions": 1,
    "active_agents": 4
  }
}
```

### 3. Subsystem Health Checks
- `GET /health/model`: NVIDIA Nemotron connection latency & model status.
- `GET /health/jenkins`: Jenkins CI server responsiveness and credentials status.
- `GET /health/execution`: Docker daemon and sandbox resource limits.

---

## 7. Execution Environments & Test Distinctions

When reviewing verification outputs, the following distinctions strictly apply:

| Tag | Infrastructure Used | Description |
| :--- | :--- | :--- |
| **REAL CLOUD TEST** | `api.studio.nebius.ai` + NVIDIA Nemotron | Real HTTP request executed against Nebius Cloud inference endpoints with live JSON parsing. |
| **LOCAL TEST** | Local host + Docker sandbox | Isolated containerized task execution on local Docker or subprocess runner. |
| **MOCK TEST** | In-memory deterministic providers | Offline regression test suites simulating CI outages, timeouts, and loop conditions. |

Never conflate mock test results with cloud test results.

---

## 8. Verification & Demonstration Commands

To run all automated verification tests:
```bash
# Run full suite (126 tests across Phases 0–10)
python -m pytest tests/ -v

# Run Phase 10 deployment tests specifically
python -m pytest tests/test_phase10_deployment.py -v

# Run interactive failure scenarios
python -m demo.scenarios.scenario_01_loop_recovery
python -m demo.scenarios.scenario_02_ci_failure
python -m demo.scenarios.scenario_03_failure_matrix
```
