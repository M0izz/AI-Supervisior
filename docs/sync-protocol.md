# Synchronization Protocol v1 (`sync_protocol.v1`)

## 1. Overview

Protocol v1 defines the versioned communication contract between the local `SyncEngine` running inside each developer's AI Supervisor instance and the remote `SyncServerStore`.

The protocol supports:
- Idempotent push of mutations
- Incremental sequence-cursor pulls
- Project isolation
- Cryptographic device authorization & revocation
- Structural tombstone deletions

---

## 2. Protocol Envelopes

### Push Request & Response

#### PushRequest
```json
{
  "protocol_version": "sync_protocol.v1",
  "client_id": "ai_supervisor_local",
  "device_id": "dev_4b8f3a1290e2",
  "device_token": "tok_991823ab...",
  "project_id": "repo:github.com/m0izz/ai-supervisior",
  "records": [
    {
      "record_id": "rec_001",
      "record_type": "memory",
      "project_id": "repo:github.com/m0izz/ai-supervisior",
      "device_id": "dev_4b8f3a1290e2",
      "revision": 2,
      "schema_version": "1.0.0",
      "created_at": "2026-10-06T12:00:00Z",
      "updated_at": "2026-10-06T12:01:00Z",
      "deleted_at": null,
      "payload": {
        "key": "build_command",
        "epistemic_status": "VERIFIED",
        "value": "npm run build"
      }
    }
  ]
}
```

#### PushResponse
```json
{
  "success": true,
  "processed_count": 1,
  "accepted_count": 1,
  "duplicate_count": 0,
  "server_cursor": 42,
  "new_cursor": 42,
  "conflicts": []
}
```

---

### Pull Request & Response

#### PullRequest
```json
{
  "device_id": "dev_4b8f3a1290e2",
  "device_token": "tok_991823ab...",
  "project_id": "repo:github.com/m0izz/ai-supervisior",
  "cursor": 41,
  "limit": 100
}
```

#### PullResponse
```json
{
  "records": [
    {
      "record_id": "rec_001",
      "record_type": "memory",
      "project_id": "repo:github.com/m0izz/ai-supervisior",
      "device_id": "dev_4b8f3a1290e2",
      "revision": 2,
      "schema_version": "1.0.0",
      "created_at": "2026-10-06T12:00:00Z",
      "updated_at": "2026-10-06T12:01:00Z",
      "payload": {
        "key": "build_command",
        "epistemic_status": "VERIFIED",
        "value": "npm run build"
      }
    }
  ],
  "next_cursor": 42,
  "has_more": false
}
```

---

## 3. REST API Surface

| Endpoint | Method | Description |
|---|---|---|
| `/api/sync/status` | GET | Returns local engine status, outbox count, and cursor |
| `/api/sync/trigger` | POST | Triggers an immediate push/pull sync cycle |
| `/api/sync/devices/register` | POST | Registers a new device identity and generates tokens |
| `/api/sync/devices` | GET | Lists all paired devices on the local Supervisor |
| `/api/sync/devices/{id}/revoke` | POST | Revokes a device; immediately bars it from syncing |
| `/api/sync/push` | POST | Ingests outbound records into the cloud log |
| `/api/sync/pull` | POST | Streams incremental records beyond client cursor |
