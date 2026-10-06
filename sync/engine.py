"""
AI Supervisor — Local Offline-First Sync Engine
Manages outbound outbox flushes, inbound pull reconciliation, deterministic
conflict resolution against local SQLite repositories, and offline resilience.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from storage.sqlite.db import DatabaseManager
    from storage.sqlite.sync_repo import SyncRepository

from sync.conflicts import ConflictResolver
from sync.identity import derive_project_id
from sync.protocol import (
    PROTOCOL_VERSION,
    ConflictType,
    PullRequest,
    PushRequest,
    SyncRecord,
    SyncState,
    SyncStatus,
)
from sync.sanitizer import sanitize_payload
from sync.server import DeviceRevokedError, SyncAuthError, SyncServerStore

logger = logging.getLogger("supervisor.sync.engine")


class SyncEngine:
    """
    Local-first synchronization engine running on a developer workstation.
    Pushes local changes from the persistent outbox, pulls remote updates,
    and resolves conflicts without ever blocking local mission execution.
    """

    def __init__(
        self,
        db: Any,
        sync_repo: Any,
        server_store: Optional[SyncServerStore] = None,
        sync_server: Optional[SyncServerStore] = None,
        device_id: str = "dev_default",
        device_token: str = "tok_default",
        project_id: Optional[str] = None,
        sync_interval_seconds: float = 5.0,
    ):
        self.db = db
        self.sync_repo = sync_repo
        self.server_store = sync_server or server_store
        self.device_id = device_id
        self.device_token = device_token
        self.project_id = project_id or derive_project_id()
        self.sync_interval_seconds = sync_interval_seconds

        self.state: SyncState = SyncState.ONLINE
        self.last_synced_at: Optional[str] = None
        self.last_error_message: Optional[str] = None
        self.cursor_key = f"cur_{self.project_id}_{self.device_id}"
        self._cached_pending_count: int = 0

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

    def set_server_store(self, store: SyncServerStore) -> None:
        self.server_store = store

    def get_status(self) -> SyncStatus:
        return SyncStatus(
            state=self.state,
            device_id=self.device_id,
            project_id=self.project_id,
            pending_outbox_count=self._cached_pending_count,
            outbox_pending_count=self._cached_pending_count,
            last_synced_at=self.last_synced_at,
            last_pull_cursor=0,
            connected_devices_count=1,
            error_message=self.last_error_message,
        )

    async def record_local_change(
        self,
        record_type: Any,
        entity_id: Optional[str] = None,
        record_id: Optional[str] = None,
        payload: Dict[str, Any] = {},
        revision: int = 1,
        deleted: bool = False,
    ) -> str:
        """
        Enqueues a local entity mutation to the persistent outbox.
        Sanitizes payload immediately so forbidden data never enters SQLite outbox.
        """
        rec_id = entity_id or record_id or f"rec_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        clean_payload = sanitize_payload(payload)

        record = SyncRecord(
            record_id=rec_id,
            entity_id=rec_id,
            record_type=record_type,
            project_id=self.project_id,
            device_id=self.device_id,
            origin_device_id=self.device_id,
            revision=revision,
            schema_version="1.0.0",
            created_at=now,
            updated_at=now,
            deleted_at=now if deleted else None,
            payload=clean_payload,
        )

        outbox_id = await self.sync_repo.enqueue_outbox(record)
        self._cached_pending_count += 1
        logger.debug(f"Enqueued local change {rec_id} ({record_type}) to outbox {outbox_id}")
        return outbox_id

    async def sync_once(self) -> Any:
        """
        Performs an offline-first synchronization round:
        1. Flush pending outbox records (Push)
        2. Fetch remote records beyond local cursor (Pull)
        3. Reconcile and apply incoming changes through ConflictResolver
        """
        from sync.protocol import SyncRoundResult
        async with self._lock:
            if not self.server_store:
                self.state = SyncState.OFFLINE
                self.last_error_message = "Sync server is not configured"
                return SyncRoundResult(
                    success=False,
                    pushed_count=0,
                    pulled_count=0,
                    state=self.state,
                    error_message=self.last_error_message,
                )

            self.state = SyncState.SYNCING
            self.last_error_message = None
            pushed_count = 0
            pulled_count = 0

            try:
                # 1. Push Phase
                pending_outbox = await self.sync_repo.get_pending_outbox(limit=100)
                if pending_outbox:
                    push_records = []
                    outbox_ids = []
                    for item in pending_outbox:
                        rec = SyncRecord(
                            record_id=item["record_id"],
                            entity_id=item.get("entity_id") or item["record_id"],
                            record_type=item["record_type"],
                            project_id=item["project_id"],
                            device_id=item["device_id"],
                            origin_device_id=item.get("origin_device_id") or item["device_id"],
                            revision=item["revision"],
                            schema_version=item["schema_version"],
                            created_at=item["created_at"],
                            updated_at=item["updated_at"],
                            deleted_at=item["deleted_at"],
                            payload=item["payload"],
                        )
                        push_records.append(rec)
                        outbox_ids.append(item["outbox_id"])

                    push_req = PushRequest(
                        client_id="ai_supervisor_local",
                        device_id=self.device_id,
                        device_token=self.device_token,
                        project_id=self.project_id,
                        records=push_records,
                    )

                    push_resp = await self.server_store.push(push_req)
                    if push_resp.success:
                        await self.sync_repo.mark_outbox_synced(outbox_ids)
                        pushed_count = len(outbox_ids)
                        self._cached_pending_count = max(0, self._cached_pending_count - pushed_count)

                        # Record any server-flagged conflicts
                        for cnf in push_resp.conflicts:
                            await self.sync_repo.record_conflict(cnf)

                # 2. Pull Phase
                current_cursor = await self.sync_repo.get_cursor(self.cursor_key)
                pull_req = PullRequest(
                    device_id=self.device_id,
                    device_token=self.device_token,
                    project_id=self.project_id,
                    cursor=current_cursor,
                    limit=100,
                )

                pull_resp = await self.server_store.pull(pull_req)

                # 3. Apply Reconciled Records
                if pull_resp.records:
                    for inc in pull_resp.records:
                        # Skip own records pulled back
                        if inc.device_id == self.device_id or inc.origin_device_id == self.device_id:
                            continue

                        pulled_count += 1
                        await self.sync_repo.enqueue_inbox(inc)
                        await self._apply_incoming_record(inc)

                    # Update cursor
                    await self.sync_repo.set_cursor(
                        self.cursor_key,
                        self.project_id,
                        self.device_id,
                        pull_resp.next_cursor,
                    )

                self.state = SyncState.SYNCED
                self.last_synced_at = datetime.now(timezone.utc).isoformat()
                return SyncRoundResult(
                    success=True,
                    pushed_count=pushed_count,
                    pulled_count=pulled_count,
                    state=self.state,
                )

            except SyncAuthError as sae:
                self.state = SyncState.AUTH_REQUIRED
                self.last_error_message = str(sae)
                logger.warning(f"Sync authentication failure: {sae}")
                return SyncRoundResult(success=False, error_message=str(sae), state=self.state)

            except DeviceRevokedError as dre:
                self.state = SyncState.AUTH_REQUIRED
                self.last_error_message = str(dre)
                logger.error(f"Sync device revoked: {dre}")
                return SyncRoundResult(success=False, error_message=str(dre), state=self.state)

            except Exception as e:
                self.state = SyncState.OFFLINE
                self.last_error_message = str(e)
                logger.warning(f"Sync round failed (offline fallback active): {e}")
                return SyncRoundResult(success=False, error_message=str(e), state=self.state)

    sync_now = sync_once

    async def _apply_incoming_record(self, record: SyncRecord) -> None:
        """Reconciles an incoming record against local SQLite entity state."""
        rec_type = record.record_type.lower()
        rec_id = record.record_id

        # 1. Fetch existing local record if present
        local_data = await self._fetch_local_entity(rec_type, rec_id)

        # 2. Run deterministic conflict resolution
        res = ConflictResolver.resolve(local_data, record)

        if res.conflict:
            await self.sync_repo.record_conflict(res.conflict)

        if not res.should_apply:
            logger.info(f"Incoming sync record {rec_id} rejected by conflict resolver: {res.conflict.reason if res.conflict else 'stale'}")
            return

        # 3. Apply resolved payload to local SQLite entity table
        await self._persist_local_entity(rec_type, rec_id, res.resolved_payload, record.deleted_at is not None)

    async def _fetch_local_entity(self, record_type: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Queries local SQLite table for current state of an entity."""
        conn = await self.db.get_connection()
        try:
            if record_type in ("mission", "missions"):
                c = await conn.execute("SELECT * FROM missions WHERE mission_id = ?;", (record_id,))
                r = await c.fetchone()
                return dict(r) if r else None

            elif record_type in ("task", "tasks"):
                c = await conn.execute("SELECT * FROM tasks WHERE task_id = ?;", (record_id,))
                r = await c.fetchone()
                return dict(r) if r else None

            elif record_type in ("memory", "memory_record", "memory_records"):
                c = await conn.execute("SELECT * FROM memory_records WHERE record_id = ?;", (record_id,))
                r = await c.fetchone()
                return dict(r) if r else None

            elif record_type in ("verification", "verifications"):
                c = await conn.execute("SELECT * FROM verifications WHERE verification_id = ?;", (record_id,))
                r = await c.fetchone()
                return dict(r) if r else None

            elif record_type in ("handoff", "handoffs"):
                c = await conn.execute("SELECT * FROM handoffs WHERE handoff_id = ?;", (record_id,))
                r = await c.fetchone()
                return dict(r) if r else None

            return None
        finally:
            await conn.close()

    async def _persist_local_entity(self, record_type: str, record_id: str, payload: Dict[str, Any], is_deleted: bool) -> None:
        """Applies incoming payload into authoritative local SQLite table."""
        conn = await self.db.get_connection()
        try:
            now = datetime.now(timezone.utc).isoformat()

            if record_type in ("mission", "missions"):
                if is_deleted:
                    await conn.execute("UPDATE missions SET status = 'CANCELLED' WHERE mission_id = ?;", (record_id,))
                else:
                    q = """
                    INSERT INTO missions (mission_id, title, goal, repository_path, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(mission_id) DO UPDATE SET
                        title = excluded.title,
                        goal = excluded.goal,
                        status = excluded.status,
                        updated_at = excluded.updated_at;
                    """
                    await conn.execute(
                        q,
                        (
                            record_id,
                            payload.get("title", "Synced Mission"),
                            payload.get("goal", ""),
                            payload.get("repository_path", "."),
                            payload.get("status", "CREATED"),
                            payload.get("created_at", now),
                            payload.get("updated_at", now),
                        ),
                    )

            elif record_type in ("task", "tasks"):
                mission_id = payload.get("mission_id", "default_mission")
                # Ensure placeholder mission exists if FK enforced
                await conn.execute(
                    "INSERT OR IGNORE INTO missions (mission_id, title, status, created_at, updated_at) VALUES (?, ?, 'CREATED', ?, ?);",
                    (mission_id, "Synced Mission Placeholder", now, now),
                )
                q = """
                INSERT INTO tasks (task_id, mission_id, title, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    title = excluded.title,
                    status = excluded.status,
                    updated_at = excluded.updated_at;
                """
                await conn.execute(
                    q,
                    (
                        record_id,
                        mission_id,
                        payload.get("title", "Synced Task"),
                        payload.get("status", "PENDING"),
                        payload.get("created_at", now),
                        payload.get("updated_at", now),
                    ),
                )

            elif record_type in ("memory", "memory_record", "memory_records"):
                q = """
                INSERT INTO memory_records (record_id, project_id, mission_id, category, content, status, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO UPDATE SET
                    content = excluded.content,
                    status = excluded.status,
                    confidence = excluded.confidence;
                """
                await conn.execute(
                    q,
                    (
                        record_id,
                        self.project_id,
                        payload.get("mission_id"),
                        payload.get("category", "fact"),
                        payload.get("content", ""),
                        payload.get("status", "VERIFIED"),
                        float(payload.get("confidence", 1.0)),
                        payload.get("created_at", now),
                    ),
                )

            elif record_type in ("verification", "verifications"):
                mission_id = payload.get("mission_id", "default_mission")
                task_id = payload.get("task_id", "default_task")
                await conn.execute(
                    "INSERT OR IGNORE INTO missions (mission_id, title, status, created_at, updated_at) VALUES (?, ?, 'CREATED', ?, ?);",
                    (mission_id, "Synced Mission Placeholder", now, now),
                )
                await conn.execute(
                    "INSERT OR IGNORE INTO tasks (task_id, mission_id, title, status, created_at, updated_at) VALUES (?, ?, 'Synced Task Placeholder', 'PENDING', ?, ?);",
                    (task_id, mission_id, now, now),
                )
                q = """
                INSERT INTO verifications (verification_id, mission_id, task_id, verification_type, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(verification_id) DO UPDATE SET
                    status = excluded.status;
                """
                await conn.execute(
                    q,
                    (
                        record_id,
                        mission_id,
                        task_id,
                        payload.get("verification_type", "test"),
                        payload.get("status", "PASSED"),
                        payload.get("created_at", now),
                    ),
                )

            await conn.commit()
        except Exception as e:
            logger.debug(f"Projection into local entity table {record_type} skipped: {e}")
        finally:
            await conn.close()

    async def sync_now(self) -> SyncStatus:
        """Operator-initiated synchronous sync trigger."""
        return await self.sync_once()

    def start(self) -> None:
        """Starts the background synchronization polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._background_loop())
        logger.info(f"SyncEngine started for device {self.device_id} on project {self.project_id}")

    def stop(self) -> None:
        """Stops the background synchronization loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("SyncEngine stopped")

    async def _background_loop(self) -> None:
        while self._running:
            try:
                await self.sync_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error in background sync loop: {e}")
            await asyncio.sleep(self.sync_interval_seconds)
