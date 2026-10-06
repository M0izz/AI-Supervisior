# Multi-Device Project Continuity Guide

## 1. The Seamless Workstation Transition

Modern software development spans multiple machines: a laptop while travelling or in meetings, and a powerful multi-monitor desktop in the office.

With Phase 12 Cloud Sync, AI Supervisor enables seamless project continuity:
1. **On Laptop**: You launch a mission, supervise an agent, and a watchdog triggers intervention. The agent is handed off, a test suite is independently verified, and verified project memory is recorded.
2. **On Desktop**: You sit down at your desk. The local desktop Supervisor pulls the synchronized project history.
3. **Continuity**: The desktop Supervisor displays the entire mission lifecycle, verified memories, and task status without re-running completed work or duplicating tokens.

---

## 2. Pairing a New Device

To connect a new computer:
1. Open the Control Room or terminal on your primary computer.
2. Register the new machine:
   ```bash
   curl -X POST http://localhost:8000/api/sync/devices/register \
     -H "Content-Type: application/json" \
     -d '{"device_name": "Studio Desktop", "platform": "Windows 11"}'
   ```
3. Copy the returned `device_id` and `device_token` to the `.env` on your new computer:
   ```env
   SUPERVISOR_DEVICE_ID=dev_...
   SUPERVISOR_DEVICE_TOKEN=tok_...
   SUPERVISOR_SYNC_SERVER=http://your-sync-server:8000
   ```
4. Start AI Supervisor on the new computer. It will automatically derive the path-independent project identity and sync history.

---

## 3. Offline Mode & Conflict Scenarios

### Working on an Airplane or Offline
- The local Supervisor operates with zero degradation.
- All decisions, watchdog triggers, and memory updates are queued in `sync_outbox`.
- When WiFi reconnects, the engine automatically flushes the queue with zero data loss.

### Conflicting Updates
If two machines update the same memory item offline:
- If Machine A recorded an `INFERRED` fact and Machine B recorded a `VERIFIED` fact, the `VERIFIED` fact deterministically wins on both machines.
- If Machine A completed a task, Machine B cannot regress it to `PENDING`.
- All decisions are logged in `sync_conflicts` for full operator visibility.
