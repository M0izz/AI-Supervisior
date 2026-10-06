"""
AI Supervisor — Deterministic Domain Conflict Resolution Engine
Enforces domain-specific deterministic conflict rules across multi-device synchronizations:
- Epistemic hierarchy for Project Memory (VERIFIED/REJECTED facts cannot be downgraded)
- Non-regressive Task lifecycle (COMPLETED/VERIFIED tasks cannot revert to PENDING/RUNNING)
- Monotonic Verification outcomes (terminal PASSED/FAILED outcomes cannot revert to PENDING)
- Terminal Approval permanence (APPROVED/DENIED cannot revert to PENDING)
- Tombstone precedence (deletions absorb equal or lower revision writes)
- Local safety invariant (Local Supervisor policy and safety always win)
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union
from sync.protocol import ConflictType, SyncConflict, SyncRecord, SyncRecordType

# Epistemic hierarchy ranking
EPISTEMIC_RANKS = {
    "UNVERIFIED": 1,
    "INFERRED": 2,
    "OBSERVED": 3,
    "DECIDED": 4,
    "REJECTED": 5,
    "VERIFIED": 6,
}

# Task lifecycle progression ranking
TASK_STATUS_RANKS = {
    "PENDING": 1,
    "IN_PROGRESS": 2,
    "BLOCKED": 2,
    "SKIPPED": 3,
    "FAILED": 3,
    "COMPLETED": 4,
    "VERIFIED": 5,
}

# Verification status ranking
VERIFICATION_STATUS_RANKS = {
    "PENDING": 1,
    "FAILED": 2,
    "PASSED": 3,
}

# Approval status ranking
APPROVAL_STATUS_RANKS = {
    "PENDING": 1,
    "CANCELLED": 2,
    "DENIED": 2,
    "APPROVED": 2,
}


@dataclass
class ResolutionResult:
    """Outcome of a conflict evaluation."""
    should_apply: bool
    conflict: Optional[SyncConflict]
    resolved_payload: Dict[str, Any]
    winning_record: Optional[Any] = None

    def __post_init__(self):
        if self.winning_record is None:
            # Create a synthetic representation if not explicitly set
            self.winning_record = SyncRecord(
                record_id="resolved",
                record_type="resolved",
                project_id="resolved",
                payload=self.resolved_payload,
            )


class ConflictResolver:
    """
    Deterministic conflict resolver enforcing semantic consistency across distributed replicas.
    """

    @classmethod
    def resolve(
        cls,
        local_record: Union[SyncRecord, Dict[str, Any], None],
        incoming_record: SyncRecord,
    ) -> ResolutionResult:
        """
        Evaluates whether an incoming record should be applied locally or rejected/merged.
        If local_record is None, incoming record is brand new and accepted.
        """
        if local_record is None:
            return ResolutionResult(
                should_apply=True,
                conflict=None,
                resolved_payload=incoming_record.payload,
                winning_record=incoming_record,
            )

        # Normalize local record
        local_obj: Optional[SyncRecord] = None
        if isinstance(local_record, SyncRecord):
            local_obj = local_record
            local_dict = local_record.model_dump()
        else:
            local_dict = local_record
            try:
                local_obj = SyncRecord.from_dict(local_record)
            except Exception:
                local_obj = None

        local_rev = local_dict.get("revision", 1)
        incoming_rev = incoming_record.revision
        incoming_type_str = incoming_record.record_type.value if hasattr(incoming_record.record_type, "value") else str(incoming_record.record_type)
        record_type = incoming_type_str.lower()

        # 1. Tombstone (Deletion) Precedence
        local_is_deleted = bool(local_dict.get("deleted_at")) or (str(local_dict.get("record_type", "")).lower() == "tombstone")
        incoming_is_deleted = bool(incoming_record.deleted_at) or (record_type == "tombstone")

        if incoming_is_deleted and not local_is_deleted:
            if incoming_rev >= local_rev:
                conflict = SyncConflict(
                    record_id=incoming_record.record_id,
                    record_type=incoming_type_str,
                    project_id=incoming_record.project_id,
                    conflict_type=ConflictType.TOMBSTONE_PRECEDENCE.value,
                    resolution="remote_won",
                    applied_record=incoming_record.payload,
                    rejected_record=local_dict.get("payload", {}),
                    reason="Incoming tombstone absorbed local active entity",
                )
                return ResolutionResult(
                    should_apply=True,
                    conflict=conflict,
                    resolved_payload=incoming_record.payload,
                    winning_record=incoming_record,
                )
            else:
                conflict = SyncConflict(
                    record_id=incoming_record.record_id,
                    record_type=incoming_type_str,
                    project_id=incoming_record.project_id,
                    conflict_type=ConflictType.STALE_REVISION.value,
                    resolution="local_won",
                    applied_record=local_dict.get("payload", {}),
                    rejected_record=incoming_record.payload,
                    reason="Stale incoming tombstone rejected by newer local revision",
                )
                return ResolutionResult(
                    should_apply=False,
                    conflict=conflict,
                    resolved_payload=local_dict.get("payload", {}),
                    winning_record=local_obj,
                )

        if local_is_deleted and not incoming_is_deleted:
            if local_rev >= incoming_rev:
                conflict = SyncConflict(
                    record_id=incoming_record.record_id,
                    record_type=incoming_type_str,
                    project_id=incoming_record.project_id,
                    conflict_type=ConflictType.TOMBSTONE_PRECEDENCE.value,
                    resolution="local_won",
                    applied_record=local_dict.get("payload", {}),
                    rejected_record=incoming_record.payload,
                    reason="Local tombstone absorbed incoming live write",
                )
                return ResolutionResult(
                    should_apply=False,
                    conflict=conflict,
                    resolved_payload=local_dict.get("payload", {}),
                    winning_record=local_obj or SyncRecord(
                        record_id=incoming_record.record_id,
                        record_type=SyncRecordType.TOMBSTONE,
                        project_id=incoming_record.project_id,
                        payload=local_dict.get("payload", {}),
                    ),
                )

        # 2. Domain-Specific Invariant Checks
        local_payload = local_dict.get("payload", {})
        incoming_payload = incoming_record.payload

        # A. Memory Hierarchy: Prevent epistemic downgrades
        if record_type in ("memory", "memory_record"):
            local_status = str(local_payload.get("epistemic_status") or local_payload.get("status", "UNVERIFIED")).upper()
            incoming_status = str(incoming_payload.get("epistemic_status") or incoming_payload.get("status", "UNVERIFIED")).upper()
            local_rank = EPISTEMIC_RANKS.get(local_status, 1)
            incoming_rank = EPISTEMIC_RANKS.get(incoming_status, 1)

            if local_rank > incoming_rank:
                # Prevent downgrade of higher epistemic status
                conflict = SyncConflict(
                    record_id=incoming_record.record_id,
                    record_type=incoming_type_str,
                    project_id=incoming_record.project_id,
                    conflict_type=ConflictType.EPISTEMIC_DOWNGRADE_BLOCKED.value,
                    resolution="local_won",
                    applied_record=local_payload,
                    rejected_record=incoming_payload,
                    reason=f"Epistemic downgrade blocked: local {local_status} (rank {local_rank}) > incoming {incoming_status} (rank {incoming_rank})",
                )
                return ResolutionResult(
                    should_apply=False,
                    conflict=conflict,
                    resolved_payload=local_payload,
                    winning_record=local_obj or incoming_record.model_copy(update={"payload": local_payload}),
                )
            elif incoming_rank > local_rank:
                # Epistemic promotion wins over lower local status
                conflict = SyncConflict(
                    record_id=incoming_record.record_id,
                    record_type=incoming_type_str,
                    project_id=incoming_record.project_id,
                    conflict_type=ConflictType.EPISTEMIC_DOWNGRADE_BLOCKED.value,
                    resolution="remote_won",
                    applied_record=incoming_payload,
                    rejected_record=local_payload,
                    reason=f"Epistemic promotion: incoming {incoming_status} (rank {incoming_rank}) > local {local_status} (rank {local_rank})",
                )
                return ResolutionResult(
                    should_apply=True,
                    conflict=conflict,
                    resolved_payload=incoming_payload,
                    winning_record=incoming_record,
                )

        # B. Task Lifecycle: Prevent task regression
        elif record_type in ("task", "tasks"):
            local_status = str(local_payload.get("status", "PENDING")).upper()
            incoming_status = str(incoming_payload.get("status", "PENDING")).upper()
            local_rank = TASK_STATUS_RANKS.get(local_status, 1)
            incoming_rank = TASK_STATUS_RANKS.get(incoming_status, 1)

            if local_rank > incoming_rank and local_status in ("COMPLETED", "VERIFIED"):
                conflict = SyncConflict(
                    record_id=incoming_record.record_id,
                    record_type=incoming_type_str,
                    project_id=incoming_record.project_id,
                    conflict_type=ConflictType.TASK_REGRESSION_BLOCKED.value,
                    resolution="local_won",
                    applied_record=local_payload,
                    rejected_record=incoming_payload,
                    reason=f"Task regression blocked: {local_status} cannot revert to {incoming_status}",
                )
                return ResolutionResult(
                    should_apply=False,
                    conflict=conflict,
                    resolved_payload=local_payload,
                    winning_record=local_obj or incoming_record.model_copy(update={"payload": local_payload}),
                )

        # C. Verification Monotonicity: Prevent verification reset
        elif record_type in ("verification", "verifications"):
            local_status = str(local_payload.get("outcome") or local_payload.get("status", "PENDING")).upper()
            incoming_status = str(incoming_payload.get("outcome") or incoming_payload.get("status", "PENDING")).upper()
            local_rank = VERIFICATION_STATUS_RANKS.get(local_status, 1)
            incoming_rank = VERIFICATION_STATUS_RANKS.get(incoming_status, 1)

            if local_rank > incoming_rank and local_status in ("PASSED", "FAILED"):
                conflict = SyncConflict(
                    record_id=incoming_record.record_id,
                    record_type=incoming_type_str,
                    project_id=incoming_record.project_id,
                    conflict_type=ConflictType.VERIFICATION_REGRESSION_BLOCKED.value,
                    resolution="local_won",
                    applied_record=local_payload,
                    rejected_record=incoming_payload,
                    reason=f"Verification regression blocked: {local_status} outcome cannot revert to {incoming_status}",
                )
                return ResolutionResult(
                    should_apply=False,
                    conflict=conflict,
                    resolved_payload=local_payload,
                    winning_record=local_obj or incoming_record.model_copy(update={"payload": local_payload}),
                )

        # D. Approvals: Prevent approval reset
        elif record_type in ("approval", "approvals"):
            local_status = str(local_payload.get("status", "PENDING")).upper()
            incoming_status = str(incoming_payload.get("status", "PENDING")).upper()
            local_rank = APPROVAL_STATUS_RANKS.get(local_status, 1)
            incoming_rank = APPROVAL_STATUS_RANKS.get(incoming_status, 1)

            if local_rank > incoming_rank and local_status in ("APPROVED", "DENIED"):
                conflict = SyncConflict(
                    record_id=incoming_record.record_id,
                    record_type=incoming_type_str,
                    project_id=incoming_record.project_id,
                    conflict_type=ConflictType.APPROVAL_REGRESSION_BLOCKED.value,
                    resolution="local_won",
                    applied_record=local_payload,
                    rejected_record=incoming_payload,
                    reason=f"Approval regression blocked: resolved status {local_status} cannot revert to {incoming_status}",
                )
                return ResolutionResult(
                    should_apply=False,
                    conflict=conflict,
                    resolved_payload=local_payload,
                    winning_record=local_obj or incoming_record.model_copy(update={"payload": local_payload}),
                )

        # 3. Revision Comparison & Last-Write-Wins
        if incoming_rev > local_rev:
            return ResolutionResult(
                should_apply=True,
                conflict=None,
                resolved_payload=incoming_payload,
                winning_record=incoming_record,
            )
        elif incoming_rev < local_rev:
            conflict = SyncConflict(
                record_id=incoming_record.record_id,
                record_type=incoming_type_str,
                project_id=incoming_record.project_id,
                conflict_type=ConflictType.STALE_REVISION.value,
                resolution="local_won",
                applied_record=local_payload,
                rejected_record=incoming_payload,
                reason=f"Stale revision: incoming rev {incoming_rev} < local rev {local_rev}",
            )
            return ResolutionResult(
                should_apply=False,
                conflict=conflict,
                resolved_payload=local_payload,
                winning_record=local_obj or incoming_record.model_copy(update={"payload": local_payload}),
            )
        else:
            # Revisions equal: Break tie by timestamp
            local_updated = local_dict.get("updated_at", "")
            incoming_updated = incoming_record.updated_at
            if incoming_updated > local_updated:
                return ResolutionResult(
                    should_apply=True,
                    conflict=None,
                    resolved_payload=incoming_payload,
                    winning_record=incoming_record,
                )
            else:
                return ResolutionResult(
                    should_apply=False,
                    conflict=None,
                    resolved_payload=local_payload,
                    winning_record=local_obj or incoming_record.model_copy(update={"payload": local_payload}),
                )
