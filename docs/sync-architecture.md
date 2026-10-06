# Cloud Sync & Multi-Device Architecture

## 1. System Vision & Foundational Invariant

AI Supervisor is a personal AI operations layer that manages, coordinates, supervises, recovers, and verifies the AI agents a developer already uses.

The foundational invariant of Phase 12:

> **"Cloud sync may replicate Supervisor state, but it must never become a higher authority than the local Supervisor."**

The local Supervisor on the developer's workstation remains 100% authoritative for:
- Agent execution & process lifecycle
- Watchdog decisions & intervention
- Safety policies, prohibited paths & commands
- Worktree isolation & branch merges
- Independent verification runs
- Interactive approvals
- Absence Mode enforcement
- Secrets, credentials, and local filesystem access

Cloud synchronization is **not** the Supervisor itself; it is a **local-first replication and continuity layer**.

```text
Laptop Workstation (Local Supervisor)              Cloud Sync Service                Desktop Workstation (Local Supervisor)
      │                                                   │                                                │
[Outbox Queue]                                            │                                                │
      │── Push Sanitized Records (Cursor N) ─────────────>│                                                │
      │<─ Ack (Server Cursor N) ──────────────────────────│                                                │
      │                                                   │── Pull Since Cursor (0) ──────────────────────>│
      │                                                   │<─ Sanitized Records ───────────────────────────│
      │                                                   │                                                │
                                                                                                    [Inbox Queue]
                                                                                                           │
                                                                                                  [Conflict Resolver]
                                                                                                           │
                                                                                                  [Local DB WAL State]
```

---

## 2. Architectural Pillars

### Local-First & Offline-First Execution
All Supervisor mutations (missions, tasks, watchdog interventions, handoffs, verification outcomes, epistemic memory) are committed directly to the local SQLite WAL database immediately. The local supervisor functions at 100% capacity whether the machine is completely air-gapped, offline, in flight, or experiencing cloud downtime.

### Outbox & Inbox Pattern
- **Outbox Queue (`sync_outbox`)**: Mutations to syncable domain entities are enqueued into the local outbox. An asynchronous worker flushes pending outbox records to the sync service when network connectivity is available.
- **Inbox Queue (`sync_inbox`)**: Incoming remote records from other registered devices are placed into the inbox, deduplicated, and reconciled sequentially via the deterministic `ConflictResolver`.

### Path-Independent Project Identity
Local filesystem paths (`C:\Users\Moiz\Desktop\AI Supervisior` vs `/home/developer/workspace/ai-supervisor`) are never shared or used as identifiers. Projects are identified by:
1. Canonical Git remote origin URL (`repo:github.com/m0izz/ai-supervisior`)
2. Git root commit hash fallback (`commit:<hash>`)
3. Deterministic folder fingerprint fallback (`local-project:<name>-<hash>`)

### Zero-Secret Data Boundary
Before any payload enters the outbox or crosses the network, it passes through the recursive `sanitize_payload()` engine. All API keys, private keys, bearer tokens, passwords, and absolute filesystem paths are scrubbed into redactions and relative tokens (`[local_path:/...]`).

---

## 3. Storage Schema Integration

Six dedicated tables in `storage/sqlite/schema.sql` manage multi-device replication:

| Table | Purpose |
|---|---|
| `sync_devices` | Local registry of known paired devices and their authentication status (`ACTIVE`, `REVOKED`) |
| `sync_outbox` | Persistent queue of outbound local changes awaiting push to the cloud |
| `sync_inbox` | Persistent queue of inbound remote changes awaiting processing & reconciliation |
| `sync_cursors` | Tracks incremental sync pagination cursors per project and device |
| `sync_tombstones` | Persistent audit records of deleted entities to prevent phantom resurrection |
| `sync_conflicts` | Audit log of all conflict resolution decisions, preserved for developer transparency |

---

## 4. Conflict Resolution Hierarchy

Conflicts are resolved deterministically without human blocking or clobbering:
1. **Memory Epistemic Hierarchy**: Higher epistemic certainty always wins (`VERIFIED` > `REJECTED` > `DECIDED` > `OBSERVED` > `INFERRED` > `UNVERIFIED`). Downgrades are rejected.
2. **Task Non-Regression**: Tasks in terminal states (`COMPLETED`, `VERIFIED`) cannot regress to `PENDING` or `IN_PROGRESS`.
3. **Verification Monotonicity**: Verification outcomes `PASSED` or `FAILED` cannot revert to `PENDING`.
4. **Approval Permanence**: Resolved approvals (`APPROVED`, `DENIED`) cannot regress to `PENDING`.
5. **Tombstone Precedence**: Valid deletions absorb live writes of equal or lower revision.
6. **Local Safety Invariant**: Local Supervisor security policy always overrides remote suggestions.
