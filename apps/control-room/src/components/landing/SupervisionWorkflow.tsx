import React, { useState } from 'react';
import { 
  Target, 
  Layers, 
  GitBranch, 
  Activity, 
  ShieldCheck,
  Network
} from 'lucide-react';

interface PipelineStage {
  id: string;
  number: string;
  name: string;
  subtitle: string;
  icon: React.ElementType;
  policy: string;
  governanceDetail: string;
  codeSnippet: string;
  badge: string;
}

const PIPELINE_STAGES: PipelineStage[] = [
  {
    id: 'ingest',
    number: '01',
    name: 'Intent Grounding',
    subtitle: 'Human language in, strict invariants out',
    icon: Target,
    policy: 'INVARIANT SPECIFICATION POLICY',
    governanceDetail: 'The operator states high-level goals. AI Supervisor parses natural language into explicit boundaries, immutable invariants, and target worktree scopes before any agent touches code.',
    codeSnippet: `// 1. Mission Declaration Schema
POST /api/missions/draft
{
  "goal": "Migrate session tokens to Ed25519 asymmetric signatures",
  "repository": "/workspace/core-service",
  "invariants": [
    "Zero API breakage on public /v1/auth contracts",
    "Max allowed cost: $8.00 USD",
    "Boundary scope: ['src/auth/**', 'tests/test_auth.py']"
  ],
  "verification_suite": "pytest tests/test_auth.py -v"
}`,
    badge: 'Scope Bounded'
  },
  {
    id: 'dag',
    number: '02',
    name: 'DAG Partitioning',
    subtitle: 'Isolated tasks in ephemeral worktrees',
    icon: Layers,
    policy: 'WORKTREE ISOLATION POLICY',
    governanceDetail: 'Complex missions are decomposed into a Directed Acyclic Graph (DAG). Each task is assigned an isolated Git worktree so concurrent workers cannot corrupt shared files.',
    codeSnippet: `// 2. Supervisory DAG Decomposition
DAG Plan: [AuthRefactor-v2]
├─ Task 01: Implement Ed25519 signer utility [crypto.py]
│  └─ Isolation: .supervisor/worktrees/task-1 (HEAD: a8f12)
├─ Task 02: Database schema migration [004_keys.sql]
│  └─ Isolation: .supervisor/worktrees/task-2 (HEAD: a8f12)
└─ Task 03: FastToken middleware integration [auth.py]
   └─ DependsOn: [Task 01, Task 02] (Merged verification)`,
    badge: 'Zero Worktree Leak'
  },
  {
    id: 'routing',
    number: '03',
    name: 'Fleet Dispatch',
    subtitle: 'Optimal agent runtime matching',
    icon: GitBranch,
    policy: 'ADAPTER ARBITRATION POLICY',
    governanceDetail: 'Tasks are dispatched to verified agent adapters based on task complexity, context length, and model strengths: Claude Code for deep refactors, Codex for targeted fixes, or local Qwen for offline workloads.',
    codeSnippet: `// 3. Adapter Dispatch & Worktree Mounting
Target Task: Task 01 (Ed25519 Crypto Signer)
Selected Adapter: ClaudeCodeAdapter (Sonnet 3.7)
Mount Mode: LOCAL_SUBPROCESS (Isolated Worktree)
Fallback Adapter: CodexAdapter (OpenAI Responses)
Shared Memory Synced:
  - 14 disproven approach signatures loaded
  - Project coding standards loaded from SQLite`,
    badge: 'Universal Protocol'
  },
  {
    id: 'watchdog',
    number: '04',
    name: 'Watchdog Telemetry',
    subtitle: 'Real-time AST checks and circuit breakers',
    icon: Activity,
    policy: 'CIRCUIT BREAKER EXECUTION POLICY',
    governanceDetail: 'Supervisory watchdogs intercept stdout, AST diffs, and tool execution after every single step. If an agent loops twice on identical errors or touches unauthorized files, execution is immediately halted.',
    codeSnippet: `// 4. Live Watchdog Telemetry Stream
[14:42:01] claude_code -> ToolCall: EditFile("src/auth/crypto.py")
[14:42:02] Watchdog AST Guard: Write within allowed scope [PASS]
[14:42:05] claude_code -> ToolCall: Bash("pytest tests/test_auth.py")
[14:42:07] Watchdog Error Signature Check:
           - Failure signature: NameError("InvalidCurve")
           - Failure count: 1 (Threshold: 2)
[14:42:08] Status: RUNNING (Budget consumed: $0.34)`,
    badge: 'Active Intercept'
  },
  {
    id: 'verify',
    number: '05',
    name: 'Air-Gapped Sandbox',
    subtitle: 'Independent deterministic proof',
    icon: ShieldCheck,
    policy: 'DETERMINISTIC VERIFICATION POLICY',
    governanceDetail: 'Never rely on an agent to self-report success. The supervisor mounts candidate changes into a clean, air-gapped test container and executes the entire validation test suite with zero agent access.',
    codeSnippet: `// 5. Independent Verification Report
Sandbox Environment: Ephemeral Docker Runner (Clean Branch)
AST Diff Invariance: 0 unauthorized mutations
Test Execution:
  ✓ tests/test_auth.py::test_keygen (0.04s)
  ✓ tests/test_auth.py::test_ed25519_signature (0.08s)
  ✓ tests/test_auth.py::test_backward_compat (0.05s)
Result: 18 passed in 1.42s
Verdict: VERIFIED (Ready for operator merge)`,
    badge: '100% Deterministic'
  },
  {
    id: 'falkordb',
    number: '06',
    name: 'FalkorDB Provenance',
    subtitle: 'Temporal Property Graph Memory & Lineage',
    icon: Network,
    policy: 'GRAPH LINEAGE & CROSS-SESSION RECALL',
    governanceDetail: 'Every invariant, subtask assignment, agent tool call, error signature, intervention, and verified output is immutably indexed in FalkorDB Property Graph. Multi-hop Cypher queries trace failure causality and retrieve disproven approach signatures in sub-millisecond latencies.',
    codeSnippet: `// 6. FalkorDB Temporal Causal Lineage Query
MATCH (m:Mission {id: "msn_a4ff348e"})-[:HAS_TASK]->(t:Task)
MATCH (t)-[:HAS_ATTEMPT]->(att:ExecutionAttempt)
OPTIONAL MATCH (att)-[:FAILED_WITH]->(f:FailureSignature)
OPTIONAL MATCH (att)-[:PRODUCED]->(art:Artifact)
RETURN t.title, att.status, f.failure_class, count(art) AS artifacts
ORDER BY att.attempt_number ASC

// Result: 41 nodes, 69 relationships traversed (2.1ms)`,
    badge: 'FalkorDB Powered'
  }
];

export const SupervisionWorkflow: React.FC = () => {
  const [selectedStageId, setSelectedStageId] = useState<string>('watchdog');

  const selectedStage = PIPELINE_STAGES.find(s => s.id === selectedStageId) || PIPELINE_STAGES[3];

  return (
    <section id="how-it-works" className="as-editorial-section as-workflow-section">
      <div className="as-container">
        {/* Section Header */}
        <div className="as-editorial-header">
          <div className="as-mono-tag">
            <span>[ ARCHITECTURAL SPECIFICATION // THE SUPERVISORY PIPELINE ]</span>
          </div>
          <h2 className="as-editorial-title">
            How Supervision Works
          </h2>
          <p className="as-editorial-sub">
            From natural language instruction to cryptographically verified code. A continuous governance pipeline providing structural oversight at every stage.
          </p>
        </div>

        {/* Continuous Horizontal Connected Pipeline Line */}
        <div className="as-pipeline-track-wrapper">
          <div className="as-pipeline-track">
            {/* Pulsing Connected Background Line */}
            <div className="as-pipeline-line">
              <div className="as-pipeline-line-pulse" />
            </div>

            {/* Pipeline Stage Milestone Nodes */}
            <div className="as-pipeline-milestones">
              {PIPELINE_STAGES.map((stage) => {
                const Icon = stage.icon;
                const isCurrent = stage.id === selectedStageId;
                return (
                  <div
                    key={stage.id}
                    className={`as-pipeline-node ${isCurrent ? 'active' : ''}`}
                    onClick={() => setSelectedStageId(stage.id)}
                    role="button"
                    tabIndex={0}
                  >
                    <div className="as-node-dot">
                      <Icon size={16} />
                    </div>
                    <div className="as-node-info">
                      <span className="as-node-num">{stage.number}</span>
                      <span className="as-node-name">{stage.name}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Interactive Workbench Inspector for Active Stage */}
        <div className="as-workbench-card">
          <div className="as-workbench-topbar">
            <div className="as-workbench-heading">
              <span className="as-workbench-step">PHASE {selectedStage.number}</span>
              <span className="as-workbench-title">{selectedStage.name}</span>
              <span className="as-workbench-pill">{selectedStage.badge}</span>
            </div>
            <div className="as-workbench-policy">
              <span>POLICY: {selectedStage.policy}</span>
            </div>
          </div>

          <div className="as-workbench-body">
            {/* Left: Detailed Governance Narrative */}
            <div className="as-workbench-narrative">
              <h3 className="as-narrative-subheading">{selectedStage.subtitle}</h3>
              <p className="as-narrative-description">
                {selectedStage.governanceDetail}
              </p>
              
              <div className="as-workbench-metrics">
                <div className="as-metric-item">
                  <span className="as-metric-key">Invariant Level:</span>
                  <span className="as-metric-val">Strict Enforcement</span>
                </div>
                <div className="as-metric-item">
                  <span className="as-metric-key">Rollback Latency:</span>
                  <span className="as-metric-val">&lt; 150ms</span>
                </div>
                <div className="as-metric-item">
                  <span className="as-metric-key">Self-Grading:</span>
                  <span className="as-metric-val prohibited">PROHIBITED</span>
                </div>
              </div>

              <div className="as-stage-stepper">
                {PIPELINE_STAGES.map((s) => (
                  <button
                    key={s.id}
                    className={`as-stepper-btn ${s.id === selectedStageId ? 'active' : ''}`}
                    onClick={() => setSelectedStageId(s.id)}
                  >
                    {s.number}. {s.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Right: Authentic Telemetry & Schema Terminal */}
            <div className="as-workbench-terminal">
              <div className="as-terminal-bar">
                <div className="as-terminal-dots">
                  <span className="as-dot red" />
                  <span className="as-dot yellow" />
                  <span className="as-dot green" />
                </div>
                <span className="as-terminal-title">pipeline_inspector // {selectedStage.id}.telemetry</span>
                <span className="as-terminal-status">AUTHORITATIVE</span>
              </div>
              <pre className="as-terminal-code">
                <code>{selectedStage.codeSnippet}</code>
              </pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
