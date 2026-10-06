"""
AI Supervisor — Reference Cloud Sync Service & Server Store
Provides the cloud-side synchronization service managing device authentication,
idempotent record ingestion, global sequence cursors, project isolation, and tombstones.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sync.conflicts import ConflictResolver
from sync.identity import hash_device_token
from sync.protocol import (
    Device,
    DeviceStatus,
    PullRequest,
    PullResponse,
    PushRequest,
    PushResponse,
    SyncConflict,
    SyncRecord,
)
from sync.sanitizer import sanitize_payload

logger = logging.getLogger("supervisor.sync.server")


class SyncAuthError(Exception):
    """Raised when device credentials are missing or invalid."""
    pass


DeviceAuthenticationError = SyncAuthError


class DeviceRevokedError(Exception):
    """Raised when an action is attempted by a revoked device."""
    pass


class SyncServerStore:
    """
    In-memory or persistent store for the Cloud Sync Service.
    Maintains registered devices, token hashes, a monotonically increasing
    global sequence cursor, and project-scoped sync records.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        # device_id -> {"device": Device, "token_hash": str}
        self._devices: Dict[str, Dict[str, Any]] = {}
        # Global sequence counter
        self._sequence_counter: int = 0
        # sequence_num -> (project_id, SyncRecord)
        self._record_log: List[Tuple[int, str, SyncRecord]] = []
        # (project_id, record_id) -> (sequence_num, SyncRecord)
        self._latest_records: Dict[Tuple[str, str], Tuple[int, SyncRecord]] = {}
        # (record_id, revision) -> sequence_num for idempotency
        self._idempotency_index: Dict[Tuple[str, int], int] = {}

    async def register_device(
        self,
        device_or_name: Any,
        token_or_platform: str = "unknown",
        app_version: str = "1.0.0",
    ) -> Any:
        async with self._lock:
            if isinstance(device_or_name, Device):
                device = device_or_name
                token = token_or_platform
                token_hash = hash_device_token(token)
                self._devices[device.device_id] = {
                    "device": device,
                    "token_hash": token_hash,
                }
                logger.info(f"Registered sync device {device.device_id} ({device.display_name})")
                return device
            else:
                from sync.identity import generate_device_credentials
                display_name = str(device_or_name)
                platform = str(token_or_platform)
                device_id, token = generate_device_credentials()
                token_hash = hash_device_token(token)
                now = datetime.now(timezone.utc).isoformat()
                device = Device(
                    device_id=device_id,
                    display_name=display_name,
                    platform=platform,
                    app_version=app_version,
                    status=DeviceStatus.ACTIVE,
                    created_at=now,
                    last_seen_at=now,
                )
                self._devices[device.device_id] = {
                    "device": device,
                    "token_hash": token_hash,
                }
                logger.info(f"Generated & registered sync device {device_id} ({display_name})")
                return (device_id, token)

    async def revoke_device(self, device_id: str) -> Optional[Device]:
        async with self._lock:
            if device_id in self._devices:
                dev = self._devices[device_id]["device"]
                dev.status = DeviceStatus.REVOKED
                logger.warning(f"Revoked sync device {device_id}")
                return dev
            return None

    async def get_device(self, device_id: str) -> Optional[Device]:
        async with self._lock:
            entry = self._devices.get(device_id)
            return entry["device"] if entry else None

    async def list_devices(self) -> List[Device]:
        async with self._lock:
            return [e["device"] for e in self._devices.values()]

    async def authenticate_device(self, device_id: str, token: str) -> Device:
        """Validates device identity and token. Raises SyncAuthError or DeviceRevokedError."""
        async with self._lock:
            entry = self._devices.get(device_id)
            if not entry:
                raise SyncAuthError(f"Unknown device ID '{device_id}'")

            expected_hash = entry["token_hash"]
            provided_hash = hash_device_token(token)
            if expected_hash != provided_hash:
                raise SyncAuthError("Invalid device token credentials")

            device = entry["device"]
            if device.status == DeviceStatus.REVOKED:
                raise DeviceRevokedError(f"Device '{device_id}' has been REVOKED and is forbidden from syncing.")

            device.last_seen_at = datetime.now(timezone.utc).isoformat()
            return device

    async def push(self, request: PushRequest, token: Optional[str] = None) -> PushResponse:
        """
        Idempotently processes inbound records from a client.
        Enforces device authentication, sanitization, deduplication,
        and project-scoped sequence logging.
        """
        auth_token = token or request.device_token
        await self.authenticate_device(request.device_id, auth_token)

        conflicts: List[SyncConflict] = []
        processed_count = 0
        accepted_count = 0
        duplicate_count = 0

        async with self._lock:
            for raw_record in request.records:
                # 1. Sanitize payload strictly
                sanitized_payload = sanitize_payload(raw_record.payload)
                record = raw_record.model_copy(update={"payload": sanitized_payload})
                if not record.project_id and request.project_id:
                    record.project_id = request.project_id

                key = (record.project_id, record.record_id)
                idempotency_key = (record.record_id, record.revision)

                # 2. Idempotency Check
                # If exact record_id and revision already processed, treat as successful no-op
                if idempotency_key in self._idempotency_index:
                    processed_count += 1
                    duplicate_count += 1
                    continue

                # 3. Conflict Resolution against latest server state
                existing_entry = self._latest_records.get(key)
                local_payload = existing_entry[1].model_dump() if existing_entry else None

                resolution = ConflictResolver.resolve(local_payload, record)

                if resolution.conflict:
                    conflicts.append(resolution.conflict)

                if resolution.should_apply:
                    self._sequence_counter += 1
                    seq = self._sequence_counter
                    applied_record = record.model_copy(update={"payload": resolution.resolved_payload})
                    self._record_log.append((seq, record.project_id, applied_record))
                    self._latest_records[key] = (seq, applied_record)
                    self._idempotency_index[idempotency_key] = seq
                    processed_count += 1
                    accepted_count += 1
                else:
                    # Conflict kept existing record; mark idempotency to avoid retry churn
                    if existing_entry:
                        self._idempotency_index[idempotency_key] = existing_entry[0]
                    processed_count += 1

            return PushResponse(
                success=True,
                processed_count=processed_count,
                accepted_count=accepted_count,
                duplicate_count=duplicate_count,
                server_cursor=self._sequence_counter,
                new_cursor=self._sequence_counter,
                conflicts=conflicts,
            )

    async def pull(self, request: PullRequest, token: Optional[str] = None) -> PullResponse:
        """
        Pulls incremental updates for a specific project beyond the client's cursor.
        Strictly enforces project isolation: records from other projects are NEVER returned.
        """
        auth_token = token or request.device_token
        await self.authenticate_device(request.device_id, auth_token)

        cursor = request.cursor if request.cursor else request.since_cursor

        async with self._lock:
            results: List[SyncRecord] = []
            next_cursor = cursor
            has_more = False

            # Scan log for records matching project_id with sequence > cursor
            matching_entries = [
                (seq, proj, rec)
                for seq, proj, rec in self._record_log
                if proj == request.project_id and seq > cursor
            ]

            limit = max(1, min(request.limit, 500))
            page = matching_entries[:limit]

            for seq, proj, rec in page:
                results.append(rec)
                next_cursor = max(next_cursor, seq)

            if len(matching_entries) > limit:
                has_more = True

            return PullResponse(
                records=results,
                next_cursor=next_cursor,
                has_more=has_more,
            )
