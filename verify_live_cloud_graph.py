"""
Complete Real Mission Lifecycle & Live Cloud FalkorDB Verification.
"""

import time
import json
import urllib.request
import urllib.error

BASE_URL = "https://ai-supervisor-api.onrender.com"

def http_req(path, method="GET", data=None):
    url = f"{BASE_URL}{path}"
    headers = {"User-Agent": "LiveGraphVerifier/1.0", "Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8") if he.fp else ""
        try:
            return he.code, json.loads(err_body)
        except Exception:
            return he.code, {"error": err_body}
    except Exception as e:
        return 0, {"error": str(e)}

def main():
    print("=== Step 1: Triggering Idempotent Graph Backfill ===")
    status, backfill_res = http_req("/api/graph/backfill", method="POST")
    print(f"Backfill status={status}:", json.dumps(backfill_res.get("backfilled", {}), indent=2))

    print("\n=== Step 2: Creating Live Mission with Tasks ===")
    mission_payload = {
        "title": "Cloud Graph Pipeline Verification Mission",
        "goal": "Verify live connected property graph relationships across missions, tasks, agents, and verifications",
        "repository_path": "./demo/sample-project",
        "tasks": [
            {
                "id": "TASK-101",
                "title": "Analyze telemetry and routing paths",
                "dependencies": [],
                "expected_files": ["src/telemetry.py"]
            },
            {
                "id": "TASK-102",
                "title": "Implement cache recovery logic",
                "dependencies": ["TASK-101"],
                "expected_files": ["src/cache.py"]
            },
            {
                "id": "TASK-103",
                "title": "Run unit verification tests",
                "dependencies": ["TASK-102"],
                "expected_files": ["tests/test_cache.py"]
            }
        ]
    }
    status, m_res = http_req("/api/missions", method="POST", data=mission_payload)
    print("Create Mission status:", status)
    mission_id = m_res["id"]
    print(f"Created Mission ID: {mission_id}")

    print("\n=== Step 3: Executing Real Task Lifecycle with Relationships ===")
    
    # 3. Discover created tasks
    status, t_list = http_req(f"/api/missions/{mission_id}/tasks")
    task_ids = [t["id"] for t in (t_list.get("tasks", []) if isinstance(t_list, dict) else t_list)]
    print(f"Discovered Task IDs for {mission_id}:", task_ids)
    if not task_ids:
        task_ids = ["TASK-001", "TASK-002", "TASK-003"]
    t1, t2, t3 = task_ids[0], task_ids[1], task_ids[2]

    # 3a. Start first task with agent claude-code
    status, res = http_req(
        f"/api/missions/{mission_id}/tasks/{t1}/status",
        method="POST",
        data={"status": "IN_PROGRESS", "agent_id": "claude-code"}
    )
    print(f"{t1} started with claude-code: status={status}")

    # 3b. Fail first task with error signature
    status, res = http_req(
        f"/api/missions/{mission_id}/tasks/{t1}/status",
        method="POST",
        data={"status": "FAILED", "agent_id": "claude-code", "error_signature": "KeyError: 'telemetry_sink'"}
    )
    print(f"{t1} recorded failure: status={status}")

    # 3c. Retry and complete first task
    status, res = http_req(
        f"/api/missions/{mission_id}/tasks/{t1}/status",
        method="POST",
        data={"status": "IN_PROGRESS", "agent_id": "claude-code"}
    )
    status, res = http_req(
        f"/api/missions/{mission_id}/tasks/{t1}/status",
        method="POST",
        data={"status": "COMPLETED", "agent_id": "claude-code", "summary": "Telemetry schema fixed and routing path established"}
    )
    print(f"{t1} completed: status={status}")

    # 3d. Start second task with codex worker and complete
    status, res = http_req(
        f"/api/missions/{mission_id}/tasks/{t2}/status",
        method="POST",
        data={"status": "IN_PROGRESS", "agent_id": "codex_worker"}
    )
    status, res = http_req(
        f"/api/missions/{mission_id}/tasks/{t2}/status",
        method="POST",
        data={"status": "COMPLETED", "agent_id": "codex_worker", "summary": "Cache recovery logic implemented cleanly"}
    )
    print(f"{t2} completed with codex_worker: status={status}")

    # 3e. Verify second task
    status, res = http_req(
        f"/api/missions/{mission_id}/tasks/{t2}/status",
        method="POST",
        data={"status": "VERIFIED", "agent_id": "SUPERVISOR", "metadata": {"tests_passed": True, "ci_passed": True}}
    )
    print(f"{t2} verified by SUPERVISOR: status={status}")

    # Allow async sinks to settle
    time.sleep(3)

    # Run backfill to ensure historical & runtime cross-links are synced
    print("\n=== Step 4: Running Graph Backfill Sync ===")
    status, bf = http_req("/api/graph/backfill", method="POST")
    print("Backfill results:", json.dumps(bf.get("backfilled", {}), indent=2))

    # 5. Query mission subgraph
    print(f"\n=== Step 5: Inspecting Mission Subgraph for {mission_id} ===")
    status, subgraph = http_req(f"/api/missions/{mission_id}/graph")
    print("Status:", status)
    print("Total Nodes in Mission Subgraph:", subgraph.get("nodes_count"))
    print("Total Edges in Mission Subgraph:", subgraph.get("edges_count"))

    node_labels = {}
    for n in subgraph.get("nodes", []):
        lbl = n.get("label", "Unknown")
        node_labels[lbl] = node_labels.get(lbl, 0) + 1
    print("\nNode Counts by Label in Subgraph:")
    for lbl, count in node_labels.items():
        print(f"  {lbl}: {count}")

    edge_types = {}
    for e in subgraph.get("edges", []):
        etype = e.get("type", "Unknown")
        edge_types[etype] = edge_types.get(etype, 0) + 1
    print("\nRelationship Counts by Type in Subgraph:")
    for etype, count in edge_types.items():
        print(f"  {etype}: {count}")

    # 6. Query entire cloud graph stats and run Cypher inspection
    print("\n=== Step 6: Live FalkorDB Cloud Cypher Verification ===")
    _, stats = http_req("/api/graph/stats")
    print("Live Cloud Graph Overall Stats:")
    print(f"  Connected: {stats.get('connected')}")
    print(f"  Host: {stats.get('host')}:{stats.get('port')}")
    print(f"  Total Nodes: {stats.get('nodes_count')}")
    print(f"  Total Relationships: {stats.get('relationships_count')}")
    print("  Labels breakdown:", stats.get("labels"))
    print("  Relationship breakdown:", stats.get("relationship_types"))

    # 7. Execute explicit Cypher paths query
    status, cypher_paths = http_req(
        "/api/graph/query",
        method="POST",
        data={
            "query": """
            MATCH (n)-[r]->(m)
            RETURN labels(n)[0] AS source_label, type(r) AS rel_type, labels(m)[0] AS target_label, count(r) AS count
            ORDER BY count DESC
            """
        }
    )
    print("\nLive Connected Graph Schema Patterns (Source -[:REL]-> Target):")
    for row in cypher_paths.get("rows", []):
        print(f"  ({row[0]}) -[:{row[1]}]-> ({row[2]}): {row[3]} relationships")

if __name__ == "__main__":
    main()
