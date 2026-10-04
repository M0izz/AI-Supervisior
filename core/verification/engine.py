import asyncio
import logging
from typing import Any, Dict, List, Optional
import uuid

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.protocol.events import ProtocolEventType
from core.protocol.schema import TaskDispatchPackage
from core.verification.models import (
    VerificationCheck,
    VerificationCheckStatus,
    VerificationCheckType,
    VerificationContext,
    VerificationDecision,
    VerificationResult,
)
from core.verification.checks import (
    run_git_check,
    run_scope_check,
    run_test_check,
    run_regression_check,
    run_completion_claim_check,
)

logger = logging.getLogger("supervisor.verification.engine")


class VerificationEngine:
    """
    Independent Verification Engine.
    Operates independently from the agent's self-assessment.
    Inspects actual worktree files, executes test suites, checks task scope boundaries,
    and enforces: CLAIMED COMPLETE != VERIFIED COMPLETE.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        repository: Optional[Any] = None,
        task_manager: Optional[Any] = None,
        worktree_manager: Optional[Any] = None,
    ):
        self.event_bus = event_bus
        self.repository = repository
        self.task_manager = task_manager
        self.worktree_manager = worktree_manager
        self._lock = asyncio.Lock()

    async def verify(self, context: VerificationContext) -> VerificationResult:
        """
        Executes independent verification checks against the task worktree.
        Produces a deterministic VerificationResult (ACCEPT, REJECT, or REQUIRE_REVIEW).
        Persists the result to SQLite and updates the task state.
        """
        verification_id = f"ver_{uuid.uuid4().hex[:12]}"
        logger.info(
            f"[VERIFIER] Starting independent verification {verification_id} for "
            f"task {context.task_id} (mission {context.mission_id})"
        )

        # 1. Emit VERIFICATION_STARTED event
        if self.event_bus:
            try:
                await self.event_bus.publish(
                    Event(
                        mission_id=context.mission_id,
                        task_id=context.task_id,
                        agent_id="verifier",
                        type=EventType.VERIFICATION_STARTED,
                        severity=EventSeverity.INFO,
                        payload={
                            "verification_id": verification_id,
                            "event_type": ProtocolEventType.VERIFICATION_STARTED.value,
                            "workspace": context.workspace,
                            "verification_requirements": context.verification_requirements,
                        },
                    )
                )
            except Exception as e:
                logger.warning(f"[VERIFIER] Failed to publish verification.started: {e}")

        # 2. Run checks sequentially
        checks: List[VerificationCheck] = []

        # Check A: Completion Claim & Criteria Structure
        check_claim = run_completion_claim_check(context)
        checks.append(check_claim)

        # Check B: Git / Worktree Integrity
        check_git = run_git_check(context)
        checks.append(check_git)

        # Check C: Files & Scope Boundaries (only if workspace exists)
        if check_git.status != VerificationCheckStatus.FAIL:
            check_scope = run_scope_check(context)
            checks.append(check_scope)
        else:
            checks.append(
                VerificationCheck(
                    check_id="check_scope",
                    check_type=VerificationCheckType.SCOPE,
                    description="Verify modifications respect declared task scope boundaries",
                    status=VerificationCheckStatus.SKIPPED,
                    message="Skipped because workspace does not exist.",
                )
            )

        # Check D: Independent Test Execution (only if workspace exists and scope didn't fatal fail)
        if check_git.status != VerificationCheckStatus.FAIL:
            check_tests = run_test_check(context)
            checks.append(check_tests)
        else:
            checks.append(
                VerificationCheck(
                    check_id="check_tests",
                    check_type=VerificationCheckType.TESTS,
                    description="Run independent test verification commands",
                    status=VerificationCheckStatus.SKIPPED,
                    message="Skipped because workspace does not exist.",
                )
            )

        # Check E: Regression Verification
        test_evidence = next((c.evidence for c in checks if c.check_type == VerificationCheckType.TESTS), {})
        check_regression = run_regression_check(context, current_test_evidence=test_evidence)
        checks.append(check_regression)

        # 3. Determine Verification Decision
        failed_checks = [c.check_id for c in checks if c.status == VerificationCheckStatus.FAIL]
        warning_checks = [c for c in checks if c.status == VerificationCheckStatus.WARN]
        warnings = [w.message or w.check_id for w in warning_checks]

        aggregate_evidence = {
            c.check_id: {"status": c.status.value, "evidence": c.evidence}
            for c in checks
        }

        if failed_checks:
            decision = VerificationDecision.REJECT
            status = "FAILED"
            summary = (
                f"Independent verification REJECTED: {len(failed_checks)} check(s) failed "
                f"({', '.join(failed_checks)})."
            )
        elif warning_checks:
            decision = VerificationDecision.REQUIRE_REVIEW
            status = "REVIEW_REQUIRED"
            summary = (
                f"Independent verification REQUIRES OPERATOR REVIEW: "
                f"{warnings[0] if warnings else 'Ambiguous acceptance criteria.'}"
            )
        else:
            decision = VerificationDecision.ACCEPT
            status = "PASSED"
            summary = "Independent verification ACCEPTED: All verification checks passed with empirical evidence."

        result = VerificationResult(
            verification_id=verification_id,
            mission_id=context.mission_id,
            task_id=context.task_id,
            agent_id=context.agent_id,
            decision=decision,
            status=status,
            checks=checks,
            evidence=aggregate_evidence,
            failed_checks=failed_checks,
            warnings=warnings,
            summary=summary,
        )

        # 4. Persist result to SQLite
        if self.repository:
            try:
                cmd_run = None
                if context.verification_requirements:
                    cmd_run = "; ".join(context.verification_requirements)
                await self.repository.save(
                    mission_id=context.mission_id,
                    task_id=context.task_id,
                    verification_type="independent_verifier",
                    status=status,
                    command=cmd_run,
                    details=result.model_dump(mode="json"),
                    verification_id=verification_id,
                )
            except Exception as e:
                logger.warning(f"[VERIFIER] Failed to persist verification result to SQLite: {e}")

        # 5. Integrate with TaskManager State
        if self.task_manager:
            try:
                if decision == VerificationDecision.ACCEPT:
                    await self.task_manager.verify_task(
                        mission_id=context.mission_id,
                        task_id=context.task_id,
                        caller_role="VERIFIER",
                        tests_passed=True,
                        evidence=result.evidence,
                    )
                    logger.info(f"[VERIFIER] Task {context.task_id} successfully transitioned to VERIFIED.")
                elif decision == VerificationDecision.REJECT:
                    await self.task_manager.reopen_task(
                        mission_id=context.mission_id,
                        task_id=context.task_id,
                        reason=summary,
                    )
                    logger.warning(f"[VERIFIER] Task {context.task_id} reopened due to verification failure.")
            except Exception as e:
                logger.warning(f"[VERIFIER] TaskManager integration encountered error: {e}")

        # 6. Publish outcome events onto EventBus
        if self.event_bus:
            try:
                if decision == VerificationDecision.ACCEPT:
                    await self.event_bus.publish(
                        Event(
                            mission_id=context.mission_id,
                            task_id=context.task_id,
                            agent_id="verifier",
                            type=EventType.VERIFICATION_RESULT,
                            severity=EventSeverity.INFO,
                            payload={
                                "verification_id": verification_id,
                                "event_type": ProtocolEventType.VERIFICATION_PASSED.value,
                                "decision": decision.value,
                                "passed": 1,
                                "failed": 0,
                                "summary": summary,
                                "evidence": aggregate_evidence,
                            },
                        )
                    )
                elif decision == VerificationDecision.REJECT:
                    await self.event_bus.publish(
                        Event(
                            mission_id=context.mission_id,
                            task_id=context.task_id,
                            agent_id="verifier",
                            type=EventType.VERIFICATION_FAILED,
                            severity=EventSeverity.CRITICAL,
                            payload={
                                "verification_id": verification_id,
                                "event_type": ProtocolEventType.VERIFICATION_FAILED.value,
                                "decision": decision.value,
                                "passed": 0,
                                "failed": len(failed_checks),
                                "failed_checks": failed_checks,
                                "summary": summary,
                                "evidence": aggregate_evidence,
                            },
                        )
                    )
                else:  # REQUIRE_REVIEW
                    await self.event_bus.publish(
                        Event(
                            mission_id=context.mission_id,
                            task_id=context.task_id,
                            agent_id="verifier",
                            type=EventType.SUPERVISOR_HUMAN_REQUIRED,
                            severity=EventSeverity.WARNING,
                            payload={
                                "verification_id": verification_id,
                                "event_type": ProtocolEventType.VERIFICATION_COMPLETED.value,
                                "decision": decision.value,
                                "summary": summary,
                                "warnings": warnings,
                                "evidence": aggregate_evidence,
                            },
                        )
                    )
            except Exception as e:
                logger.warning(f"[VERIFIER] Failed to publish verification completion events: {e}")

        return result

    async def verify_dispatch(
        self,
        dispatch: TaskDispatchPackage,
        completion_claim: Optional[Dict[str, Any]] = None,
        baseline_test_results: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Convenience entrypoint verifying task execution directly from a TaskDispatchPackage.
        """
        context = VerificationContext(
            mission_id=dispatch.mission_id,
            task_id=dispatch.task_id,
            workspace=dispatch.workspace,
            allowed_files=dispatch.allowed_files,
            verification_requirements=dispatch.verification_requirements,
            completion_claim=completion_claim or {},
            baseline_test_results=baseline_test_results,
            timeout=dispatch.timeout or 60.0,
        )
        return await self.verify(context)
