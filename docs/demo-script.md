# 3-Minute Live Demo Presentation Script

> **Goal**: Present the full supervisory loop of **AI Work Supervisor** in under 3 minutes with zero fluff, high technical density, and clear visual coordination between the Control Room and the autonomous execution.

---

## Timeline & Narration

| Timestamp | Visual / Screen View | Presenter Action | Narration Script |
| :--- | :--- | :--- | :--- |
| **0:00 – 0:20** | **Slide / Control Room Overview**<br>`http://localhost:5173/` | Show the Control Room cockpit showing active agents and watchdogs. | *"AI coding agents are remarkably capable at writing initial code, but in real engineering workflows, they fail constantly: they loop on identical errors, hallucinate test passes, exceed iteration budgets, and silently modify unauthorized files. Today, we're demonstrating **AI Work Supervisor** — an autonomous control plane that acts as the nervous system for AI software work, supervising agents in real-time and intervening when they go wrong."* |
| **0:20 – 0:40** | **Mission Detail Page**<br>`http://localhost:5173/missions/msn-killer-001` | Show the Mission DAG visualizer generating 6 tasks for `sample-project`. | *"Let's dispatch a real mission: adding UTF-8 BOM CSV parsing to an existing data pipeline. The Planner immediately decomposes this goal into a directed acyclic task graph (DAG). The Supervisor validates the plan, enforces file boundary constraints, and dispatches Worker-01 to implement the parser inside an isolated Docker sandbox."* |
| **0:40 – 1:00** | **Agent Detail & Test Logs**<br>`http://localhost:5173/agents/worker_01` | Worker executes tests. Terminal and UI show test failures on line 42 (`45 passed, 2 failed`). | *"Worker-01 begins editing `src/parser.py`. It runs the test suite inside the container. But there's a subtle bug: the parser fails to strip the UTF-8 byte order mark (`\ufeff`). The worker tries to fix it naively and re-runs the tests. It fails again. It tries a third time with the same regex — and fails a third time."* |
| **1:00 – 1:20** | **Intervention Banner Flashes**<br>`http://localhost:5173/events` | Amber alert card surfaces: `LOOP DETECTED — 3 Identical Failures`. Worker transitions to `PAUSED`. | *"Notice what just happened. The agent didn't blow past its budget into an infinite loop. The Supervisor's deterministic watchdog detected a loop anomaly: three consecutive identical test failures. The Supervisor instantly revokes the worker's execution token and pauses the agent."* |
| **1:20 – 1:40** | **Supervisor Events & Nemotron Panel**<br>`http://localhost:5173/events` | Show the structured intervention card: Model `NVIDIA Nemotron-4-340B`, Action `DELEGATE → Reviewer`. | *"Now, the cognitive supervisor engages. Anomaly context is passed to **NVIDIA Nemotron-4-340B** hosted on **Nebius AI Studio**. Nemotron causal reasoning determines that Worker-01 has a flawed conceptual model. It issues a structured decision: `DELEGATE to Reviewer`. The Supervisor dispatches a specialized Reviewer agent equipped strictly with read-only inspection tools to isolate the root cause."* |
| **1:40 – 2:00** | **Project Memory Page**<br>`http://localhost:5173/memory` | Show the new `VERIFIED_FACT` (UTF-8 BOM prefix) and `REJECTED_APPROACH` (regex strip) recorded with commit hashes. | *"The Reviewer diagnoses the exact issue: `codecs.BOM_UTF8` must be stripped at the byte-stream level before decoding. This diagnosis is committed as a `VERIFIED_FACT` in Project Memory, and the worker's failed regex is permanently stored as a `REJECTED_APPROACH` so no agent repeats it. The Context Packager bundles these empirical findings into a targeted recovery package."* |
| **2:00 – 2:20** | **Mission Detail & Jenkins CI Badge**<br>`http://localhost:5173/missions/msn-killer-001` | Worker resumes with recovery prompt, writes the fix, and runs sandbox tests (`47 passed, 0 failed`). | *"Worker-01 resumes with the recovery context. It applies the correct byte-level fix. In the sandbox, all 47 tests pass! But the Supervisor does not trust the agent's self-reported success. It automatically triggers an independent Jenkins CI pipeline build."* |
| **2:20 – 2:40** | **Verification Seal Awarded**<br>`http://localhost:5173/missions/msn-killer-001` | Jenkins build #482 shows green checkmark. Verifier agent issues final stamp: `VERIFIED (47/47 tests)`. | *"Jenkins executes the pipeline independently with a cryptographic nonce, validating all 47 JUnit tests in a clean environment. The independent Verifier agent confirms zero regressions. The mission transitions to `COMPLETED`."* |
| **2:40 – 2:55** | **Supervisor Events Story Timeline**<br>`http://localhost:5173/events` | Scroll through the chronological narrative timeline showing the complete causal sequence. | *"In under 30 seconds, we went from an autonomous agent trapped in an infinite loop, to Nemotron causal diagnosis on Nebius, to reviewer analysis, persistent memory recording, targeted recovery, and independent CI verification — with zero human debugging required."* |
| **2:55 – 3:00** | **Closing Summary** | Concluding screen showing GitHub repo link and architectural pillars. | *"AI Work Supervisor transforms erratic autonomous agents into reliable, verifiable software engineering teams. Thank you!"* |

---

## Presenter Technical Checklist Before Stage

1. **Verify Services Running**:
   - Backend API: `http://localhost:8000/health` returns `{"status": "healthy"}`
   - Control Room UI: `http://localhost:5173/` loaded in browser
2. **Execute Demo Reset**:
   ```bash
   python -m demo.reset
   ```
3. **Trigger Killer Scenario Live**:
   ```bash
   python -m demo.scenarios.killer_scenario
   ```
4. **Browser Tabs Prepared**:
   - Tab 1: `http://localhost:5173/` (Control Room Overview)
   - Tab 2: `http://localhost:5173/missions/msn-killer-001` (DAG Viewer & Jenkins CI)
   - Tab 3: `http://localhost:5173/events` (Supervisor Story Timeline & Nemotron Intervention)
   - Tab 4: `http://localhost:5173/memory` (Empirical Fact & Rejected Hypotheses Store)
