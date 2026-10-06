"""
AI Supervisor — SQLite Sync Repository
Provides local-first persistence for sync devices, outbox queue, inbox queue,
pagination cursors, tombstones, and conflict audit logs.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from storage.sqlite.db import DatabaseManager
from sync.protocol import (
    Device,
    DeviceStatus,
    SyncConflict,
    SyncRecord,
)

logger = logging.getLogger("supervisor.storage.sync")


def _to_json(val: Any) -> str:
    return json.dumps(val, default=str)


def _from_json(raw: Optional[str]) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


class SyncRepository:
    """Repository managing local-first SQLite persistence for Phase 12 synchronization."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    # --- 1. Device Management ---

    async def register_device(self, device: Device, token_hash: Optional[str] = None) -> Device:
        conn = await self.db.get_connection()
        try:
            th = token_hash or getattr(device, "device_token_hash", None) or ""
            query = """
            INSERT INTO sync_devices (
                device_id, display_name, platform, app_version, protocol_version,
                device_token_hash, status, created_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                display_name = excluded.display_name,
                app_version = excluded.app_version,
                last_seen_at = excluded.last_seen_at;
            """
            await conn.execute(
                query,
                (
                    device.device_id,
                    device.display_name,
                    device.platform,
                    device.app_version,
                    device.protocol_version,
                    th,
                    device.status.value,
                    device.created_at,
                    device.last_seen_at,
                ),
            )
            await conn.commit()
            return device
        finally:
            await conn.close()

    async def get_device(self, device_id: str) -> Optional[Device]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM sync_devices WHERE device_id = ?;",
                (device_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            r = dict(row)
            return Device(
                device_id=r["device_id"],
                display_name=r["display_name"],
                platform=r["platform"],
                app_version=r["app_version"],
                protocol_version=r["protocol_version"],
                status=DeviceStatus(r["status"]),
                created_at=r["created_at"],
                last_seen_at=r["last_seen_at"],
            )
        finally:
            await conn.close()

    async def get_device_token_hash(self, device_id: str) -> Optional[str]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT device_token_hash FROM sync_devices WHERE device_id = ?;",
                (device_id,),
            )
            row = await cursor.fetchone()
            return row["device_token_hash"] if row else None
        finally:
            await conn.close()

    async def list_devices(self) -> List[Device]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM sync_devices ORDER BY created_at ASC;"
            )
            rows = await cursor.fetchall()
            devices = []
            for row in rows:
                r = dict(row)
                devices.append(
                    Device(
                        device_id=r["device_id"],
                        display_name=r["display_name"],
                        platform=r["platform"],
                        app_version=r["app_version"],
                        protocol_version=r["protocol_version"],
                        status=DeviceStatus(r["status"]),
                        created_at=r["created_at"],
                        last_seen_at=r["last_seen_at"],
                    )
                )
            return devices
        finally:
            await conn.close()

    async def revoke_device(self, device_id: str) -> bool:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "UPDATE sync_devices SET status = ? WHERE device_id = ?;",
                (DeviceStatus.REVOKED.value, device_id),
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()

    async def touch_device(self, device_id: str) -> None:
        conn = await self.db.get_connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            await conn.execute(
                "UPDATE sync_devices SET last_seen_at = ? WHERE device_id = ?;",
                (now, device_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    # --- 2. Outbox Management ---

    async def enqueue_outbox(self, record: SyncRecord, idempotency_key: Optional[str] = None) -> str:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT outbox_id FROM sync_outbox WHERE record_id = ? AND revision = ?;",
                (record.record_id, record.revision),
            )
            existing = await cursor.fetchone()
            if existing:
                return existing["outbox_id"]

            outbox_id = f"out_{uuid.uuid4().hex[:12]}"
            rec_type_val = record.record_type.value if hasattr(record.record_type, "value") else str(record.record_type)
            query = """
            INSERT INTO sync_outbox (
                outbox_id, record_id, record_type, project_id, device_id,
                revision, schema_version, created_at, updated_at, deleted_at,
                payload, status, retry_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0);
            """
            await conn.execute(
                query,
                (
                    outbox_id,
                    record.record_id,
                    rec_type_val,
                    record.project_id,
                    record.device_id,
                    record.revision,
                    record.schema_version,
                    record.created_at,
                    record.updated_at,
                    record.deleted_at,
                    _to_json(record.payload),
                ),
            )
            await conn.commit()
            return outbox_id
        finally:
            await conn.close()

    async def get_pending_outbox(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                """
                SELECT * FROM sync_outbox
                WHERE status IN ('PENDING', 'FAILED', 'RETRY')
                ORDER BY created_at ASC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                r = dict(row)
                r["id"] = r["outbox_id"]
                r["payload"] = _from_json(r.get("payload"))
                r["attempts"] = r.get("retry_count", 0)
                if r.get("status") == "FAILED":
                    r["status"] = "RETRY"
                records.append(r)
            return records
        finally:
            await conn.close()

    async def mark_outbox_synced(self, outbox_ids: List[str]) -> None:
        if not outbox_ids:
            return
        conn = await self.db.get_connection()
        try:
            placeholders = ",".join("?" for _ in outbox_ids)
            await conn.execute(
                f"UPDATE sync_outbox SET status = 'SYNCED' WHERE outbox_id IN ({placeholders});",
                outbox_ids,
            )
            await conn.commit()
        finally:
            await conn.close()

    async def mark_outbox_sent(self, outbox_id: str) -> None:
        await self.mark_outbox_synced([outbox_id])

    async def mark_outbox_failed(self, outbox_id: str, error_message: str = "", retry_count: Optional[int] = None) -> None:
        conn = await self.db.get_connection()
        try:
            if retry_count is None:
                cursor = await conn.execute(
                    "SELECT retry_count FROM sync_outbox WHERE outbox_id = ?;",
                    (outbox_id,),
                )
                row = await cursor.fetchone()
                current_retries = int(row["retry_count"]) if row else 0
                retry_count = current_retries + 1

            await conn.execute(
                """
                UPDATE sync_outbox
                SET status = 'FAILED', error_message = ?, retry_count = ?
                WHERE outbox_id = ?;
                """,
                (error_message, retry_count, outbox_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get_outbox_pending_count(self) -> int:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT COUNT(*) as count FROM sync_outbox WHERE status IN ('PENDING', 'FAILED', 'RETRY');"
            )
            row = await cursor.fetchone()
            return row["count"] if row else 0
        finally:
            await conn.close()

    # --- 3. Inbox Management ---

    async def enqueue_inbox(self, record: SyncRecord) -> Optional[str]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT inbox_id FROM sync_inbox WHERE record_id = ? AND revision = ?;",
                (record.record_id, record.revision),
            )
            existing = await cursor.fetchone()
            if existing:
                return None

            inbox_id = f"in_{uuid.uuid4().hex[:12]}"
            rec_type_val = record.record_type.value if hasattr(record.record_type, "value") else str(record.record_type)
            query = """
            INSERT INTO sync_inbox (
                inbox_id, record_id, record_type, project_id, device_id,
                revision, schema_version, created_at, updated_at, deleted_at,
                payload, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING');
            """
            await conn.execute(
                query,
                (
                    inbox_id,
                    record.record_id,
                    rec_type_val,
                    record.project_id,
                    record.device_id,
                    record.revision,
                    record.schema_version,
                    record.created_at,
                    record.updated_at,
                    record.deleted_at,
                    _to_json(record.payload),
                ),
            )
            await conn.commit()
            return inbox_id
        finally:
            await conn.close()

    async def get_unprocessed_inbox(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                """
                SELECT * FROM sync_inbox
                WHERE status = 'PENDING'
                ORDER BY created_at ASC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            records = []
            for row in rows:
                r = dict(row)
                r["id"] = r["inbox_id"]
                r["entity_id"] = r.get("record_id")
                r["payload"] = _from_json(r.get("payload"))
                records.append(r)
            return records
        finally:
            await conn.close()

    async def mark_inbox_processed(self, inbox_id_or_dict: Any, status: str = "PROCESSED") -> None:
        inbox_id = inbox_id_or_dict.get("id") if isinstance(inbox_id_or_dict, dict) else str(inbox_id_or_dict)
        conn = await self.db.get_connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            await conn.execute(
                "UPDATE sync_inbox SET status = ?, processed_at = ? WHERE inbox_id = ?;",
                (status, now, inbox_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    # --- 4. Cursor Management ---

    async def get_cursor(self, cursor_key_or_project: str) -> int:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT last_cursor FROM sync_cursors WHERE cursor_key = ? OR project_id = ? ORDER BY last_cursor DESC LIMIT 1;",
                (cursor_key_or_project, cursor_key_or_project),
            )
            row = await cursor.fetchone()
            return int(row["last_cursor"]) if row else 0
        finally:
            await conn.close()

    async def set_cursor(self, cursor_key: str, project_id: str, device_id: str, last_cursor: int) -> None:
        conn = await self.db.get_connection()
        try:
            now = datetime.now(timezone.utc).isoformat()
            query = """
            INSERT INTO sync_cursors (cursor_key, project_id, device_id, last_cursor, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cursor_key) DO UPDATE SET
                last_cursor = excluded.last_cursor,
                updated_at = excluded.updated_at;
            """
            await conn.execute(query, (cursor_key, project_id, device_id, last_cursor, now))
            await conn.commit()
        finally:
            await conn.close()

    # --- 5. Tombstones ---

    async def record_tombstone(
        self,
        record_id: str,
        record_type: str,
        project_id: str,
        device_id: str,
        revision: int,
        deleted_at: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        conn = await self.db.get_connection()
        try:
            tombstone_id = f"tomb_{uuid.uuid4().hex[:12]}"
            query = """
            INSERT INTO sync_tombstones (
                tombstone_id, record_id, record_type, project_id, device_id,
                revision, deleted_at, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                revision = excluded.revision,
                deleted_at = excluded.deleted_at,
                payload = excluded.payload;
            """
            await conn.execute(
                query,
                (
                    tombstone_id,
                    record_id,
                    record_type,
                    project_id,
                    device_id,
                    revision,
                    deleted_at,
                    _to_json(payload or {}),
                ),
            )
            await conn.commit()
            return tombstone_id
        finally:
            await conn.close()

    async def get_tombstone(self, record_id: str) -> Optional[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            cursor = await conn.execute(
                "SELECT * FROM sync_tombstones WHERE record_id = ?;",
                (record_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            r = dict(row)
            r["payload"] = _from_json(r.get("payload"))
            return r
        finally:
            await conn.close()

    async def is_tombstoned(self, record_id: str) -> bool:
        return (await self.get_tombstone(record_id)) is not None

    # --- 6. Conflict Audit Log ---

    async def record_conflict(self, conflict: SyncConflict) -> str:
        conn = await self.db.get_connection()
        try:
            cid = f"cnf_{uuid.uuid4().hex[:12]}"
            now = datetime.now(timezone.utc).isoformat()
            query = """
            INSERT INTO sync_conflicts (
                conflict_id, record_id, record_type, project_id, conflict_type,
                resolution, applied_payload, rejected_payload, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            await conn.execute(
                query,
                (
                    cid,
                    conflict.record_id,
                    conflict.record_type,
                    conflict.project_id,
                    conflict.conflict_type,
                    conflict.resolution,
                    _to_json(conflict.applied_record),
                    _to_json(conflict.rejected_record or {}),
                    conflict.reason,
                    now,
                ),
            )
            await conn.commit()
            return cid
        finally:
            await conn.close()

    async def list_conflicts(self, project_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        conn = await self.db.get_connection()
        try:
            if project_id:
                cursor = await conn.execute(
                    "SELECT * FROM sync_conflicts WHERE project_id = ? ORDER BY created_at DESC LIMIT ?;",
                    (project_id, limit),
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM sync_conflicts ORDER BY created_at DESC LIMIT ?;",
                    (limit,),
                )
            rows = await cursor.fetchall()
            conflicts = []
            for row in rows:
                r = dict(row)
                r["applied_payload"] = _from_json(r.get("applied_payload"))
                r["rejected_payload"] = _from_json(r.get("rejected_payload"))
                conflicts.append(r)
            return conflicts
        finally:
            await conn.close()
