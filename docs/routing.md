# Dynamic Agent Routing Engine (Phase 6)

AI Supervisor features a deterministic, capability-aware routing layer located in `core/routing/`.

## 1. Core Invariant

> **"Routing is a Supervisor decision based on task requirements and available agent capabilities. Agents do NOT self-select or influence their own routing score."**

The router is a pure control-plane component. Agents are external runtimes that execute work; the Supervisor decides who receives that work.

---

## 2. Routing Architecture

The router does not execute tasks. It answers: *"Given this task and the agents currently available, which agent should handle it?"*

```text
Task
 ↓
Task Requirements (Required + Preferred Capabilities, Constraints)
 ↓
Available Registered Agents (AdapterRegistry)
 ↓
Eligibility Gate (Exclusions, Availability Probes, Required Capabilities)
 ↓
Deterministic Routing Scoring (Base + Capabilities + Historical Reliability)
 ↓
Deterministic Tie-Breaking
 ↓
Routing Decision (ROUTE / NO_ELIGIBLE_AGENT / REQUIRE_REVIEW)
 ↓
AgentAdapter Execution / Task Dispatch
```

---

## 3. Domain Models

Located in `core/routing/models.py`:

* **`TaskRequirements`**: Extracted metadata describing `task_type`, `required_capabilities`, `preferred_capabilities`, `constraints`, and `scope`.
* **`RoutingCandidate`**: Evaluation state for a candidate agent including `eligible`, `score`, `capability_match_count`, `preferred_capability_match_count`, `availability_status`, `ineligibility_reasons`, and `score_breakdown`.
* **`RoutingRequest`**: Request payload containing `mission_id`, `task_id`, `task_requirements`, `excluded_agent_ids`, `candidate_agent_ids`, and optional `context`.
* **`RoutingDecision`**: Final output containing `decision` (`ROUTE`, `NO_ELIGIBLE_AGENT`, `REQUIRE_REVIEW`), `selected_agent_id`, `selected_adapter_id`, `score`, `decision_reason`, candidate list, and timestamp.

---

## 4. Eligibility Gate & Hard Capability Matching

Before any score is computed, each registered agent is evaluated against the **Eligibility Gate**:

1. **Explicit Exclusion**: If the agent is in `excluded_agent_ids` (e.g., the failing source agent during a handoff, or an agent that previously failed on the same task), it is marked `eligible = False`.
2. **Runtime Availability**: The agent's `check_availability()` method is invoked. If `status != AVAILABLE`, the agent is marked `eligible = False` with an explicit reason (e.g., `NOT_INSTALLED`, `MISCONFIGURED`, `UNAUTHORIZED`).
3. **Required Capabilities**: The candidate must declare *all* capabilities listed in `required_capabilities`. If even a single required capability is missing, `eligible = False`.

> **Critical Invariant**: Historical performance can **never** override the hard capability gate. An agent with 100 successful completions missing `git` or `test_execution` is strictly ineligible.

---

## 5. Scoring Model & Formula

For eligible candidates, the routing score is calculated using an additive, explainable formula:

$$\text{score} = \text{capability\_score} + \text{preferred\_capability\_score} + \text{availability\_score} + \text{reliability\_score}$$

Where:
* **`capability_score`**: Base score for satisfying all required capabilities = **10.0**.
* **`preferred_capability_score`**: **+2.0** for each preferred capability present on the adapter.
* **`availability_score`**: **+2.0** when adapter availability probe returns `AVAILABLE`.
* **`reliability_score`**: Derived from verified historical evidence in SQLite:
  $$\text{net\_performance} = (\text{verified\_successes} \times 1.5) - (\text{verification\_failures} \times 2.0) - (\text{handoffs} \times 1.0)$$
  $$\text{reliability\_score} = \text{clamp}(\text{net\_performance}, -10.0, 10.0)$$

### Cold-Start Behavior
If an agent has zero recorded historical tasks ($0\text{ successes}, 0\text{ failures}, 0\text{ handoffs}$):
* $\text{reliability\_score} = \mathbf{0.0}$ (strictly neutral).
* The cold-start agent remains eligible and selectable based on its capability and availability scores.

---

## 6. Deterministic Tie-Breaking

When two or more candidates achieve identical total scores, ties are resolved deterministically without randomness:
1. **Total capability count**: Prefer the agent with the tighter/more specialized capability footprint to avoid over-allocation.
2. **Fewer historical verification failures**: Lower failure count preferred.
3. **Fewer historical handoffs**: Lower handoff count preferred.
4. **Stable lexicographical order**: Sorting by `agent_id` guarantees identical results across multiple evaluations.

---

## 7. Routing Decisions

* **`ROUTE`**: At least one candidate is eligible. The highest-ranked candidate is assigned to `selected_agent_id`.
* **`NO_ELIGIBLE_AGENT`**: All candidates failed the eligibility gate (e.g., missing required capabilities or offline). Supervisor blocks the task from unverified execution and enters human review.
* **`REQUIRE_REVIEW`**: Routing requirements were malformed, empty, or ambiguous.

---

## 8. Explainability

Every `RoutingDecision` generates a human-readable explanation derived from real candidate data:

```text
Selected: codex
Score: 23.00
Reason: Selected codex (score 23.00) with 4/4 required and 1/1 preferred capabilities.
Historical Record: 8 verified successes, 1 verification failures, 0 handoffs.

Candidates Evaluated:
- codex: ELIGIBLE | score=23.00 (base=10.0, preferred=2.0, avail=2.0, rel=9.0)
- claude_code: ELIGIBLE | score=14.00 (base=10.0, preferred=2.0, avail=2.0, rel=0.0)
```

---

## 9. Handoff Integration (Phase 5 + Phase 6)

In Phase 5, handoffs required manual or deterministic hardcoded target selection. Phase 6 integrates the router directly into `HandoffEngine`:
1. When a watchdog or verifier flags a failure, `execute_handoff(target_agent_id="auto")` triggers a `RoutingRequest`.
2. The failing source agent is placed in `excluded_agent_ids`, preventing $A \to A$ ping-pong handoffs.
3. The router queries the registry, scores alternative candidates, and returns the best eligible alternative (e.g. `codex`).
4. The `HandoffEngine` packages the context, prepares the worktree, and dispatches the task to the selected target.

---

## 10. Persistence & Lifecycle Events

* **Table `routing_decisions`**: Persisted in SQLite WAL (`routing_id`, `mission_id`, `task_id`, `selected_agent_id`, `selected_adapter_id`, `score`, `decision`, `reason`, `candidates_evaluated`, `created_at`). Survives supervisor reboots.
* **EventBus Events**:
  * `routing.started`: Dispatched when evaluation begins.
  * `routing.candidate.evaluated`: Emitted per candidate with score breakdown.
  * `routing.completed`: Emitted upon successful `ROUTE` decision.
  * `routing.failed`: Emitted when `NO_ELIGIBLE_AGENT` or `REQUIRE_REVIEW` occurs.

---

## 11. Concrete Routing Example

```python
from core.routing import RoutingEngine, RoutingRequest, TaskRequirements

req = RoutingRequest(
    mission_id="msn_101",
    task_id="tsk_202",
    task_objective="Fix authentication token validation",
    task_requirements=TaskRequirements(
        task_type="bug_fix",
        required_capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
        preferred_capabilities=["terminal_execution"],
    ),
)

decision = await routing_engine.route(req)
print(decision.decision)           # RoutingDecisionType.ROUTE
print(decision.selected_agent_id)  # "codex"
print(decision.decision_reason)    # Full deterministic breakdown
```
