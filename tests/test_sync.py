import asyncio
import os
import tempfile
import pytest
from datetime import datetime, timezone
from pathlib import Path

from sync.protocol import (
    Device,
    DeviceStatus,
    SyncRecord,
    SyncRecordType,
    ConflictType,
    PushRequest,
    PullRequest,
    SyncState,
)
from sync.identity import (
    derive_project_id,
    generate_device_credentials,
    hash_device_token,
)
from sync.sanitizer import (
    sanitize_payload,
    assert_payload_is_clean,
    PayloadSanitizationError,
)
from sync.conflicts import ConflictResolver
from sync.server import (
    SyncServerStore,
    DeviceAuthenticationError,
    DeviceRevokedError,
)
from sync.engine import SyncEngine
from storage.sqlite.db import DatabaseManager
from storage.sqlite.sync_repo import SyncRepository


# ---------------------------------------------------------------------------
# 1. Protocol Serialization & Versioning
# ---------------------------------------------------------------------------
def test_protocol_serialization_and_versioning():
    record = SyncRecord(
        record_id="rec-101",
        project_id="proj-alpha",
        record_type=SyncRecordType.MEMORY,
        entity_id="mem-42",
        revision=2,
        origin_device_id="dev-laptop",
        payload={
            "key": "framework_choice",
            "epistemic_status": "VERIFIED",
            "content": "Using FastAPI and SQLite WAL",
        },
    )
    serialized = record.to_dict()
    assert serialized["protocol_version"] == "1.0"
    assert serialized["record_id"] == "rec-101"
    assert serialized["record_type"] == "memory"
    assert serialized["entity_id"] == "mem-42"
    assert serialized["revision"] == 2

    # Roundtrip deserialization
    deserialized = SyncRecord.from_dict(serialized)
    assert deserialized.record_id == record.record_id
    assert deserialized.payload == record.payload
    assert deserialized.record_type == SyncRecordType.MEMORY


# ---------------------------------------------------------------------------
# 2. Secret Sanitizer & Path Scrubbing
# ---------------------------------------------------------------------------
def test_secret_sanitizer():
    dirty_payload = {
        "anthropic_key": "sk-ant-api03-abcdef1234567890abcdef1234567890",
        "openai_key": "sk-abcdef1234567890abcdef1234567890abcdef12",
        "gh_token": "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
        "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END OPENSSH PRIVATE KEY-----",
        "bearer": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz",
        "local_windows_path": "C:\\Users\\Moiz\\Desktop\\AI Supervisior\\secret_file.py",
        "local_posix_path": "/home/developer/workspace/project/secrets.env",
        "clean_field": "Supervised Verification Passed",
        "nested": {
            "auth_password": "super_secret_password_123",
            "regular_note": "Task completed successfully",
        },
    }

    cleaned = sanitize_payload(dirty_payload)

    # Verify secrets stripped
    assert "sk-ant" not in cleaned["anthropic_key"]
    assert cleaned["anthropic_key"] == "[REDACTED_CREDENTIAL]"
    assert cleaned["openai_key"] == "[REDACTED_CREDENTIAL]"
    assert cleaned["gh_token"] == "[REDACTED_CREDENTIAL]"
    assert cleaned["private_key"] == "[REDACTED_CREDENTIAL]" or cleaned["private_key"] == "[REDACTED_SECRET]"
    assert cleaned["bearer"] == "[REDACTED_CREDENTIAL]" or cleaned["bearer"] == "[REDACTED_SECRET]"
    assert cleaned["nested"]["auth_password"] == "[REDACTED_CREDENTIAL]"

    # Verify paths scrubbed to safe relative references
    assert "C:\\Users" not in cleaned["local_windows_path"]
    assert "[local_path:/secret_file.py]" in cleaned["local_windows_path"]
    assert "/home/developer" not in cleaned["local_posix_path"]
    assert "[local_path:/secrets.env]" in cleaned["local_posix_path"]

    # Clean fields preserved
    assert cleaned["clean_field"] == "Supervised Verification Passed"
    assert cleaned["nested"]["regular_note"] == "Task completed successfully"

    # assert_payload_is_clean behavior
    assert_payload_is_clean(cleaned)
    with pytest.raises(PayloadSanitizationError):
        assert_payload_is_clean({"secret": "sk-ant-api03-abcdef1234567890abcdef1234567890"})


# ---------------------------------------------------------------------------
# 3. Project Identity Derivation
# ---------------------------------------------------------------------------
def test_project_identity_derivation():
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Fallback deterministic fingerprint
        project_id_1 = derive_project_id(tmpdir)
        assert project_id_1.startswith("local-project:") or project_id_1.startswith("proj")
        assert len(project_id_1) > 10

        # Subdirectory identical files produce identical fingerprint
        file_path = Path(tmpdir) / "config.json"
        file_path.write_text('{"name": "test"}', encoding="utf-8")
        project_id_2 = derive_project_id(tmpdir)
        project_id_3 = derive_project_id(tmpdir)
        assert project_id_2 == project_id_3

        # Path independence: Ensure absolute host path does NOT appear in project_id
        assert tmpdir not in project_id_2
        assert "Users" not in project_id_2
        assert "/" not in project_id_2
        assert "\\" not in project_id_2


# ---------------------------------------------------------------------------
# 4. Outbox & Inbox Persistence, Deduplication & Retries
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_outbox_persistence_retry_and_dedupe():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_supervisor.db")
        db = DatabaseManager(db_path)
        await db.init_db()
        repo = SyncRepository(db)

        record = SyncRecord(
            record_id="rec-test-outbox",
            project_id="proj-demo",
            record_type=SyncRecordType.TASK,
            entity_id="task-001",
            revision=1,
            origin_device_id="dev-1",
            payload={"status": "IN_PROGRESS"},
        )

        # Enqueue once
        outbox_id_1 = await repo.enqueue_outbox(record, idempotency_key="task-001-rev1")
        assert outbox_id_1 is not None

        # Duplicate enqueue returns existing outbox_id without duplicating rows
        outbox_id_2 = await repo.enqueue_outbox(record, idempotency_key="task-001-rev1")
        assert outbox_id_2 == outbox_id_1

        pending = await repo.get_pending_outbox(limit=10)
        assert len(pending) == 1
        assert pending[0]["record_id"] == "rec-test-outbox"

        # Record failure
        await repo.mark_outbox_failed(outbox_id_1, error_message="Network timeout")
        pending_after_fail = await repo.get_pending_outbox(limit=10)
        assert len(pending_after_fail) == 1
        assert pending_after_fail[0]["attempts"] == 1
        assert pending_after_fail[0]["status"] == "RETRY"

        # Mark sent
        await repo.mark_outbox_sent(outbox_id_1)
        pending_sent = await repo.get_pending_outbox(limit=10)
        assert len(pending_sent) == 0


@pytest.mark.asyncio
async def test_inbox_deduplication_and_processing():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_supervisor.db")
        db = DatabaseManager(db_path)
        await db.init_db()
        repo = SyncRepository(db)

        record = SyncRecord(
            record_id="rec-inbox-01",
            project_id="proj-demo",
            record_type=SyncRecordType.TASK,
            entity_id="task-002",
            revision=1,
            origin_device_id="dev-remote",
            payload={"status": "COMPLETED"},
        )

        inbox_id_1 = await repo.enqueue_inbox(record)
        assert inbox_id_1 is not None

        # Duplicate record_id in inbox is ignored
        inbox_id_2 = await repo.enqueue_inbox(record)
        assert inbox_id_2 is None

        pending = await repo.get_unprocessed_inbox(limit=10)
        assert len(pending) == 1
        assert pending[0]["record_id"] == "rec-inbox-01"

        await repo.mark_inbox_processed(pending[0]["id"])
        pending_after = await repo.get_unprocessed_inbox(limit=10)
        assert len(pending_after) == 0


# ---------------------------------------------------------------------------
# 5. Cloud Sync Server: Device Auth, Revocation & Push Idempotency
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_server_device_registration_auth_and_revocation():
    server = SyncServerStore()

    # Register Laptop
    device_id, token = await server.register_device("Laptop", "MacBook Pro M3")
    assert device_id.startswith("dev_") or device_id.startswith("dev-")
    assert len(token) > 20

    # Auth valid
    auth_device = await server.authenticate_device(device_id, token)
    assert auth_device.device_id == device_id
    assert auth_device.status == DeviceStatus.ACTIVE

    # Auth invalid token raises
    with pytest.raises(DeviceAuthenticationError):
        await server.authenticate_device(device_id, "invalid_secret_token")

    # Revoke device
    revoked = await server.revoke_device(device_id)
    assert revoked.status == DeviceStatus.REVOKED

    # Revoked device is denied
    with pytest.raises(DeviceRevokedError):
        await server.authenticate_device(device_id, token)


@pytest.mark.asyncio
async def test_idempotent_push_and_project_isolated_pull():
    server = SyncServerStore()
    dev_a, token_a = await server.register_device("Dev A", "Machine A")
    dev_b, token_b = await server.register_device("Dev B", "Machine B")

    # Push records for project A
    record_a1 = SyncRecord(
        record_id="rec-projA-1",
        project_id="project-alpha",
        record_type=SyncRecordType.MISSION,
        entity_id="mis-001",
        revision=1,
        origin_device_id=dev_a,
        payload={"title": "Phase 12 Sync Mission"},
    )
    record_a2 = SyncRecord(
        record_id="rec-projA-2",
        project_id="project-alpha",
        record_type=SyncRecordType.TASK,
        entity_id="task-001",
        revision=1,
        origin_device_id=dev_a,
        payload={"title": "Deploy API"},
    )

    req_push = PushRequest(
        device_id=dev_a,
        project_id="project-alpha",
        records=[record_a1, record_a2],
    )

    res1 = await server.push(req_push, token_a)
    assert res1.accepted_count == 2
    assert res1.new_cursor == 2

    # Idempotent re-push of same records: duplicate count reflects deduplication
    res2 = await server.push(req_push, token_a)
    assert res2.accepted_count == 0
    assert res2.duplicate_count == 2
    assert res2.new_cursor == 2

    # Push record for separate project B
    record_b1 = SyncRecord(
        record_id="rec-projB-1",
        project_id="project-beta",
        record_type=SyncRecordType.MISSION,
        entity_id="mis-999",
        revision=1,
        origin_device_id=dev_b,
        payload={"title": "Top Secret Beta Mission"},
    )
    await server.push(
        PushRequest(device_id=dev_b, project_id="project-beta", records=[record_b1]),
        token_b,
    )

    # Pull project A: strictly isolated, never sees project B
    pull_a = await server.pull(
        PullRequest(device_id=dev_b, project_id="project-alpha", since_cursor=0),
        token_b,
    )
    assert len(pull_a.records) == 2
    for r in pull_a.records:
        assert r.project_id == "project-alpha"
        assert r.project_id != "project-beta"

    # Pull project B: strictly isolated
    pull_b = await server.pull(
        PullRequest(device_id=dev_a, project_id="project-beta", since_cursor=0),
        token_a,
    )
    assert len(pull_b.records) == 1
    assert pull_b.records[0].project_id == "project-beta"


# ---------------------------------------------------------------------------
# 6. Conflict Resolution Domain Rules
# ---------------------------------------------------------------------------
def test_conflict_resolution_epistemic_hierarchy():
    resolver = ConflictResolver()

    # VERIFIED memory wins over UNVERIFIED/INFERRED even if local has lower revision
    local_rec = SyncRecord(
        record_id="mem-1",
        project_id="p1",
        record_type=SyncRecordType.MEMORY,
        entity_id="mem-db",
        revision=1,
        origin_device_id="dev-1",
        payload={"key": "db_driver", "epistemic_status": "INFERRED", "val": "sqlite"},
    )
    remote_rec = SyncRecord(
        record_id="mem-2",
        project_id="p1",
        record_type=SyncRecordType.MEMORY,
        entity_id="mem-db",
        revision=1,
        origin_device_id="dev-2",
        payload={"key": "db_driver", "epistemic_status": "VERIFIED", "val": "aiosqlite_wal"},
    )

    resolution = resolver.resolve(local_rec, remote_rec)
    assert resolution.winning_record.payload["epistemic_status"] == "VERIFIED"
    assert resolution.conflict.resolution == "remote_won"

    # Downgrades are BLOCKED: Local VERIFIED will NOT be downgraded by remote UNVERIFIED
    local_verified = SyncRecord(
        record_id="mem-3",
        project_id="p1",
        record_type=SyncRecordType.MEMORY,
        entity_id="mem-db",
        revision=2,
        origin_device_id="dev-1",
        payload={"key": "db_driver", "epistemic_status": "VERIFIED", "val": "aiosqlite_wal"},
    )
    remote_unverified = SyncRecord(
        record_id="mem-4",
        project_id="p1",
        record_type=SyncRecordType.MEMORY,
        entity_id="mem-db",
        revision=3,  # Higher revision, but lower epistemic rank
        origin_device_id="dev-2",
        payload={"key": "db_driver", "epistemic_status": "UNVERIFIED", "val": "mock"},
    )
    res_downgrade = resolver.resolve(local_verified, remote_unverified)
    assert res_downgrade.winning_record.payload["epistemic_status"] == "VERIFIED"
    assert res_downgrade.conflict.resolution == "local_won"


def test_conflict_resolution_task_and_verification_monotonicity():
    resolver = ConflictResolver()

    # Completed task cannot regress to PENDING or IN_PROGRESS
    local_completed = SyncRecord(
        record_id="t1",
        project_id="p1",
        record_type=SyncRecordType.TASK,
        entity_id="task-42",
        revision=1,
        origin_device_id="dev-1",
        payload={"status": "COMPLETED"},
    )
    remote_regressed = SyncRecord(
        record_id="t2",
        project_id="p1",
        record_type=SyncRecordType.TASK,
        entity_id="task-42",
        revision=2,
        origin_device_id="dev-2",
        payload={"status": "IN_PROGRESS"},
    )
    res_task = resolver.resolve(local_completed, remote_regressed)
    assert res_task.winning_record.payload["status"] == "COMPLETED"
    assert res_task.conflict.resolution == "local_won"

    # Verification outcome PASSED cannot regress to PENDING
    local_verif_passed = SyncRecord(
        record_id="v1",
        project_id="p1",
        record_type=SyncRecordType.VERIFICATION,
        entity_id="verif-1",
        revision=1,
        origin_device_id="dev-1",
        payload={"outcome": "PASSED"},
    )
    remote_verif_pending = SyncRecord(
        record_id="v2",
        project_id="p1",
        record_type=SyncRecordType.VERIFICATION,
        entity_id="verif-1",
        revision=2,
        origin_device_id="dev-2",
        payload={"outcome": "PENDING"},
    )
    res_verif = resolver.resolve(local_verif_passed, remote_verif_pending)
    assert res_verif.winning_record.payload["outcome"] == "PASSED"
    assert res_verif.conflict.resolution == "local_won"


def test_conflict_resolution_tombstone_precedence():
    resolver = ConflictResolver()
    tombstone = SyncRecord(
        record_id="tomb-1",
        project_id="p1",
        record_type=SyncRecordType.TOMBSTONE,
        entity_id="item-x",
        revision=5,
        origin_device_id="dev-1",
        payload={"deleted": True},
    )
    resurrected_item = SyncRecord(
        record_id="item-1",
        project_id="p1",
        record_type=SyncRecordType.MEMORY,
        entity_id="item-x",
        revision=4,
        origin_device_id="dev-2",
        payload={"val": "stale_write"},
    )
    res = resolver.resolve(tombstone, resurrected_item)
    assert res.winning_record.record_type == SyncRecordType.TOMBSTONE


# ---------------------------------------------------------------------------
# 7. Offline Queue Persistence & Engine Sync
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_offline_queue_and_engine_sync():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_supervisor.db")
        db = DatabaseManager(db_path)
        await db.init_db()
        repo = SyncRepository(db)
        server = SyncServerStore()

        # Register local device
        dev_id, token = await server.register_device("Dev 1", "Localhost")
        device_obj = Device(
            device_id=dev_id,
            device_name="Dev 1",
            device_token_hash=hash_device_token(token),
            status=DeviceStatus.ACTIVE,
        )
        await repo.register_device(device_obj)

        engine = SyncEngine(
            db=db,
            sync_repo=repo,
            sync_server=server,
            device_id=dev_id,
            device_token=token,
            project_id="proj-offline-test",
        )

        # 1. Record changes offline
        await engine.record_local_change(
            record_type=SyncRecordType.MISSION,
            entity_id="mis-off-1",
            payload={"status": "IN_PROGRESS", "title": "Offline Mission"},
            revision=1,
        )

        # Outbox should have 1 pending item
        pending = await repo.get_pending_outbox()
        assert len(pending) == 1
        assert engine.get_status().outbox_pending_count == 1

        # 2. Sync now flushes outbox to server
        res = await engine.sync_now()
        assert res.pushed_count == 1
        assert res.success is True
        assert engine.get_status().outbox_pending_count == 0
        assert engine.get_status().state == SyncState.SYNCED


# ---------------------------------------------------------------------------
# 8. Pre-Phase-12 Schema Upgrade
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schema_upgrade_pre_phase_12():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "pre_phase12.db")
        # Initialize standard database manager
        db = DatabaseManager(db_path)
        await db.init_db()

        # Check sync tables exist and are functional
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sync_%';"
            )
            tables = [row[0] for row in await cursor.fetchall()]

        expected_tables = {
            "sync_devices",
            "sync_outbox",
            "sync_inbox",
            "sync_cursors",
            "sync_tombstones",
            "sync_conflicts",
        }
        for tbl in expected_tables:
            assert tbl in tables, f"Expected table {tbl} was not found after initialization"


# ---------------------------------------------------------------------------
# 9. Multi-Device Killer Scenario
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_multi_device_killer_scenario():
    """
    Device A (Laptop) runs mission -> fails -> watchdog intervention -> handoff ->
    verification -> memory recorded -> synced to cloud.
    Device B (Desktop) registers -> pulls project -> reconstructs entire lifecycle,
    verified memory, and verification result without raw code or credentials.
    """
    server = SyncServerStore()

    # Setup Laptop (Device A)
    laptop_dir = tempfile.TemporaryDirectory()
    laptop_db = DatabaseManager(str(Path(laptop_dir.name) / "laptop.db"))
    await laptop_db.init_db()
    laptop_repo = SyncRepository(laptop_db)

    dev_laptop, token_laptop = await server.register_device("Laptop", "MacBook Pro")
    await laptop_repo.register_device(
        Device(
            device_id=dev_laptop,
            device_name="Laptop",
            device_token_hash=hash_device_token(token_laptop),
            status=DeviceStatus.ACTIVE,
        )
    )
    project_id = "proj-universal-ai-ops"

    laptop_engine = SyncEngine(
        db=laptop_db,
        sync_repo=laptop_repo,
        sync_server=server,
        device_id=dev_laptop,
        device_token=token_laptop,
        project_id=project_id,
    )

    # 1. Mission lifecycle on Laptop
    await laptop_engine.record_local_change(
        record_type=SyncRecordType.MISSION,
        entity_id="mis-001",
        payload={"title": "Refactor Data Pipeline", "status": "IN_PROGRESS"},
        revision=1,
    )
    # Task 1 failed watchdog check
    await laptop_engine.record_local_change(
        record_type=SyncRecordType.WATCHDOG,
        entity_id="watch-001",
        payload={"verdict": "TRIGGERED", "rule": "NO_INFINITE_LOOP", "action": "INTERVENE"},
        revision=1,
    )
    # Handoff created
    await laptop_engine.record_local_change(
        record_type=SyncRecordType.HANDOFF,
        entity_id="handoff-001",
        payload={"from_agent": "claude-code", "to_agent": "codex", "reason": "watchdog_loop"},
        revision=1,
    )
    # Independent verification passed
    await laptop_engine.record_local_change(
        record_type=SyncRecordType.VERIFICATION,
        entity_id="verif-001",
        payload={"outcome": "PASSED", "criteria": "pytest_green", "evidence": "250 passed"},
        revision=1,
    )
    # Epistemic Memory recorded
    await laptop_engine.record_local_change(
        record_type=SyncRecordType.MEMORY,
        entity_id="mem-001",
        payload={
            "key": "chunk_size_tuning",
            "epistemic_status": "VERIFIED",
            "value": "1000 items per batch",
            "api_key": "sk-ant-api03-secret1234567890abcdef1234567890", # should be sanitized!
        },
        revision=1,
    )

    # Sync Laptop to Cloud Server
    laptop_sync_res = await laptop_engine.sync_now()
    assert laptop_sync_res.pushed_count == 5
    assert laptop_sync_res.success is True

    # Setup Desktop (Device B)
    desktop_dir = tempfile.TemporaryDirectory()
    desktop_db = DatabaseManager(str(Path(desktop_dir.name) / "desktop.db"))
    await desktop_db.init_db()
    desktop_repo = SyncRepository(desktop_db)

    dev_desktop, token_desktop = await server.register_device("Desktop", "Linux Workstation")
    await desktop_repo.register_device(
        Device(
            device_id=dev_desktop,
            device_name="Desktop",
            device_token_hash=hash_device_token(token_desktop),
            status=DeviceStatus.ACTIVE,
        )
    )

    desktop_engine = SyncEngine(
        db=desktop_db,
        sync_repo=desktop_repo,
        sync_server=server,
        device_id=dev_desktop,
        device_token=token_desktop,
        project_id=project_id,
    )

    # Desktop syncs from Cloud Server
    desktop_sync_res = await desktop_engine.sync_now()
    assert desktop_sync_res.pulled_count == 5
    assert desktop_sync_res.success is True

    # Verify Desktop inbox received all records and memory is clean
    cursor = await desktop_repo.get_cursor(project_id)
    assert cursor == 5

    # Check sanitized payload in inbox
    unprocessed = await desktop_repo.get_unprocessed_inbox()
    mem_record = next(r for r in unprocessed if r["entity_id"] == "mem-001")
    assert mem_record["payload"]["epistemic_status"] == "VERIFIED"
    assert mem_record["payload"]["api_key"] in ("[REDACTED_API_KEY]", "[REDACTED_CREDENTIAL]")
    assert "sk-ant" not in mem_record["payload"]["api_key"]

    laptop_dir.cleanup()
    desktop_dir.cleanup()


# ---------------------------------------------------------------------------
# 10. Negative Scenarios: Revocation & Cloud Downtime Resilience
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_negative_revocation_and_offline_resilience():
    server = SyncServerStore()
    dev_rogue, token_rogue = await server.register_device("Rogue Device", "Untrusted")

    # Revoke device immediately
    await server.revoke_device(dev_rogue)

    # Rogue push attempt is rejected
    push_req = PushRequest(
        device_id=dev_rogue,
        project_id="p1",
        records=[
            SyncRecord(
                record_id="r1",
                project_id="p1",
                record_type=SyncRecordType.TASK,
                entity_id="t1",
                revision=1,
                origin_device_id=dev_rogue,
                payload={},
            )
        ],
    )
    with pytest.raises(DeviceRevokedError):
        await server.push(push_req, token_rogue)

    # Cloud downtime resilience: local supervisor continues unaffected
    with tempfile.TemporaryDirectory() as tmpdir:
        db = DatabaseManager(str(Path(tmpdir) / "offline.db"))
        await db.init_db()
        repo = SyncRepository(db)

        # Engine configured with invalid / disconnected server
        engine = SyncEngine(
            db=db,
            sync_repo=repo,
            sync_server=None,  # No server configured (offline)
            device_id="dev-local",
            device_token="token",
            project_id="p1",
        )

        # Record changes works 100% fine locally without cloud
        await engine.record_local_change(
            record_type=SyncRecordType.TASK,
            entity_id="t2",
            payload={"status": "IN_PROGRESS"},
            revision=1,
        )
        assert engine.get_status().outbox_pending_count == 1

        # Sync attempt fails gracefully without throwing an unhandled exception
        res = await engine.sync_now()
        assert res.success is False
        assert "not configured" in res.error_message.lower()
        assert engine.get_status().state == SyncState.OFFLINE
