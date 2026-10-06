-- AI Supervisor Database Schema v1
-- SQLite WAL mode enabled for high-performance concurrent local-first persistence

PRAGMA foreign_keys = ON;

-- 1. Missions Table
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    repository_path TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_agents TEXT DEFAULT '[]',
    active_agent_id TEXT,
    constraints TEXT DEFAULT '{}',
    metrics TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Tasks Table
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL,
    assigned_agent TEXT,
    dependencies TEXT DEFAULT '[]',
    expected_files TEXT DEFAULT '[]',
    order_idx INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    result TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

-- 3. Agents Table
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    agent_type TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    current_task_id TEXT,
    mission_id TEXT,
    iterations INTEGER DEFAULT 0,
    tool_calls INTEGER DEFAULT 0,
    interventions INTEGER DEFAULT 0,
    last_activity TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);

-- 4. Events Table (Append-Only Event Store)
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    task_id TEXT,
    agent_id TEXT,
    provider TEXT DEFAULT 'internal',
    event_type TEXT NOT NULL,
    schema_version TEXT DEFAULT '1.0.0',
    severity TEXT DEFAULT 'info',
    timestamp TEXT NOT NULL,
    action TEXT DEFAULT '{}',
    telemetry TEXT DEFAULT '{}',
    payload TEXT DEFAULT '{}',
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

-- 5. Memory Records Table
CREATE TABLE IF NOT EXISTS memory_records (
    record_id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT '',
    mission_id TEXT,
    task_id TEXT,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    memory_type TEXT DEFAULT 'FACT',
    status TEXT DEFAULT 'OBSERVED',
    confidence REAL DEFAULT 1.0,
    source TEXT DEFAULT 'system',
    source_id TEXT DEFAULT '',
    created_by TEXT DEFAULT 'system',
    superseded_by TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

-- 6. Approvals Table
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    task_id TEXT,
    action_type TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL, -- PENDING, APPROVED, REJECTED
    requested_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT,
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

-- 7. Verifications Table
CREATE TABLE IF NOT EXISTS verifications (
    verification_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    task_id TEXT,
    verification_type TEXT NOT NULL,
    status TEXT NOT NULL, -- PENDING, PASSED, FAILED
    command TEXT,
    details TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

-- 8. Handoffs Table
CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    source_agent_id TEXT NOT NULL,
    target_agent_id TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT DEFAULT '',
    context_package TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    result TEXT,
    error TEXT,
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

-- 9. Routing Decisions Table
CREATE TABLE IF NOT EXISTS routing_decisions (
    routing_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    selected_agent_id TEXT,
    selected_adapter_id TEXT,
    decision TEXT NOT NULL, -- ROUTE, NO_ELIGIBLE_AGENT, REQUIRE_REVIEW
    score REAL DEFAULT 0.0,
    decision_reason TEXT NOT NULL,
    candidates TEXT DEFAULT '[]',
    requirements TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

-- 10. Absence Sessions Table (Phase 9)
CREATE TABLE IF NOT EXISTS absence_sessions (
    absence_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    status TEXT NOT NULL, -- DISABLED, ARMED, ACTIVE, PAUSED, EXPIRED, COMPLETED, CANCELLED, BLOCKED
    policy_snapshot TEXT NOT NULL, -- Frozen JSON of AbsencePolicy
    started_at TEXT,
    expires_at TEXT,
    created_by TEXT DEFAULT 'user',
    tasks_completed INTEGER DEFAULT 0,
    retries_count INTEGER DEFAULT 0,
    handoffs_count INTEGER DEFAULT 0,
    paused_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

-- 11. Absence Decisions Table (Auditable decision log)
CREATE TABLE IF NOT EXISTS absence_decisions (
    decision_id TEXT PRIMARY KEY,
    absence_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    task_id TEXT,
    agent_id TEXT,
    decision TEXT NOT NULL, -- ALLOW, DENY, PAUSE, REQUIRE_USER
    rule_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    action TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    timestamp TEXT NOT NULL,
    FOREIGN KEY (absence_id) REFERENCES absence_sessions(absence_id) ON DELETE CASCADE
);

-- Indexes for performance & query lookups
CREATE INDEX IF NOT EXISTS idx_tasks_mission ON tasks(mission_id);
CREATE INDEX IF NOT EXISTS idx_events_mission ON events(mission_id);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_memory_project ON memory_records(project_id);
CREATE INDEX IF NOT EXISTS idx_memory_mission ON memory_records(mission_id);
CREATE INDEX IF NOT EXISTS idx_memory_task ON memory_records(task_id);
CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_records(status);
CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_records(memory_type);
CREATE INDEX IF NOT EXISTS idx_approvals_mission ON approvals(mission_id);
CREATE INDEX IF NOT EXISTS idx_verifications_mission ON verifications(mission_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_mission ON handoffs(mission_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_task ON handoffs(task_id);
CREATE INDEX IF NOT EXISTS idx_routing_mission ON routing_decisions(mission_id);
CREATE INDEX IF NOT EXISTS idx_routing_task ON routing_decisions(task_id);
CREATE INDEX IF NOT EXISTS idx_absence_sessions_mission ON absence_sessions(mission_id);
CREATE INDEX IF NOT EXISTS idx_absence_sessions_status ON absence_sessions(status);
CREATE INDEX IF NOT EXISTS idx_absence_decisions_absence ON absence_decisions(absence_id);
CREATE INDEX IF NOT EXISTS idx_absence_decisions_mission ON absence_decisions(mission_id);

-- ============================================================================
-- Phase 12: Cloud Sync & Multi-Device Tables
-- ============================================================================

-- 12. Sync Devices Table
CREATE TABLE IF NOT EXISTS sync_devices (
    device_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    platform TEXT DEFAULT 'unknown',
    app_version TEXT DEFAULT '1.0.0',
    protocol_version TEXT DEFAULT 'sync_protocol.v1',
    device_token_hash TEXT NOT NULL,
    status TEXT NOT NULL, -- ACTIVE, REVOKED
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

-- 13. Sync Outbox Table (Local persistent outbound mutations queue)
CREATE TABLE IF NOT EXISTS sync_outbox (
    outbox_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    project_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    revision INTEGER DEFAULT 1,
    schema_version TEXT DEFAULT '1.0.0',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    payload TEXT NOT NULL,
    status TEXT NOT NULL, -- PENDING, IN_FLIGHT, SYNCED, FAILED, BLOCKED
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    in_flight_at TEXT
);

-- 14. Sync Inbox Table (Incoming remote changes queue for deduplication & processing)
CREATE TABLE IF NOT EXISTS sync_inbox (
    inbox_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    project_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    revision INTEGER DEFAULT 1,
    schema_version TEXT DEFAULT '1.0.0',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    payload TEXT NOT NULL,
    status TEXT NOT NULL, -- PENDING, PROCESSED, CONFLICT, REJECTED
    processed_at TEXT
);

-- 15. Sync Cursors Table (Tracks pagination cursors per project/device)
CREATE TABLE IF NOT EXISTS sync_cursors (
    cursor_key TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    last_cursor INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);

-- 16. Sync Tombstones Table (Persistent deletion records)
CREATE TABLE IF NOT EXISTS sync_tombstones (
    tombstone_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    project_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    revision INTEGER DEFAULT 1,
    deleted_at TEXT NOT NULL,
    payload TEXT DEFAULT '{}'
);

-- 17. Sync Conflicts Audit Log Table
CREATE TABLE IF NOT EXISTS sync_conflicts (
    conflict_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    project_id TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    resolution TEXT NOT NULL,
    applied_payload TEXT NOT NULL,
    rejected_payload TEXT,
    reason TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- Sync Indexes
CREATE INDEX IF NOT EXISTS idx_sync_outbox_status ON sync_outbox(status);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_project ON sync_outbox(project_id);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_record ON sync_outbox(record_id);
CREATE INDEX IF NOT EXISTS idx_sync_inbox_status ON sync_inbox(status);
CREATE INDEX IF NOT EXISTS idx_sync_inbox_record ON sync_inbox(record_id);
CREATE INDEX IF NOT EXISTS idx_sync_tombstones_record ON sync_tombstones(record_id);
CREATE INDEX IF NOT EXISTS idx_sync_tombstones_project ON sync_tombstones(project_id);
CREATE INDEX IF NOT EXISTS idx_sync_conflicts_project ON sync_conflicts(project_id);


