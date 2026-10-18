import React, { useState, useEffect, useMemo } from 'react';
import { 
  Network, 
  Database, 
  Activity, 
  Terminal, 
  Cpu, 
  ShieldCheck, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw, 
  Copy, 
  Check, 
  Search, 
  Layers, 
  GitBranch, 
  Code, 
  Sparkles, 
  Clock, 
  Play
} from 'lucide-react';
import type { 
  Mission, 
  GraphHealth, 
  GraphStats, 
  GraphActivityEvent, 
  SafeQueryResult, 
  SupervisorDecision 
} from '../types';
import { 
  getGraphHealth, 
  getGraphStats, 
  getGraphActivity, 
  executeGraphQuery,
  getSupervisorDecisions
} from '../api';
import { FalkorGraphInspector } from '../components/FalkorGraphInspector';

interface FalkorDBWorkspaceProps {
  missions: Mission[];
  selectedMissionId: string | null;
  onSelectMission: (missionId: string) => void;
  onSeedDemo: () => void;
  isSeeding?: boolean;
}

type WorkspaceTab = 'overview' | 'explorer' | 'lineage' | 'activity' | 'cypher';

interface CypherTemplate {
  id: string;
  title: string;
  description: string;
  cypher: string;
  defaultParams: Record<string, string>;
  category: 'Causality' | 'Verification' | 'Governance' | 'Topology';
}

const CYPHER_TEMPLATES: CypherTemplate[] = [
  {
    id: 'causal-failure-chain',
    title: '1. Causal Failure Chains (FAILS_WITH)',
    description: 'Retrieves execution attempts linked directly to the causal failure events that triggered supervisor recovery, including diagnostic error signatures.',
    cypher: `MATCH (m:Mission {id: $mission_id})-[:CONTAINS_TASK]->(t:Task)
MATCH (e:Execution {task_id: t.id})-[:FAILS_WITH]->(ev:ExecutionEvent)
RETURN t.id AS task_id, e.id AS execution_id, e.attempt_number AS attempt, ev.event_type AS failure_type, ev.payload_json AS diagnostics
ORDER BY e.attempt_number DESC`,
    defaultParams: { mission_id: '' },
    category: 'Causality'
  },
  {
    id: 'empirical-prereq-gate',
    title: '2. Empirical Prerequisite Verification Gate (DEPENDS_ON + EVALUATES)',
    description: 'Enforces the graph invariant: predecessor tasks cannot be merely marked completed; they must possess an accepted independent Verification node in FalkorDB.',
    cypher: `MATCH (t:Task {mission_id: $mission_id})-[:DEPENDS_ON]->(dep:Task)
OPTIONAL MATCH (v:Verification {decision: 'ACCEPT'})-[:EVALUATES]->(dep)
RETURN t.id AS waiting_task, dep.id AS prerequisite_id, dep.title AS prerequisite_title, dep.status AS dep_status, (v IS NOT NULL) AS is_empirically_verified`,
    defaultParams: { mission_id: '' },
    category: 'Verification'
  },
  {
    id: 'decision-lineage',
    title: '3. Supervisory Recovery Decision Lineage (RESPONDS_TO + SELECTS)',
    description: 'Traces supervisor decisions back to the causal failure event that triggered them and the replacement agent runtime selected for recovery.',
    cypher: `MATCH (d:Decision {mission_id: $mission_id})
OPTIONAL MATCH (d)-[:RESPONDS_TO]->(ev:ExecutionEvent)
OPTIONAL MATCH (d)-[:SELECTS]->(a:Agent)
RETURN d.id AS decision_id, d.decision_type AS type, d.action AS action, d.reason AS rationale, a.id AS selected_agent, ev.event_type AS triggered_by
ORDER BY d.timestamp DESC`,
    defaultParams: { mission_id: '' },
    category: 'Governance'
  },
  {
    id: 'context-handoff-graph',
    title: '4. Context Handoff Between Agents (TRANSFERS_CONTEXT)',
    description: 'Inspects handoff nodes that transfer execution context, diagnostic state, and rejected approaches between different model runtimes.',
    cypher: `MATCH (h:Handoff {mission_id: $mission_id})-[:TRANSFERS_CONTEXT]->(t:Task)
RETURN h.id AS handoff_id, h.source_agent AS from_agent, h.target_agent AS to_agent, h.trigger AS trigger, h.context_summary AS context, t.title AS task_title
ORDER BY h.timestamp DESC`,
    defaultParams: { mission_id: '' },
    category: 'Causality'
  },
  {
    id: 'evidence-proof-lineage',
    title: '5. Empirical Evidence Proof Lineage (SUPPORTED_BY)',
    description: 'Verifies the chain of evidence supporting a task acceptance: unit test outputs, AST checks, exit codes, and immutable verification assertions.',
    cypher: `MATCH (v:Verification)-[:SUPPORTED_BY]->(ev:Evidence)
WHERE v.mission_id = $mission_id
RETURN v.id AS verification_id, v.task_id AS task_id, v.decision AS decision, ev.evidence_type AS evidence_type, ev.description AS proof, ev.passed AS passed`,
    defaultParams: { mission_id: '' },
    category: 'Verification'
  },
  {
    id: 'mission-topology-summary',
    title: '6. Full Mission Graph Topology Breakdown',
    description: 'Counts all connected nodes grouped by label and outgoing relationship type for a high-level graph audit.',
    cypher: `MATCH (m:Mission {id: $mission_id})-[r]->(target)
RETURN labels(target)[0] AS node_type, type(r) AS relationship, count(target) AS total_nodes
ORDER BY total_nodes DESC`,
    defaultParams: { mission_id: '' },
    category: 'Topology'
  }
];

export const FalkorDBWorkspace: React.FC<FalkorDBWorkspaceProps> = ({
  missions,
  selectedMissionId,
  onSelectMission,
  onSeedDemo,
  isSeeding = false
}) => {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('overview');
  const [graphHealth, setGraphHealth] = useState<GraphHealth | null>(null);
  const [graphStats, setGraphStats] = useState<GraphStats | null>(null);
  const [activityEvents, setActivityEvents] = useState<GraphActivityEvent[]>([]);
  const [decisions, setDecisions] = useState<SupervisorDecision[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [copiedText, setCopiedText] = useState<string | null>(null);

  // Cypher Sandbox state
  const [selectedTemplate, setSelectedTemplate] = useState<CypherTemplate>(CYPHER_TEMPLATES[0]);
  const [activeCypherQuery, setActiveCypherQuery] = useState<string>(CYPHER_TEMPLATES[0].cypher);
  const [queryParams, setQueryParams] = useState<Record<string, string>>({
    mission_id: selectedMissionId || (missions[0]?.id || '')
  });
  const [queryResult, setQueryResult] = useState<SafeQueryResult | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [isQuerying, setIsQuerying] = useState<boolean>(false);

  // Activity filter state
  const [activityFilter, setActivityFilter] = useState<string>('ALL');
  const [activitySearch, setActivitySearch] = useState<string>('');

  // Keep active mission in sync with params
  const effectiveMissionId = selectedMissionId || (missions[0]?.id || '');

  const copyToClipboard = (text: string, label: string = text) => {
    navigator.clipboard.writeText(text);
    setCopiedText(label);
    setTimeout(() => setCopiedText(null), 2000);
  };

  const loadGraphData = async () => {
    setIsLoading(true);
    try {
      const [h, s, act] = await Promise.all([
        getGraphHealth().catch(() => null),
        getGraphStats().catch(() => null),
        getGraphActivity(40).catch(() => ({ events: [], count: 0 }))
      ]);
      setGraphHealth(h);
      setGraphStats(s);
      setActivityEvents(act?.events || []);

      if (effectiveMissionId) {
        getSupervisorDecisions(effectiveMissionId)
          .then(res => setDecisions(res?.decisions || []))
          .catch(() => setDecisions([]));
      }
    } catch (err) {
      console.error('Failed to load FalkorDB data', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadGraphData();
    const interval = setInterval(loadGraphData, 10000);
    return () => clearInterval(interval);
  }, [effectiveMissionId]);

  useEffect(() => {
    if (effectiveMissionId) {
      setQueryParams(prev => ({ ...prev, mission_id: effectiveMissionId }));
    }
  }, [effectiveMissionId]);

  const handleSelectTemplate = (tpl: CypherTemplate) => {
    setSelectedTemplate(tpl);
    setActiveCypherQuery(tpl.cypher);
    setQueryResult(null);
    setQueryError(null);
  };

  const handleRunQuery = async () => {
    setIsQuerying(true);
    setQueryError(null);
    setQueryResult(null);
    try {
      // Substitute or pass parameters cleanly
      const cleanParams: Record<string, any> = { ...queryParams };
      if (!cleanParams.mission_id && effectiveMissionId) {
        cleanParams.mission_id = effectiveMissionId;
      }
      const res = await executeGraphQuery(activeCypherQuery, cleanParams);
      setQueryResult(res);
    } catch (err: any) {
      setQueryError(err?.message || 'Query execution failed');
    } finally {
      setIsQuerying(false);
    }
  };

  const filteredActivity = useMemo(() => {
    return activityEvents.filter(ev => {
      if (activityFilter !== 'ALL' && ev.operation_type !== activityFilter) {
        return false;
      }
      if (activitySearch.trim()) {
        const q = activitySearch.toLowerCase();
        return (
          ev.description?.toLowerCase().includes(q) ||
          ev.operation_type?.toLowerCase().includes(q) ||
          ev.mission_id?.toLowerCase().includes(q) ||
          ev.task_id?.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [activityEvents, activityFilter, activitySearch]);

  const isConnected = graphHealth?.connected ?? false;

  return (
    <div className="falkordb-workspace" style={{ padding: '24px 32px', maxWidth: '1440px', margin: '0 auto' }}>
      {/* 1. Header Section */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: 'rgba(56, 189, 248, 0.12)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#38bdf8'
            }}>
              <Network size={18} />
            </div>
            <h1 style={{ fontSize: '22px', fontWeight: 700, margin: 0, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              FalkorDB Graph Memory
            </h1>
            <span style={{
              fontSize: '11px',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: '12px',
              backgroundColor: isConnected ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
              color: isConnected ? '#10b981' : '#ef4444',
              border: `1px solid ${isConnected ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
              display: 'flex',
              alignItems: 'center',
              gap: '5px'
            }}>
              <span style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: isConnected ? '#10b981' : '#ef4444'
              }} />
              {isConnected ? 'FalkorDB Connected' : 'FalkorDB Offline'}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: '13.5px', color: 'var(--text-secondary)' }}>
            Explore the context, relationships and decisions that power AI Supervisor.
          </p>
        </div>

        {/* Global Quick Action Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            onClick={loadGraphData}
            className="btn btn-secondary btn-sm"
            disabled={isLoading}
            title="Refresh graph health & vitals"
          >
            <RefreshCw size={13} className={isLoading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>

          <button
            onClick={onSeedDemo}
            className="btn btn-primary btn-sm"
            disabled={isSeeding}
            title="Populate graph with realistic authentication recovery mission"
          >
            <Sparkles size={13} />
            <span>{isSeeding ? 'Seeding Graph...' : 'Seed Demo Scenario'}</span>
          </button>
        </div>
      </div>

      {/* 2. Top-Level Mission Selector Bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        backgroundColor: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        marginBottom: '20px',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Mission Context:
          </span>
          {missions.length > 0 ? (
            <select
              value={effectiveMissionId}
              onChange={(e) => onSelectMission(e.target.value)}
              style={{
                backgroundColor: 'var(--bg)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                padding: '6px 12px',
                fontSize: '13px',
                fontWeight: 500,
                outline: 'none',
                minWidth: '260px'
              }}
            >
              {missions.map(m => (
                <option key={m.id} value={m.id}>
                  {m.title} ({m.id}) — {m.status}
                </option>
              ))}
            </select>
          ) : (
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              No active missions found. Click "Seed Demo Scenario" to populate the property graph.
            </span>
          )}
        </div>

        {/* Live Vitals Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            backgroundColor: 'rgba(59, 130, 246, 0.08)',
            border: '1px solid rgba(59, 130, 246, 0.2)',
            borderRadius: '6px',
            color: 'var(--text-secondary)'
          }}>
            <Database size={13} color="#3b82f6" />
            <span>Graph:</span>
            <strong style={{ color: 'var(--text-primary)' }}>{graphHealth?.graph_name || 'ai_supervisor_memory'}</strong>
          </div>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            backgroundColor: 'rgba(16, 185, 129, 0.08)',
            border: '1px solid rgba(16, 185, 129, 0.2)',
            borderRadius: '6px',
            color: 'var(--text-secondary)'
          }}>
            <span>Nodes:</span>
            <strong style={{ color: '#10b981' }}>{graphHealth?.nodes_count ?? graphStats?.nodes_count ?? 0}</strong>
            <span style={{ color: 'var(--border)' }}>•</span>
            <span>Edges:</span>
            <strong style={{ color: '#10b981' }}>{graphHealth?.relationships_count ?? graphStats?.relationships_count ?? 0}</strong>
          </div>

          {isConnected && graphHealth?.latency_ms !== undefined && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '4px 8px',
              borderRadius: '6px',
              backgroundColor: 'var(--bg)',
              border: '1px solid var(--border)',
              color: 'var(--text-muted)'
            }}>
              <Clock size={12} />
              <span>{Math.round(graphHealth.latency_ms)}ms</span>
            </div>
          )}
        </div>
      </div>

      {/* 3. Section Navigation Tabs */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        borderBottom: '1px solid var(--border)',
        marginBottom: '24px'
      }}>
        {[
          { id: 'overview', label: 'Overview & Health', icon: Activity },
          { id: 'explorer', label: 'Graph Explorer', icon: Network },
          { id: 'lineage', label: 'Execution & Decisions', icon: GitBranch },
          { id: 'activity', label: 'Graph Activity', icon: Terminal },
          { id: 'cypher', label: 'Cypher & Memory', icon: Code }
        ].map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as WorkspaceTab)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 16px',
                fontSize: '13px',
                fontWeight: isActive ? 600 : 500,
                color: isActive ? '#38bdf8' : 'var(--text-secondary)',
                backgroundColor: 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid #38bdf8' : '2px solid transparent',
                cursor: 'pointer',
                marginBottom: '-1px',
                transition: 'all 0.15s ease'
              }}
            >
              <Icon size={15} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* 4. Tab Content Panels */}

      {/* TAB 1: OVERVIEW & HEALTH */}
      {activeTab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Disconnected Error Alert if Offline */}
          {!isConnected && (
            <div style={{
              padding: '18px 20px',
              borderRadius: '8px',
              backgroundColor: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '14px'
            }}>
              <AlertTriangle size={20} color="#ef4444" style={{ marginTop: '2px', flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '14px', fontWeight: 600, color: '#ef4444', marginBottom: '4px' }}>
                  FalkorDB Graph Memory Offline (localhost:6379)
                </div>
                <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px', lineHeight: '1.5' }}>
                  {graphHealth?.error || 'Target machine actively refused connection on port 6379.'}
                  <br />
                  FalkorDB serves as AI Supervisor's persistent property graph store for causal failure chains, prerequisite verification gates, and supervisory decision lineage.
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <div style={{
                    backgroundColor: 'rgba(0, 0, 0, 0.4)',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                    color: '#e2e8f0',
                    border: '1px solid rgba(255, 255, 255, 0.1)'
                  }}>
                    docker run -p 6379:6379 -it --rm falkordb/falkordb
                  </div>
                  <button
                    onClick={() => copyToClipboard('docker run -p 6379:6379 -it --rm falkordb/falkordb', 'docker')}
                    className="btn btn-secondary btn-sm"
                  >
                    {copiedText === 'docker' ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
                    <span>{copiedText === 'docker' ? 'Copied Command' : 'Copy Docker Command'}</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Vitals Grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '16px'
          }}>
            <div className="card" style={{ padding: '16px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>Connection State</div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: isConnected ? '#10b981' : '#ef4444' }}>
                {isConnected ? 'Active & Ready' : 'Offline / Refused'}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                Host: {graphHealth?.host || 'localhost'}:{graphHealth?.port || 6379}
              </div>
            </div>

            <div className="card" style={{ padding: '16px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>Property Graph Name</div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: '#38bdf8' }}>
                {graphHealth?.graph_name || 'ai_supervisor_memory'}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                Isolated mission namespace
              </div>
            </div>

            <div className="card" style={{ padding: '16px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>Stored Nodes</div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {graphHealth?.nodes_count ?? graphStats?.nodes_count ?? 0}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                Missions, Tasks, Executions, Decisions
              </div>
            </div>

            <div className="card" style={{ padding: '16px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>Relationships (Edges)</div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {graphHealth?.relationships_count ?? graphStats?.relationships_count ?? 0}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                FAILS_WITH, DEPENDS_ON, EVALUATES
              </div>
            </div>
          </div>

          {/* Node Labels Breakdown */}
          <div className="card" style={{ padding: '20px' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, margin: '0 0 16px 0', color: 'var(--text-primary)' }}>
              FalkorDB Node Schema & Live Entity Counts
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
              {[
                { label: 'Mission', desc: 'Root mission records & objectives', icon: Sparkles, color: '#38bdf8' },
                { label: 'Task', desc: 'Task DAG nodes & file bounds', icon: Layers, color: '#06b6d4' },
                { label: 'Execution', desc: 'Attempt numbers & runtimes', icon: Terminal, color: '#818cf8' },
                { label: 'ExecutionEvent', desc: 'Causal failures & error dumps', icon: AlertTriangle, color: '#ef4444' },
                { label: 'Decision', desc: 'Supervisor recovery rationales', icon: Cpu, color: '#a855f7' },
                { label: 'Handoff', desc: 'Context transfers between models', icon: GitBranch, color: '#f59e0b' },
                { label: 'Verification', desc: 'Independent test evaluations', icon: ShieldCheck, color: '#10b981' },
                { label: 'Evidence', desc: 'Test proofs, AST & exit codes', icon: CheckCircle2, color: '#14b8a6' }
              ].map(item => {
                const count = graphStats?.labels?.[item.label] ?? 0;
                const Icon = item.icon;
                return (
                  <div
                    key={item.label}
                    style={{
                      padding: '12px',
                      borderRadius: '6px',
                      backgroundColor: 'var(--bg)',
                      border: '1px solid var(--border)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px'
                    }}
                  >
                    <div style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '6px',
                      backgroundColor: `${item.color}15`,
                      border: `1px solid ${item.color}35`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: item.color
                    }}>
                      <Icon size={14} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{item.label}</strong>
                        <span style={{ fontSize: '12px', fontWeight: 600, color: count > 0 ? item.color : 'var(--text-muted)' }}>
                          {count}
                        </span>
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.desc}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Core Traceability Invariants Card */}
          <div className="card" style={{ padding: '20px' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, margin: '0 0 12px 0', color: 'var(--text-primary)' }}>
              Core Graph Traceability Invariants Enforced in Cypher
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
              <div style={{ padding: '14px', borderRadius: '6px', backgroundColor: 'var(--bg)', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#ef4444', marginBottom: '6px' }}>
                  1. Failure Causality (FAILS_WITH)
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
                  Execution attempts are linked directly to the causal failure event explaining the crash, preventing generic latest-event assumptions.
                </div>
              </div>

              <div style={{ padding: '14px', borderRadius: '6px', backgroundColor: 'var(--bg)', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#10b981', marginBottom: '6px' }}>
                  2. Empirical Prerequisite Gate (DEPENDS_ON)
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
                  Downstream task dispatch is blocked unless predecessor tasks have an accepted Verification node in FalkorDB with empirical proof.
                </div>
              </div>

              <div style={{ padding: '14px', borderRadius: '6px', backgroundColor: 'var(--bg)', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#a855f7', marginBottom: '6px' }}>
                  3. Supervisory Decision Lineage (RESPONDS_TO)
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
                  Recovery actions trace back to both the failure signature and the alternative model selected, preserving context across retries.
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: GRAPH EXPLORER */}
      {activeTab === 'explorer' && (
        <div>
          {effectiveMissionId ? (
            <FalkorGraphInspector missionId={effectiveMissionId} />
          ) : (
            <div className="card" style={{ padding: '40px', textAlign: 'center' }}>
              <Network size={36} color="var(--text-muted)" style={{ margin: '0 auto 12px auto' }} />
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>No Mission Selected</h3>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '16px' }}>
                Please create a mission or run the demo scenario to generate a queryable graph.
              </p>
              <button onClick={onSeedDemo} className="btn btn-primary" disabled={isSeeding}>
                <Sparkles size={14} />
                <span>Run Demo Scenario</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: EXECUTION & DECISIONS */}
      {activeTab === 'lineage' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ padding: '20px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, margin: '0 0 6px 0', color: 'var(--text-primary)' }}>
              Execution Attempts, Failures & Recovery Decisions
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '0 0 16px 0' }}>
              Graph-driven lineage tracing failed attempts through causal events, supervisor interventions, model handoffs, and verification.
            </p>

            {decisions.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {decisions.map((dec, idx) => (
                  <div
                    key={dec.id || idx}
                    style={{
                      padding: '16px',
                      borderRadius: '8px',
                      backgroundColor: 'var(--bg)',
                      border: '1px solid var(--border)'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '11px',
                          fontWeight: 600,
                          backgroundColor: 'rgba(168, 85, 247, 0.15)',
                          color: '#c084fc',
                          border: '1px solid rgba(168, 85, 247, 0.3)'
                        }}>
                          {dec.decision_type || 'SUPERVISORY_DECISION'}
                        </span>
                        <strong style={{ fontSize: '14px', color: 'var(--text-primary)' }}>
                          {dec.action || dec.title || 'Intervention'}
                        </strong>
                      </div>
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {dec.timestamp ? new Date(dec.timestamp).toLocaleTimeString() : ''}
                      </span>
                    </div>

                    <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px', lineHeight: '1.5' }}>
                      {dec.why || (dec as any).reason || 'Supervisor evaluated execution graph and applied recovery strategy.'}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '12px', color: 'var(--text-muted)' }}>
                      <span>Context: <strong>{(dec as any).task_id || dec.title || 'Global'}</strong></span>
                      {dec.target_agent && <span>Target Agent: <strong>{dec.target_agent}</strong></span>}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                No recovery decisions recorded for mission <strong>{effectiveMissionId || 'None'}</strong>.
                <br />
                Seed the demo scenario to observe an intentional failure, circuit breaker trip, and supervisor model handoff.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: GRAPH ACTIVITY */}
      {activeTab === 'activity' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Search size={14} color="var(--text-muted)" />
              <input
                type="text"
                placeholder="Search graph operations or entity IDs..."
                value={activitySearch}
                onChange={(e) => setActivitySearch(e.target.value)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  backgroundColor: 'var(--card-bg)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontSize: '13px',
                  outline: 'none',
                  minWidth: '260px'
                }}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              {['ALL', 'Mission', 'Task', 'Execution', 'Decision', 'Verification'].map(filter => (
                <button
                  key={filter}
                  onClick={() => setActivityFilter(filter)}
                  style={{
                    padding: '4px 10px',
                    fontSize: '12px',
                    borderRadius: '6px',
                    border: '1px solid var(--border)',
                    backgroundColor: activityFilter === filter ? 'rgba(56, 189, 248, 0.15)' : 'var(--card-bg)',
                    color: activityFilter === filter ? '#38bdf8' : 'var(--text-secondary)',
                    fontWeight: activityFilter === filter ? 600 : 500,
                    cursor: 'pointer'
                  }}
                >
                  {filter}
                </button>
              ))}
            </div>
          </div>

          <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--bg)', borderBottom: '1px solid var(--border)', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  <th style={{ padding: '10px 16px' }}>Type</th>
                  <th style={{ padding: '10px 16px' }}>Operation Description</th>
                  <th style={{ padding: '10px 16px' }}>Target ID</th>
                  <th style={{ padding: '10px 16px' }}>Timestamp</th>
                  <th style={{ padding: '10px 16px' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredActivity.length > 0 ? (
                  filteredActivity.map((ev, i) => (
                    <tr key={ev.id || i} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '12px 16px' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '11px',
                          fontWeight: 600,
                          backgroundColor: 'rgba(56, 189, 248, 0.1)',
                          color: '#38bdf8'
                        }}>
                          {ev.operation_type}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', color: 'var(--text-primary)' }}>
                        {ev.description}
                      </td>
                      <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontSize: '12px', color: 'var(--text-muted)' }}>
                        {ev.task_id || ev.mission_id || ev.id}
                      </td>
                      <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: '12px', whiteSpace: 'nowrap' }}>
                        {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          color: '#10b981',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}>
                          <CheckCircle2 size={12} />
                          {ev.status || 'RECORDED'}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No graph activity recorded matching your filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 5: CYPHER & MEMORY */}
      {activeTab === 'cypher' && (
        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '20px', alignItems: 'flex-start' }}>
          {/* Query Templates Sidebar */}
          <div className="card" style={{ padding: '16px' }}>
            <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '0 0 12px 0' }}>
              Standard Parameterized Cypher Queries
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {CYPHER_TEMPLATES.map(tpl => {
                const isSelected = selectedTemplate.id === tpl.id;
                return (
                  <button
                    key={tpl.id}
                    onClick={() => handleSelectTemplate(tpl)}
                    style={{
                      textAlign: 'left',
                      padding: '10px 12px',
                      borderRadius: '6px',
                      backgroundColor: isSelected ? 'rgba(56, 189, 248, 0.12)' : 'var(--bg)',
                      border: isSelected ? '1px solid rgba(56, 189, 248, 0.3)' : '1px solid var(--border)',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    <div style={{ fontSize: '12.5px', fontWeight: 600, color: isSelected ? '#38bdf8' : 'var(--text-primary)', marginBottom: '3px' }}>
                      {tpl.title}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                      {tpl.description}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Query Runner & Results */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="card" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Code size={16} color="#38bdf8" />
                  <strong style={{ fontSize: '14px', color: 'var(--text-primary)' }}>
                    {selectedTemplate.title}
                  </strong>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    onClick={() => copyToClipboard(activeCypherQuery, 'cypher')}
                    className="btn btn-secondary btn-sm"
                  >
                    {copiedText === 'cypher' ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
                    <span>{copiedText === 'cypher' ? 'Copied Cypher' : 'Copy Cypher'}</span>
                  </button>

                  <button
                    onClick={handleRunQuery}
                    className="btn btn-primary btn-sm"
                    disabled={isQuerying || !isConnected}
                    title={isConnected ? 'Execute read-only Cypher query' : 'FalkorDB is offline'}
                  >
                    <Play size={13} />
                    <span>{isQuerying ? 'Executing...' : 'Run Safe Query'}</span>
                  </button>
                </div>
              </div>

              {/* Cypher Code Box */}
              <div style={{
                position: 'relative',
                borderRadius: '6px',
                overflow: 'hidden',
                border: '1px solid var(--border)',
                marginBottom: '16px'
              }}>
                <textarea
                  value={activeCypherQuery}
                  onChange={(e) => setActiveCypherQuery(e.target.value)}
                  rows={6}
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    backgroundColor: 'rgba(15, 23, 42, 0.75)',
                    color: '#38bdf8',
                    fontFamily: 'monospace',
                    fontSize: '12.5px',
                    padding: '12px',
                    border: 'none',
                    outline: 'none',
                    lineHeight: '1.5',
                    resize: 'vertical'
                  }}
                />
              </div>

              {/* Parameter Inputs */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '10px 14px',
                borderRadius: '6px',
                backgroundColor: 'var(--bg)',
                border: '1px solid var(--border)',
                flexWrap: 'wrap'
              }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }}>
                  Parameters:
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>$mission_id:</label>
                  <input
                    type="text"
                    value={queryParams.mission_id || ''}
                    onChange={(e) => setQueryParams({ ...queryParams, mission_id: e.target.value })}
                    placeholder="e.g. msn_18dd82ec"
                    style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      border: '1px solid var(--border)',
                      backgroundColor: 'var(--card-bg)',
                      color: 'var(--text-primary)',
                      fontFamily: 'monospace',
                      fontSize: '12px'
                    }}
                  />
                </div>

                <span style={{ marginLeft: 'auto', fontSize: '11px', color: 'var(--text-muted)' }}>
                  Read-Only • Strictly Sandboxed
                </span>
              </div>
            </div>

            {/* Query Results / Output Panel */}
            {queryError && (
              <div style={{
                padding: '14px 18px',
                borderRadius: '8px',
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                color: '#ef4444',
                fontSize: '13px'
              }}>
                <strong>Query Error:</strong> {queryError}
              </div>
            )}

            {queryResult && (
              <div className="card" style={{ padding: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <strong style={{ fontSize: '13.5px', color: 'var(--text-primary)' }}>
                    Query Results ({queryResult.row_count} rows)
                  </strong>
                  <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                    Execution Time: {queryResult.execution_time_ms}ms
                  </span>
                </div>

                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
                    <thead>
                      <tr style={{ backgroundColor: 'var(--bg)', borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                        {queryResult.columns.map((col, idx) => (
                          <th key={idx} style={{ padding: '8px 12px', fontWeight: 600 }}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {queryResult.rows.map((row, rIdx) => (
                        <tr key={rIdx} style={{ borderBottom: '1px solid var(--border)' }}>
                          {row.map((val, cIdx) => (
                            <td key={cIdx} style={{ padding: '8px 12px', fontFamily: typeof val === 'object' ? 'monospace' : 'inherit' }}>
                              {typeof val === 'object' ? JSON.stringify(val) : String(val ?? '')}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
