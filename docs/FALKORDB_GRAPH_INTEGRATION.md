# FalkorDB Integration: Graph Memory & Coordination Layer

## Track 02: Agent Memory and Coordination

### AI Supervisor — Graph-Powered Memory and Coordination for AI Agents

> **AI Supervisor turns FalkorDB into a persistent context layer for long-running AI-agent workflows.** It connects missions, tasks, execution attempts, failures, recovery decisions, handoffs, artifacts, and verification evidence into a queryable property graph. Before dispatching work or attempting recovery, the supervisor retrieves relevant dependencies and previous execution history. Its decision lineage makes it possible to inspect not only what an agent did, but also which events and relationships informed the supervisor's response. Unlike a simple execution dashboard, AI Supervisor preserves context across retries and restarts while keeping final completion dependent on verification evidence.

---

## 1. Architectural Details & Traceability Invariants

To avoid misleading traceability, three foundational invariants are strictly enforced in Cypher:

1. **Failure Causality (`FAILS_WITH`)**:
   - `(:Execution)-[:FAILS_WITH]->(:ExecutionEvent)` links an execution attempt directly to the causal failure event that explains why it failed (including error signatures and diagnostic payloads), not simply the latest generic event.
2. **Verification Lineage (`EVALUATES_EXECUTION` and `EVALUATES`)**:
   - Each verification explicitly identifies the exact execution attempt and task it evaluated:
     `(:Verification)-[:EVALUATES]->(:Task)` and `(:Verification)-[:EVALUATES_EXECUTION]->(:Execution)`.
   - This ensures a passing verification cannot accidentally validate a subsequent untested retry or mask an earlier failure.
3. **Empirical Prerequisite Gate (`DEPENDS_ON`)**:
   - The dependency readiness traversal verifies that predecessor tasks are not merely labeled with a `COMPLETED` status string, but have an accepted Verification node in FalkorDB (`is_verified = true`):
     ```cypher
     MATCH (t:Task {id: $task_id})-[:DEPENDS_ON]->(dep:Task)
     OPTIONAL MATCH (v:Verification {decision: 'ACCEPT'})-[:EVALUATES]->(dep)
     RETURN dep.id AS id, dep.title AS title, dep.status AS status, (v IS NOT NULL) AS is_verified
     ```
   - If any prerequisite lacks empirical verification, the supervisor records a `BLOCK_DISPATCH` decision and halts downstream dispatch.

---

## 2. Product Integration: Control Room Mission Graph Inspector

The graph is fully visible in the product via the interactive **FalkorDB Graph Memory Inspector** in the React Control Room (`apps/control-room`):

- **Location**: Navigating to any mission in the Control Room reveals the **FalkorDB Graph Memory** tab alongside Mandatory Plan Review.
- **8-Stage Mission Lineage Pipeline**:
  `1. Mission` → `2. Task DAG` → `3. Execution` → `4. Causal Failure` → `5. Supervisory Decision` → `6. Retry / Handoff` → `7. Independent Verification` → `8. Empirical Evidence`
- **Dual Visual Modes**:
  1. **Lineage Flow View**: Stage-by-stage causality cards displaying titles, status badges, error signatures, and supervisory decisions.
  2. **Interactive SVG Graph Topology**: Directed graph rendering with zoom, pan, reset, labeled relationship arrows, and glowing node selection.
- **Interactive Node Inspector & Evidence Drawer**:
  - Selecting any node opens a slide-over inspection drawer revealing:
    - Node Label, ID (with one-click copy), and full properties table.
    - Graph Traversal Lineage: Incoming and outgoing directed relationships.
    - Causal Failure Event Card: Explains the exact failure signature and error message.
    - **Linked Empirical Evidence Viewer**: When inspecting a task or verification, reveals all underlying test commands, AST checks, file integrity assertions, and exit codes.

---

## 3. Persistence Boundaries & Consistency Guarantees

AI Supervisor avoids distributed transaction hazards through clear persistence delineation and fail-fast semantics:

| Subsystem / Data Domain | Authoritative Store | Rationale |
| :--- | :--- | :--- |
| **Mission Records & Objectives** | SQLite (CRUD) + **FalkorDB (Graph)** | SQLite stores operational state; FalkorDB anchors the requirement graph. |
| **Task Dependencies & DAG** | **FalkorDB (Graph)** | Authoritative for dependency resolution, cycle detection, and readiness traversals. |
| **Execution Attempts & Retries** | **FalkorDB (Graph)** | Distinct attempts (`Execution` nodes) preserved with attempt numbers and statuses. |
| **Causal Failure Chains** | **FalkorDB (Graph)** | Links failed attempts to specific execution events with `FAILS_WITH`. |
| **Supervisory Recovery Decisions**| **FalkorDB (Graph)** | Traced via `RESPONDS_TO` (ExecutionEvent) and `SELECTS` (Agent). |
| **Handoff Provenance & Context** | **FalkorDB (Graph)** | Direct context transfer graph (`Handoff TRANSFERS_CONTEXT Task`). |
| **Independent Verification Evidence**| **FalkorDB (Graph)** | Proof lineage: `Verification EVALUATES Task`, `EVALUATES_EXECUTION`, and `SUPPORTED_BY Evidence`. |
| **Transactional Audit Log & Sync** | SQLite | High-frequency write-ahead logging and multi-device sync outbox. |

### Consistency & Recovery Guarantees
- **No Silent Fallback**: If FalkorDB disconnects mid-mission, operations immediately raise `FalkorDBUnavailableError` (HTTP 503). The system never silently pretends graph-dependent decisions or verifications succeeded.
- **Replay Idempotency**: All graph writes use parameterized Cypher `MERGE` on unique IDs (`id`). Replaying the mission event stream or re-evaluating the task DAG produces zero duplicate nodes or relationships.
- **Restart Durability**: All execution attempts, failure events, decisions, and evidence persist in the FalkorDB Docker volume. Upon cold process restart, the supervisor queries FalkorDB to seamlessly restore in-flight context.

---

## 4. Property Graph Schema

### Node Labels
- **`(:Mission)`**: `{id, title, goal, repository_path, status, created_at, updated_at}`
- **`(:Requirement)`**: `{id, mission_id, description, category, created_at}`
- **`(:Task)`**: `{id, mission_id, title, order, status, expected_files, created_at, updated_at}`
- **`(:Agent)`**: `{id, agent_type, model, display_name, status, created_at, updated_at}`
- **`(:Execution)`**: `{id, task_id, mission_id, agent_id, attempt_number, status, started_at, completed_at, error_signature, summary}`
- **`(:ExecutionEvent)`**: `{id, execution_id, event_type, severity, payload_json, timestamp}`
- **`(:Decision)`**: `{id, mission_id, task_id, decision_type, action, reason, timestamp}`
- **`(:Handoff)`**: `{id, task_id, source_agent, target_agent, trigger, status, context_summary, timestamp}`
- **`(:Artifact)`**: `{id, file_path, artifact_type, hash, created_at}`
- **`(:Evidence)`**: `{id, evidence_type, description, passed, empirical_data, created_at}`
- **`(:Verification)`**: `{id, task_id, mission_id, execution_id, decision, summary, verified_at}`

### Relationships
- `(:Mission)-[:HAS_REQUIREMENT]->(:Requirement)`
- `(:Mission)-[:CONTAINS_TASK]->(:Task)`
- `(:Task)-[:DEPENDS_ON]->(:Task)`
- `(:Agent)-[:EXECUTES]->(:Execution)`
- `(:Execution)-[:FOR_TASK]->(:Task)`
- `(:Execution)-[:EMITS]->(:ExecutionEvent)`
- `(:Execution)-[:PRODUCES]->(:Artifact)`
- `(:Execution)-[:FAILS_WITH]->(:ExecutionEvent)`
- `(:Decision)-[:RESPONDS_TO]->(:ExecutionEvent)`
- `(:Decision)-[:SELECTS]->(:Agent)`
- `(:Handoff)-[:TRANSFERS_CONTEXT]->(:Task)`
- `(:Verification)-[:EVALUATES]->(:Task)`
- `(:Verification)-[:EVALUATES_EXECUTION]->(:Execution)`
- `(:Verification)-[:SUPPORTED_BY]->(:Evidence)`

---

## 5. Key Cypher Queries & Operational Impact

### 1. Task Coordination & Dependency Readiness Traversal
```cypher
MATCH (t:Task {id: $task_id})-[:DEPENDS_ON]->(dep:Task)
OPTIONAL MATCH (v:Verification {decision: 'ACCEPT'})-[:EVALUATES]->(dep)
RETURN dep.id AS id, dep.title AS title, dep.status AS status, (v IS NOT NULL) AS is_verified
```
*Operational Impact*: Directly gates task dispatch. If any predecessor task lacks empirical verification, dispatch is rejected with a `BLOCK_DISPATCH` decision.

### 2. Prior Failure History Retrieval for Informed Recovery
```cypher
MATCH (e:Execution {task_id: $task_id, status: 'FAILED'})
OPTIONAL MATCH (e)-[:FAILS_WITH]->(evt:ExecutionEvent)
OPTIONAL MATCH (d:Decision)-[:RESPONDS_TO]->(evt)
RETURN e.id, e.attempt_number, e.agent_id, e.error_signature, evt.id, evt.event_type, d.id, d.action, d.reason
ORDER BY e.attempt_number ASC
```
*Operational Impact*: The supervisor extracts prior failure signatures from FalkorDB and injects them as negative constraints or triggers an agent swap (e.g., routing from Claude to Codex with iterative parser constraints).

### 3. Supervisory Decision Lineage
```cypher
MATCH (d:Decision {mission_id: $mission_id})
OPTIONAL MATCH (d)-[:RESPONDS_TO]->(evt:ExecutionEvent)
OPTIONAL MATCH (d)-[:SELECTS]->(a:Agent)
RETURN d.id, d.task_id, d.decision_type, d.action, d.reason, d.timestamp, evt.id, evt.event_type, a.id, a.display_name
ORDER BY d.timestamp ASC
```
*Operational Impact*: Provides complete explainability. Operators can trace exactly which failure event triggered an intervention and which agent was dispatched to fix it.

### 4. Independent Verification Evidence Traceability
```cypher
MATCH (v:Verification {task_id: $task_id})-[:EVALUATES]->(t:Task)
OPTIONAL MATCH (v)-[:EVALUATES_EXECUTION]->(e:Execution)
OPTIONAL MATCH (v)-[:SUPPORTED_BY]->(ev:Evidence)
RETURN v.id, v.decision, v.summary, v.verified_at, e.id AS execution_id,
       collect({id: ev.id, type: ev.evidence_type, description: ev.description, passed: ev.passed, data: ev.empirical_data}) AS evidence
```
*Operational Impact*: Proves that claimed completion is supported by concrete, empirical evidence rather than worker self-reports.

---

## 6. Verification & Automated Test Suites

The test suite validates the integration across 15 automated test cases:

```bash
python -m pytest tests/test_graph_driven_decisions.py tests/test_falkordb_consistency_recovery.py tests/test_falkordb_graph_memory.py -v
```

### Verified Test Matrix:
1. `test_connection_and_health_reporting` — PASS
2. `test_idempotent_creation` — PASS
3. `test_task_dependency_traversal` — PASS
4. `test_failure_retrieval_for_retry` — PASS
5. `test_handoff_context_retrieval` — PASS
6. `test_preservation_of_distinct_attempts` — PASS
7. `test_verification_evidence_traceability` — PASS
8. `test_unavailable_falkordb_fails_clearly` — PASS
9. `test_persistence_across_restart` — PASS
10. `test_plan_approval_gate_enforced_with_graph` — PASS
11. `test_unverified_prerequisite_blocks_task_dispatch` — PASS (Priority 3)
12. `test_prior_failure_history_guides_recovery_routing` — PASS (Priority 3)
13. `test_replay_idempotency_does_not_duplicate_nodes_or_edges` — PASS (Priority 2)
14. `test_mid_mission_disconnection_raises_falkordb_unavailable_error` — PASS (Priority 2)
15. `test_state_recovery_across_application_restart` — PASS (Priority 2)

---

## 7. How to Run the Demonstration

### 1. Start FalkorDB
```bash
docker compose up -d
```

### 2. Run the End-to-End Real Mission Workflow
```bash
python demo_falkordb_workflow.py
```

### 3. Launch the Backend & Web Control Room
```bash
# Terminal 1: FastAPI Backend
uvicorn apps.api.main:app --port 8000

# Terminal 2: React Control Room
cd apps/control-room
npm run dev
```

Navigate to `http://localhost:5173`, select any mission, and click the **FalkorDB Graph Memory** tab to inspect the live property graph and linked evidence drawer.
