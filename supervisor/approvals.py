import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import uuid

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.state.models import ApprovalRequest, ApprovalStatus

logger = logging.getLogger("supervisor.approvals")


class ApprovalResolutionAction(str, Enum):
    APPROVE_ONCE = "APPROVE_ONCE"
    APPROVE_FOR_MISSION = "APPROVE_FOR_MISSION"
    DENY = "DENY"
    TAKE_CONTROL = "TAKE_CONTROL"


class ResolveApprovalPayload(BaseModel):
    action: ApprovalResolutionAction
    operator: str = "human_operator"
    feedback: Optional[str] = None


class ApprovalManager:
    """
    Manages human-in-the-loop approval workflows for dangerous commands,
    high-risk file modifications, or when the supervisor explicitly requests human control.
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._requests: Dict[str, ApprovalRequest] = {}
        self._whitelisted_mission_actions: Dict[str, List[str]] = {}  # mission_id -> list of approved action targets
        self._lock = asyncio.Lock()

        if self._event_bus:
            self._event_bus.subscribe_sync(self.handle_event)

    async def create_request(
        self,
        mission_id: str,
        agent_id: str,
        action_type: str,
        target: str,
        reason: str,
        risk_level: str = "high",
        task_id: Optional[str] = None
    ) -> ApprovalRequest:
        async with self._lock:
            # Check if already approved for entire mission
            whitelisted = self._whitelisted_mission_actions.get(mission_id, [])
            if target in whitelisted or action_type in whitelisted:
                req = ApprovalRequest(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    action_type=action_type,
                    target=target,
                    reason=f"{reason} (pre-approved for mission)",
                    risk_level=risk_level,
                    status=ApprovalStatus.APPROVED,
                    resolved_at=datetime.now(timezone.utc),
                    resolved_by="mission_policy"
                )
                self._requests[req.id] = req
                return req

            req = ApprovalRequest(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                action_type=action_type,
                target=target,
                reason=reason,
                risk_level=risk_level,
                status=ApprovalStatus.PENDING
            )
            self._requests[req.id] = req

        if self._event_bus:
            await self._event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    type=EventType.APPROVAL_REQUESTED,
                    severity=EventSeverity.CRITICAL if risk_level in ("high", "critical") else EventSeverity.WARNING,
                    payload={
                        "approval_id": req.id,
                        "action_type": action_type,
                        "target": target,
                        "reason": reason,
                        "risk_level": risk_level
                    }
                )
            )
        logger.warning(f"[APPROVAL] Requested: {req.id} ({action_type} on {target}) by {agent_id}")
        return req

    async def get_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        async with self._lock:
            return self._requests.get(approval_id)

    async def list_requests(
        self,
        mission_id: Optional[str] = None,
        status: Optional[ApprovalStatus] = None
    ) -> List[ApprovalRequest]:
        async with self._lock:
            reqs = list(self._requests.values())
            if mission_id:
                reqs = [r for r in reqs if r.mission_id == mission_id]
            if status:
                reqs = [r for r in reqs if r.status == status]
            return reqs

    async def resolve_request(
        self,
        approval_id: str,
        resolution: ResolveApprovalPayload
    ) -> Optional[ApprovalRequest]:
        async with self._lock:
            req = self._requests.get(approval_id)
            if not req:
                return None

            req.resolved_at = datetime.now(timezone.utc)
            req.resolved_by = resolution.operator
            req.feedback = resolution.feedback

            if resolution.action == ApprovalResolutionAction.DENY:
                req.status = ApprovalStatus.DENIED
            elif resolution.action in (ApprovalResolutionAction.APPROVE_ONCE, ApprovalResolutionAction.APPROVE_FOR_MISSION):
                req.status = ApprovalStatus.APPROVED
                if resolution.action == ApprovalResolutionAction.APPROVE_FOR_MISSION:
                    if req.mission_id not in self._whitelisted_mission_actions:
                        self._whitelisted_mission_actions[req.mission_id] = []
                    self._whitelisted_mission_actions[req.mission_id].append(req.target)
            elif resolution.action == ApprovalResolutionAction.TAKE_CONTROL:
                req.status = ApprovalStatus.DENIED

        logger.info(f"[APPROVAL] Resolved {approval_id}: {resolution.action.value} by {resolution.operator}")

        if self._event_bus:
            # Emit resolution event
            await self._event_bus.publish(
                Event(
                    mission_id=req.mission_id,
                    task_id=req.task_id,
                    agent_id="supervisor",
                    type=EventType.APPROVAL_RESOLVED,
                    severity=EventSeverity.INFO if req.status == ApprovalStatus.APPROVED else EventSeverity.WARNING,
                    payload={
                        "approval_id": req.id,
                        "action": resolution.action.value,
                        "status": req.status.value,
                        "operator": resolution.operator,
                        "feedback": resolution.feedback,
                        "target": req.target
                    }
                )
            )

            # If human took control
            if resolution.action == ApprovalResolutionAction.TAKE_CONTROL:
                await self._event_bus.publish(
                    Event(
                        mission_id=req.mission_id,
                        task_id=req.task_id,
                        agent_id=resolution.operator,
                        type=EventType.OPERATOR_TAKE_CONTROL,
                        severity=EventSeverity.WARNING,
                        payload={
                            "operator": resolution.operator,
                            "reason": resolution.feedback or "Operator initiated manual control override"
                        }
                    )
                )

        return req

    async def handle_event(self, event: Event) -> None:
        """Handle raw approval requested events if generated externally."""
        if event.type == EventType.APPROVAL_REQUESTED and "approval_id" not in event.payload:
            # Auto-register external approval request
            await self.create_request(
                mission_id=event.mission_id or "default",
                agent_id=event.agent_id or "worker",
                action_type=event.payload.get("action_type", "unknown"),
                target=event.payload.get("target", "workspace"),
                reason=event.payload.get("reason", "Action flagged for approval"),
                risk_level=event.payload.get("risk_level", "high"),
                task_id=event.task_id
            )
