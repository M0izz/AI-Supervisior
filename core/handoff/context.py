from datetime import datetime, timezone
import logging
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

from core.handoff.models import (
    ContextFact,
    FactProvenance,
    HandoffContextPackage,
    HandoffTrigger,
)

logger = logging.getLogger("supervisor.handoff.context")


class HandoffContextBuilder:
    """
    Constructs structured, provenance-preserving HandoffContextPackages.
    Extracts relevant evidence from Git worktrees, watchdog anomalies,
    and verification results while keeping context bounded and verifiable.
    """

    @staticmethod
    def build(
        mission_id: str,
        task_id: str,
        objective: str,
        workspace: str,
        source_agent_id: str,
        target_agent_id: str,
        trigger: HandoffTrigger,
        reason: str = "",
        task_description: str = "",
        allowed_scope: Optional[List[str]] = None,
        failure_signature: Optional[str] = None,
        consecutive_failures: int = 0,
        watchdog_evidence: Optional[Dict[str, Any]] = None,
        verification_evidence: Optional[Dict[str, Any]] = None,
        source_claim: Optional[Dict[str, Any]] = None,
        executed_commands: Optional[List[str]] = None,
        handoff_history: Optional[List[Dict[str, Any]]] = None,
        handoff_count: int = 1,
    ) -> HandoffContextPackage:
        verified_facts: List[ContextFact] = []
        unverified_claims: List[ContextFact] = []
        rejected_attempts: List[ContextFact] = []

        # 1. Inspect Git worktree for changed files
        ws_path = Path(workspace)
        changed_files: List[str] = []
        if ws_path.exists():
            verified_facts.append(
                ContextFact(
                    statement=f"Task worktree is isolated and located at '{workspace}'.",
                    provenance=FactProvenance.VERIFIED,
                    source="git_worktree_manager",
                )
            )
            try:
                st = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(ws_path),
                    capture_output=True,
                    text=True,
                    shell=False,
                    timeout=5,
                )
                if st.returncode == 0 and st.stdout.strip():
                    for line in st.stdout.strip().splitlines():
                        if len(line) > 3:
                            path_part = line[3:].strip().strip('"')
                            if " -> " in path_part:
                                path_part = path_part.split(" -> ")[1].strip()
                            changed_files.append(path_part)
                    if changed_files:
                        verified_facts.append(
                            ContextFact(
                                statement=f"Changed files in worktree: {', '.join(changed_files)}",
                                provenance=FactProvenance.VERIFIED,
                                source="git_status",
                                metadata={"changed_files": changed_files},
                            )
                        )
            except Exception as e:
                logger.debug(f"Git inspection in context builder had non-fatal error: {e}")

        # 2. Process Watchdog Evidence
        w_ev = watchdog_evidence or {}
        if failure_signature:
            rejected_attempts.append(
                ContextFact(
                    statement=f"Source agent failed {consecutive_failures} consecutive times with error signature: '{failure_signature}'.",
                    provenance=FactProvenance.REJECTED,
                    source=f"watchdog:{w_ev.get('rule_id', 'LOOP_DETECTED')}",
                    metadata=w_ev,
                )
            )

        # 3. Process Verification Evidence
        v_ev = verification_evidence or {}
        if v_ev:
            failed_checks = v_ev.get("failed_checks", [])
            if failed_checks:
                rejected_attempts.append(
                    ContextFact(
                        statement=f"Independent verifier rejected source agent work. Failed checks: {failed_checks}.",
                        provenance=FactProvenance.REJECTED,
                        source="verification_engine",
                        metadata=v_ev,
                    )
                )
            test_results = v_ev.get("check_tests", {}).get("evidence", {}).get("results", [])
            for tr in test_results:
                if tr.get("exit_code") != 0:
                    rejected_attempts.append(
                        ContextFact(
                            statement=f"Command '{tr.get('command')}' failed with exit code {tr.get('exit_code')}.",
                            provenance=FactProvenance.REJECTED,
                            source="verification_engine",
                            metadata=tr,
                        )
                    )

        # 4. Process Source Agent Claims
        if source_claim:
            claimed_summary = (
                source_claim.get("summary")
                or source_claim.get("result")
                or source_claim.get("claim")
            )
            if claimed_summary:
                unverified_claims.append(
                    ContextFact(
                        statement=f"Source agent claimed: '{claimed_summary}'.",
                        provenance=FactProvenance.UNVERIFIED,
                        source=f"agent:{source_agent_id}",
                        metadata=source_claim,
                    )
                )

        # 5. Formulate Remaining Work
        remaining = (
            f"Fix failing assertions and complete objective '{objective}'. "
            f"Do NOT repeat previously failed approaches: '{failure_signature or reason}'. "
            f"Keep all modifications strictly within allowed scope: {allowed_scope or ['*']}."
        )

        return HandoffContextPackage(
            task_id=task_id,
            mission_id=mission_id,
            objective=objective,
            task_description=task_description,
            allowed_scope=allowed_scope or [],
            workspace=workspace,
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            trigger=trigger,
            failure_reason=reason or "Task handed off by supervisor due to execution stall or verification failure.",
            failure_signature=failure_signature,
            consecutive_failures=consecutive_failures,
            verified_facts=verified_facts,
            unverified_claims=unverified_claims,
            rejected_attempts=rejected_attempts,
            changed_files=changed_files,
            executed_commands=executed_commands or [],
            watchdog_evidence=w_ev,
            verification_evidence=v_ev,
            remaining_work=remaining,
            handoff_history=handoff_history or [],
            handoff_count=handoff_count,
        )
