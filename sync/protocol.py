"""
AI Supervisor — Synchronization Protocol v1
Defines versioned models for local-first multi-device synchronization,
device registration, push/pull envelopes, conflict representations, and sync status.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

PROTOCOL_VERSION = "sync_protocol.v1"


class DeviceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class Device(BaseModel):
    """Represents a synchronized client device identity."""
    device_id: str
    display_name: str = ""
    device_name: Optional[str] = None
    device_token_hash: Optional[str] = None
    platform: str = "unknown"
    app_version: str = "1.0.0"
    protocol_version: str = PROTOCOL_VERSION
    status: DeviceStatus = DeviceStatus.ACTIVE
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_seen_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __init__(self, **data):
        super().__init__(**data)
        if not self.display_name and self.device_name:
            self.display_name = self.device_name
        elif not self.device_name and self.display_name:
            self.device_name = self.display_name


class SyncRecordType(str, Enum):
    MISSION = "mission"
    TASK = "task"
    MEMORY = "memory"
    VERIFICATION = "verification"
    HANDOFF = "handoff"
    ROUTING = "routing"
    APPROVAL = "approval"
    ABSENCE = "absence"
    WATCHDOG = "watchdog"
    TOMBSTONE = "tombstone"


class SyncRecord(BaseModel):
    """
    Standard synchronized domain record.
    Strictly sanitizes all secrets, credentials, and host-local filesystem paths.
    """
    record_id: str
    record_type: Union[SyncRecordType, str]
    project_id: str
    device_id: str = "default_device"
    entity_id: Optional[str] = None
    origin_device_id: Optional[str] = None
    revision: int = 1
    protocol_version: str = "1.0"
    schema_version: str = "1.0.0"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deleted_at: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data):
        super().__init__(**data)
        if not self.origin_device_id and self.device_id:
            self.origin_device_id = self.device_id
        if self.origin_device_id and self.device_id == "default_device":
            self.device_id = self.origin_device_id

    def to_dict(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["record_type"] = self.record_type.value if isinstance(self.record_type, Enum) else str(self.record_type)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncRecord":
        return cls(**data)


class ConflictType(str, Enum):
    STALE_REVISION = "STALE_REVISION"
    EPISTEMIC_DOWNGRADE_BLOCKED = "EPISTEMIC_DOWNGRADE_BLOCKED"
    TASK_REGRESSION_BLOCKED = "TASK_REGRESSION_BLOCKED"
    VERIFICATION_REGRESSION_BLOCKED = "VERIFICATION_REGRESSION_BLOCKED"
    APPROVAL_REGRESSION_BLOCKED = "APPROVAL_REGRESSION_BLOCKED"
    TOMBSTONE_PRECEDENCE = "TOMBSTONE_PRECEDENCE"
    LOCAL_SAFETY_OVERRIDE = "LOCAL_SAFETY_OVERRIDE"


class SyncConflict(BaseModel):
    """Represents an auditable conflict resolution decision."""
    record_id: str
    record_type: str
    project_id: str
    conflict_type: str
    resolution: str  # "APPLIED_INCOMING", "KEPT_LOCAL", "MERGED"
    applied_record: Dict[str, Any]
    rejected_record: Optional[Dict[str, Any]] = None
    reason: str = ""


class PushRequest(BaseModel):
    """Client push request containing queued outbound mutations."""
    device_id: str
    client_id: str = ""
    device_token: str = ""
    project_id: str = ""
    protocol_version: str = PROTOCOL_VERSION
    records: List[SyncRecord]
    cursor: Optional[int] = None


class PushResponse(BaseModel):
    """Server response acknowledging received push records."""
    success: bool = True
    processed_count: int = 0
    accepted_count: int = 0
    duplicate_count: int = 0
    server_cursor: int = 0
    new_cursor: int = 0
    conflicts: List[SyncConflict] = Field(default_factory=list)


class PullRequest(BaseModel):
    """Client pull request requesting changes beyond current cursor."""
    device_id: str
    device_token: str = ""
    project_id: str
    cursor: int = 0
    since_cursor: int = 0
    limit: int = 100

    def __init__(self, **data):
        super().__init__(**data)
        if self.since_cursor and not self.cursor:
            self.cursor = self.since_cursor
        elif self.cursor and not self.since_cursor:
            self.since_cursor = self.cursor


class PullResponse(BaseModel):
    """Server response containing incremental synchronized changes."""
    records: List[SyncRecord]
    next_cursor: int
    has_more: bool = False


class SyncState(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    SYNCING = "SYNCING"
    SYNCED = "SYNCED"
    ERROR = "ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"


class SyncStatus(BaseModel):
    """Local synchronization engine status report."""
    state: SyncState
    device_id: str
    project_id: str
    pending_outbox_count: int = 0
    outbox_pending_count: int = 0
    last_synced_at: Optional[str] = None
    last_pull_cursor: int = 0
    connected_devices_count: int = 1
    error_message: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.pending_outbox_count and not self.outbox_pending_count:
            self.outbox_pending_count = self.pending_outbox_count
        elif self.outbox_pending_count and not self.pending_outbox_count:
            self.pending_outbox_count = self.outbox_pending_count

    def __await__(self):
        async def _identity():
            return self
        return _identity().__await__()


class SyncRoundResult(BaseModel):
    """Result of a sync_now() or sync_once() execution."""
    success: bool
    pushed_count: int = 0
    pulled_count: int = 0
    state: SyncState = SyncState.ONLINE
    error_message: Optional[str] = None
