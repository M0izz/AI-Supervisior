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
    mission_id TEXT NOT NULL,
    task_id TEXT,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
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

-- Indexes for performance & query lookups
CREATE INDEX IF NOT EXISTS idx_tasks_mission ON tasks(mission_id);
CREATE INDEX IF NOT EXISTS idx_events_mission ON events(mission_id);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_memory_mission ON memory_records(mission_id);
CREATE INDEX IF NOT EXISTS idx_approvals_mission ON approvals(mission_id);
CREATE INDEX IF NOT EXISTS idx_verifications_mission ON verifications(mission_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_mission ON handoffs(mission_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_task ON handoffs(task_id);

