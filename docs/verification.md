# Independent Verification Engine (Phase 4)

## 1. Overview & Core Product Invariant

> **Agent completion ≠ verified completion.**
> **No agent is permitted to certify its own success.**

In autonomous multi-agent software engineering, worker agents frequently drift, loop on flawed logic, or prematurely claim task completion while tests are still failing or unintended regressions have been introduced.

The **Independent Verification Engine** acts as the objective gatekeeper in AI Supervisor. When an agent signals task completion, that signal is treated strictly as an **unverified completion claim**. The Supervisor independently gathers empirical evidence directly from the isolated Git worktree, runs test suites, verifies scope boundaries, and certifies the outcome before the task can be marked `VERIFIED`.

```text
Worker Agent (e.g. Claude Code CLI)
        ↓
    task.completed (Completion Claim)
        ↓
  VerificationEngine (Independent Evaluation)
        │
        ├─ Completion Claim Structure Check
        ├─ Git / Worktree Integrity Check
        ├─ Scope & Path Traversal Check
        ├─ Independent Test Execution Check (shell=False)
        └─ Regression Comparison Check
        ↓
VerificationDecision (ACCEPT / REJECT / REQUIRE_REVIEW)
        │
        ├─ ACCEPT ────────► Task marked VERIFIED
        ├─ REJECT ────────► Task REOPENED (Not Verified)
        └─ REQUIRE_REVIEW ─► Operator Review Flagged
        │
        ▼
SQLite WAL Persistence & Canonical Protocol Events
```

---

## 2. Verification Decision Model

Every verification pass evaluates to a structured `VerificationResult` containing a definitive decision:

| Decision | Meaning | Task State Transition | Event Emitted |
| :--- | :--- | :--- | :--- |
| **`ACCEPT`** | All required criteria satisfied with empirical evidence; 0 failures. | `IN_PROGRESS` / `COMPLETED` $\to$ `VERIFIED` | `verification.result` (`passed: 1, failed: 0`) |
| **`REJECT`** | Objective evidence proves test failure, out-of-scope mutation, or regression. | Reopened to `IN_PROGRESS` with failure details | `verification.failed` (`decision: REJECT`) |
| **`REQUIRE_REVIEW`** | Task lacks structured acceptance criteria or contains unresolvable ambiguity. | Flagged for operator review | `supervisor.human_required` |

---

## 3. Verification Check Taxonomy

The verifier executes five modular check suites in sequence:

### A. Completion Claim Check (`COMPLETION_CLAIM`)
- Verifies that the task possesses structured, machine-evaluable acceptance criteria (test requirements, expected files, or allowed files).
- If a task lacks any verifiable criteria (e.g. "make the code look nicer" without tests), the check flags a `WARN`, preventing blind automated approval and routing to `REQUIRE_REVIEW`.

### B. Git / Worktree Integrity Check (`GIT`)
- Verifies that the designated workspace exists, is accessible, and retains its Git worktree structure.
- Gathers Git metadata: current HEAD commit, porcelain working-tree status, and uncommitted modification counts.

### C. Files & Scope Boundary Check (`SCOPE`)
- Inspects all modified and untracked files across the workspace.
- **Path Traversal Guard**: Flags directory escapes (`../`, leading `/`, drive letters) as hard failures.
- **Protected Files Guard**: Forbids modifications to `.env`, `.git/`, `schema.sql`, and credentials.
- **Task Scope Whitelist**: Compares changes against `TaskDispatchPackage.allowed_files`; any unauthorized file edit triggers `REJECT`.
- **Expected Files Presence**: Confirms that files declared in `Task.expected_files` physically exist on disk.

### D. Independent Test Execution Check (`TESTS`)
- Independently executes test commands declared in `TaskDispatchPackage.verification_requirements` (e.g. `pytest tests/test_auth.py`).
- **Security Invariants**:
  - `shell=False` execution using safe argument tokenization.
  - Commands execute strictly within the isolated worktree directory (`cwd=workspace`).
  - Output bounded to prevent buffer exhaustion.
  - Strict timeout enforcement (`timeout` ceiling). Any command timeout immediately produces a `FAIL` and `REJECT` decision.

### E. Regression Comparison Check (`REGRESSION`)
- Compares current test outcomes against `baseline_test_results` (when a baseline is available).
- Tests that were passing in the baseline but fail in the current run are classified as regressions, triggering `REJECT`.
- If no baseline is available, the check records `SKIPPED` with explicit diagnostic evidence rather than fabricating assumptions.

---

## 4. SQLite Persistence & Durability

Verification results are saved to the `verifications` table in SQLite WAL storage via `VerificationRepository`:
- Fields: `verification_id`, `mission_id`, `task_id`, `verification_type`, `status`, `command`, `details` (full JSON check breakdown), and `created_at`.
- **Restart Durability**: All verification decisions and evidence survive application restarts and are queryable via `list_by_mission()` and `list_by_task()`.

---

## 5. Security & Isolation Guarantees

1. **Untrusted Agent Boundary**: The verifier never trusts the agent's stdout claims. Even if the agent prints `"All 50 tests passed 100%"`, the verifier independently runs the tests.
2. **No Shell Injections**: Verification commands are executed using `subprocess.run(shell=False)` with tokenized arguments.
3. **Primary Working Tree Protection**: All file inspections and test executions take place inside the isolated Git worktree (`.supervisor/worktrees/`), never touching the developer's primary checkout.
4. **Bounded Telemetry**: Standard output and error streams are truncated at 50KB to protect against runaway stdout loops.

---

## 6. Known Limitations

1. **Baseline Availability**: Independent regression detection requires an explicit baseline test execution record. If none exists, the regression check gracefully skips without blocking.
2. **Language Runtime Dependency**: Test commands require the relevant runtime (e.g. Python, Node) to be installed in the local environment.
3. **Future Extensibility**: Phase 4 focuses on deterministic test execution and Git diff inspection; automated static analysis (linters, typecheckers) can be plugged in as additional verification checks.

---

## 7. Killer Scenario: False Claim Interception

```text
1. Mission: "Fix authentication tests"
2. Task: "Repair authentication test failures"
3. Agent (Claude Code): Modifies auth.py, emits task.completed.
   Agent Claim: "Authentication tests are fixed and passing."
4. Supervisor: Intercepts claim. Task is NOT marked VERIFIED.
5. Verifier: Runs 'pytest test_auth.py' in worktree.
6. Test Result: test_token_expiry fails with 403 != 200.
7. Verifier Decision: REJECT.
8. State Update: Task status reverted to IN_PROGRESS (reopened).
9. Outcome: agent_claimed_success == True, verified_success == False.
```
