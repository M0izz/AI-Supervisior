# Structured Project Memory & Provenance

## Provenance Model
Unsupervised LLM memory often leads to progressive hallucinations. In the AI Work Supervisor, all memory entries have explicit **provenance**:

```json
{
  "fact_id": "fact_019",
  "fact": "PostgreSQL database primary key is user_id",
  "source": "test_schema_check",
  "created_by": "verifier_01",
  "confidence": 0.99,
  "status": "VERIFIED",
  "created_at": "2026-09-30T18:40:22Z"
}
```

### Fact Status Categories
- `OBSERVED`: Raw empirical observations (e.g. error output, test run).
- `INFERRED`: Derived hypotheses from analysis.
- `DECIDED`: Architectural or policy choices made during execution.
- `VERIFIED`: Proven by independent tests and static checks.
- `REJECTED`: Disproven approaches logged to prevent repeating mistakes.
- `STALE`: Outdated facts superseded by recent repository changes.

## Agent Context Package
Instead of dumping full conversation logs, agents receive a curated package:
```json
{
  "mission_id": "msn_001",
  "objective": "Add CSV import validation",
  "task": {
    "task_id": "task_003",
    "title": "Implement CSV parser"
  },
  "constraints": [
    "Do not modify database schema",
    "Use existing validation library"
  ],
  "relevant_memory": [
    { "fact": "CSV header format requires UTF-8 normalization", "status": "VERIFIED" }
  ],
  "rejected_approaches": [
    { "approach": "Direct string header comparison", "reason": "Fails with UTF-8 BOM" }
  ],
  "recent_events": [ ... ],
  "previous_attempts": [ ... ]
}
```
