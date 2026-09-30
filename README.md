# AI Work Supervisor

> **Control Room for AI Agents** — Give AI agents a goal. Let them work. The Supervisor watches what they actually do, detects failure or drift, verifies their claims, and intervenes when necessary.

Powered by **Nemotron** reasoning on **Nebius** hosted AI infrastructure.

---

## 🏛 Architecture Overview

```
                         HUMAN
                           │
                           │ Goal
                           ▼
                  ┌─────────────────┐
                  │  AI SUPERVISOR  │
                  │                 │
                  │ Rules +         │
                  │ Nemotron        │
                  └────────┬────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                    ▼             ▼
                PROJECT        POLICIES
                 MEMORY
                    │
                    ▼
        ┌───────────┼───────────┐
        ▼           ▼           ▼
     PLANNER      WORKER     VERIFIER
                    │           │
                    │           │
                    └─────┬─────┘
                          ▼
                     EVENT BUS
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
         SUPERVISOR    MEMORY     DASHBOARD
              │
      ┌───────┼────────┐
      ▼       ▼        ▼
   CONTINUE  FIX     ESCALATE
                       │
                       ▼
                     HUMAN
```

## 📂 Repository Structure

```
├── apps/
│   ├── web/                     # Frontend Control Room (React, Vite, Tailwind, React Flow)
│   └── api/                     # Backend FastAPI service (WebSockets, REST, Orchestrator)
├── core/
│   ├── events/                  # Event schemas, async EventBus, EventStore
│   ├── missions/                # Mission state machine, lifecycle manager, constraints
│   ├── tasks/                   # Task model, DAG graph resolution, scheduler
│   ├── policies/                # Autonomy levels, rule policies, safety guardrails
│   └── state/                   # AgentContextPackage, supervisor states, snapshots
├── agents/
│   ├── base.py                  # Agent base class with tool-loop & event emitter
│   ├── planner/                 # Task breakdown & plan synthesis agent
│   ├── worker/                  # Tool-executing agent (file edits, tests, commands)
│   ├── verifier/                # Independent evidence-based verification agent
│   └── reviewer/                # Anomaly diagnosis & strategy recommendation agent
├── supervisor/
│   ├── engine.py                # Dual-layer supervisor engine (Rules + Nemotron)
│   ├── rules.py                 # Deterministic anomaly detection rules
│   ├── reasoning.py             # Nemotron structured reasoning caller
│   ├── decisions.py             # Action space (CONTINUE, RETRY, DELEGATE, ROLLBACK, PAUSE, APPROVAL)
│   └── state_machine.py         # Supervisor lifecycle state machine
├── memory/
│   ├── store.py                 # Structured project memory store
│   ├── facts.py                 # Verified facts with confidence & provenance
│   ├── provenance.py            # Audit trail (OBSERVED, INFERRED, DECIDED, VERIFIED, REJECTED)
│   └── retrieval.py             # Selective cross-agent context packaging
├── tools/
│   ├── base.py                  # Sandbox-checked tool interface
│   ├── filesystem.py            # read_file, write_file, edit_file, list_files
│   ├── shell.py                 # run_command with security guards
│   ├── testing.py               # run_tests with structured output extraction
│   └── git.py                   # git_status, git_diff
├── integrations/
│   └── nebius/                  # Model-agnostic ReasoningProvider & Nebius Nemotron client
├── demo/
│   ├── sample-project/          # Isolated target workspace (CSV importer demo)
│   └── scenarios/               # Reproducible test scenarios (drift, loops, recovery)
└── docs/
    ├── architecture.md          # Complete architectural specification
    ├── supervisor.md            # Supervisory rule & reasoning specification
    ├── memory.md                # Structured memory & provenance model
    └── demo.md                  # Step-by-step killer demo script
```

## 🚀 Quickstart

### Backend API & Event Bus
```bash
# Start FastAPI backend server with real-time WebSockets
python -m uvicorn apps.api.main:app --reload --port 8000
```

### Run Tests
```bash
pytest tests/ -v
```
