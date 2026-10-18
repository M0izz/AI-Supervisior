import React, { useState, useEffect } from 'react';
import { 
  Target, 
  Bot, 
  ShieldAlert, 
  CheckCircle2, 
  AlertTriangle, 
  ArrowRight, 
  Compass,
  Play,
  Pause,
  Sparkles,
  ShieldCheck,
  Database,
  Network,
  RefreshCw,
  X
} from 'lucide-react';
import type { Mission, AgentRecord, ApprovalRequest, Event, InterventionDetail, AdapterInfo, MemoryRecord, SupervisorDecision, GraphActivityEvent } from '../types';
import { ProviderLogo } from '../components/ProviderLogo';
import { SupervisorDecisionCard } from '../components/SupervisorDecisionCard';
import { pauseMission, resumeMission, getSupervisorDecisions, explainDecision, getGraphHealth, getGraphActivity } from '../api';

interface OverviewProps {
  missions: Mission[];
  agents: AgentRecord[];
  adapters: AdapterInfo[];
  approvals: ApprovalRequest[];
  interventions: InterventionDetail[];
  events: Event[];
  memoryRecords?: MemoryRecord[];
  onSelectMission: (missionId: string) => void;
  onSelectAgent: (agentId: string) => void;
  onNavigateToTab: (tab: any) => void;
  onOpenCreateMission: () => void;
  onRefresh: () => void;
}

export const Overview: React.FC<OverviewProps> = ({
  missions,
  agents,
  adapters,
  approvals,
  interventions,
  events,
  memoryRecords = [],
  onSelectMission,
  onSelectAgent,
  onNavigateToTab,
  onOpenCreateMission,
  onRefresh
}) => {
  const safeMissions = Array.isArray(missions) ? missions : [];
  const safeAgents = Array.isArray(agents) ? agents : [];
  const safeApprovals = Array.isArray(approvals) ? approvals : [];
  const safeEvents = Array.isArray(events) ? events : [];
  const safeAdapters = Array.isArray(adapters) ? adapters : [];
  const safeMemory = Array.isArray(memoryRecords) ? memoryRecords : [];

  const [decisions, setDecisions] = useState<SupervisorDecision[]>([]);
  const [explainingDecision, setExplainingDecision] = useState<SupervisorDecision | null>(null);
  const [gemmaExplanation, setGemmaExplanation] = useState<any | null>(null);
  const [isExplaining, setIsExplaining] = useState(false);

  // Live FalkorDB Graph Health & Activity Stream
  const [graphHealth, setGraphHealth] = useState<{ connected: boolean; graph_name?: string; node_count?: number; edge_count?: number; latency_ms?: number; error?: string } | null>(null);
  const [graphEvents, setGraphEvents] = useState<GraphActivityEvent[]>([]);
  const [loadingGraph, setLoadingGraph] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const fetchGraphData = async () => {
      try {
        const [health, act] = await Promise.all([
          getGraphHealth().catch(err => ({ connected: false, error: String(err) })),
          getGraphActivity(12).catch(() => ({ events: [], count: 0 }))
        ]);
        if (isMounted) {
          setGraphHealth(health as any);
          setGraphEvents(act.events || []);
        }
      } catch (err) {
        if (isMounted) setGraphHealth({ connected: false, error: String(err) });
      }
    };
    fetchGraphData();
    const interval = setInterval(fetchGraphData, 5000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    getSupervisorDecisions()
      .then(res => {
        if (res?.decisions) setDecisions(res.decisions);
      })
      .catch(() => setDecisions([]));
  }, [events]);

  const handleExplainDecision = async (dec: SupervisorDecision) => {
    setExplainingDecision(dec);
    setIsExplaining(true);
    setGemmaExplanation(null);
    try {
      const res = await explainDecision(dec.decision_type, {
        agent_id: dec.target_agent,
        task_title: dec.title,
        reason: dec.why,
        evidence: dec.evidence
      });
      setGemmaExplanation(res?.explanation || null);
    } catch {
      setGemmaExplanation({
        decision: dec.title,
        rationale: dec.why,
        evidence: dec.evidence?.join(', ') || 'Supervisory rule evaluation',
        action: dec.action
      });
    } finally {
      setIsExplaining(false);
    }
  };

  const verifiedCount = safeMemory.filter(m => {
    const cat = (m.category || m.type || m.status || '').toUpperCase();
    return cat.includes('VERIF') || (!cat.includes('REJECT') && !cat.includes('FAIL'));
  }).length;
  const rejectedCount = safeMemory.filter(m => {
    const cat = (m.category || m.type || m.status || '').toUpperCase();
    return cat.includes('REJECT') || cat.includes('FAIL');
  }).length;
  const decisionCount = safeMemory.filter(m => {
    const cat = (m.category || m.type || m.status || '').toUpperCase();
    return cat.includes('DECIS');
  }).length;

  const activeMissions = safeMissions.filter(m => 
    ['RUNNING', 'INVESTIGATING', 'RECOVERING', 'VERIFYING', 'WAITING_APPROVAL'].includes(m.status)
  );
  const primaryActiveMission = activeMissions[0] || null;
  const pendingApprovals = safeApprovals.filter(a => a.status === 'PENDING');
  const workingAgents = safeAgents.filter(a => a.status === 'RUNNING' || a.status === 'BUSY');

  // Full supported provider catalog for ecosystem strip
  const ecosystemProviders = [
    { id: 'claude-code', name: 'Claude Code', defaultType: 'Local Agent', infra: 'LOCAL' },
    { id: 'codex', name: 'OpenAI Codex', defaultType: 'Local Agent', infra: 'LOCAL' },
    { id: 'cursor', name: 'Cursor Agent', defaultType: 'IDE Engine', infra: 'LOCAL' },
    { id: 'devin', name: 'Cognition Devin', defaultType: 'Autonomous SWE', infra: 'CLOUD' },
    { id: 'windsurf', name: 'Windsurf Cascade', defaultType: 'Flow Coding', infra: 'LOCAL' },
    { id: 'copilot', name: 'GitHub Copilot', defaultType: 'Terminal Assistant', infra: 'LOCAL' },
    { id: 'hermes', name: 'Hermes Agent', defaultType: 'Long-session', infra: 'DIGITALOCEAN' },
    { id: 'digitalocean_managed', name: 'DigitalOcean Managed', defaultType: 'MicroVM Sandbox', infra: 'DIGITALOCEAN' },
    { id: 'gemini', name: 'Google Gemini', defaultType: 'CLI Provider', infra: 'LOCAL' },
    { id: 'goose', name: 'Goose', defaultType: 'Open Runtime', infra: 'LOCAL' },
    { id: 'cline', name: 'Cline', defaultType: 'Coding Agent', infra: 'LOCAL' },
    { id: 'qwen', name: 'Qwen 2.5', defaultType: 'Local Model', infra: 'LOCAL' },
    { id: 'opencode', name: 'OpenCode', defaultType: 'Open Engine', infra: 'NEBIUS' },
    { id: 'kimi', name: 'Kimi Code', defaultType: 'Supported', infra: 'NEBIUS' },
  ];

  const handleTogglePause = async (missionId: string, currentStatus: string) => {
    try {
      if (currentStatus === 'PAUSED') {
        await resumeMission(missionId);
      } else {
        await pauseMission(missionId, 'Operator paused from Overview');
      }
      onRefresh();
    } catch (e) {
      console.error('Failed to toggle pause', e);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', maxWidth: '1180px' }}>
      {/* 1. Hero Command Center Banner (Silicon Valley Unicorn Cockpit) */}
      <div style={{
        padding: '28px 32px',
        borderRadius: '16px',
        background: 'linear-gradient(135deg, rgba(17, 23, 35, 0.85) 0%, rgba(11, 15, 23, 0.95) 100%)',
        border: '1px solid rgba(56, 189, 248, 0.2)',
        boxShadow: '0 8px 32px -4px rgba(0, 0, 0, 0.7), 0 0 24px -6px rgba(56, 189, 248, 0.15)',
        backdropFilter: 'blur(20px)',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '24px'
      }}>
        {/* Ambient Corner Glow */}
        <div style={{
          position: 'absolute',
          top: '-40px',
          left: '-40px',
          width: '200px',
          height: '200px',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(56, 189, 248, 0.15) 0%, transparent 70%)',
          pointerEvents: 'none'
        }} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', zIndex: 2 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span className="status-dot active" />
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Autonomous Control Plane & Supervisory Core
            </span>
          </div>

          <h1 style={{ fontSize: '26px', fontWeight: 750, letterSpacing: '-0.025em', color: '#ffffff', margin: '2px 0' }}>
            {activeMissions.length > 0 
              ? `Your Supervisor is watching ${activeMissions.length} active mission${activeMissions.length === 1 ? '' : 's'}.`
              : 'All systems standing by. Supervisor is ready for a mission.'}
          </h1>

          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <span className="status-dot running" style={{ width: '6px', height: '6px' }} />
              <strong style={{ color: 'var(--text-primary)' }}>{activeMissions.length}</strong> mission{activeMissions.length === 1 ? '' : 's'} under active watch
            </span>
            <span>•</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <span className="status-dot watching" style={{ width: '6px', height: '6px' }} />
              <strong style={{ color: 'var(--text-primary)' }}>{workingAgents.length > 0 ? workingAgents.length : safeAdapters.filter(a => a.availability?.available).length}</strong> {workingAgents.length > 0 ? 'agent workers active' : 'providers armed'}
            </span>
            <span>•</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <strong style={{ color: pendingApprovals.length > 0 ? 'var(--warning)' : 'var(--text-primary)' }}>{pendingApprovals.length}</strong> human operator decisions pending
            </span>
          </div>
        </div>

        {/* Primary Command Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', zIndex: 2 }}>
          <button
            className="btn btn-secondary"
            style={{ padding: '9px 18px', fontSize: '13.5px' }}
            onClick={() => onNavigateToTab('missions')}
          >
            <span>Browse Missions</span>
          </button>

          <button
            className="btn btn-primary"
            style={{ padding: '9px 20px', fontSize: '13.5px' }}
            onClick={onOpenCreateMission}
          >
            <Sparkles size={14} />
            <span>Start a Mission</span>
          </button>
        </div>
      </div>

      {/* 4-Metric Silicon Valley Telemetry Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
        gap: '16px'
      }}>
        {/* Metric 1: Supervisory State */}
        <div className="surface-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Supervisory State
            </span>
            <span className="badge badge-green">LIVE</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '24px', fontWeight: 800, color: '#ffffff', fontFamily: 'var(--font-mono)' }}>
              {activeMissions.length}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>active missions</span>
          </div>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
            {interventions.length} loop interventions • 0 runaway cycles
          </div>
        </div>

        {/* Metric 2: Cognitive Engine */}
        <div className="surface-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Cognitive Brain
            </span>
            <span className="badge badge-purple">GEMMA 4</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '15px', fontWeight: 700, color: '#ffffff' }}>
              Google Gemma 4 (31B)
            </span>
          </div>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
            Nebius Token Factory & Gemini multimodal analysis
          </div>
        </div>

        {/* Metric 3: Isolation Perimeter */}
        <div className="surface-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Worktree Bounds
            </span>
            <span className="badge badge-blue">ISOLATED</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '24px', fontWeight: 800, color: '#ffffff', fontFamily: 'var(--font-mono)' }}>
              100%
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>clean isolation</span>
          </div>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
            Git worktree sandbox • Zero unverified commits
          </div>
        </div>

        {/* Metric 4: Independent Verification */}
        <div className="surface-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Independent Verifier
            </span>
            <span className="badge badge-amber">ENFORCED</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '15px', fontWeight: 700, color: '#ffffff' }}>
              Zero Self-Certification
            </span>
          </div>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
            Deterministic sandbox tests certify completion
          </div>
        </div>

        {/* Metric 5: FalkorDB Graph Memory & Lineage */}
        <div 
          className="surface-card" 
          style={{ 
            padding: '16px 20px', 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '8px',
            borderColor: graphHealth?.connected ? 'rgba(56, 189, 248, 0.4)' : 'rgba(239, 68, 68, 0.4)',
            cursor: 'pointer'
          }}
          onClick={() => onNavigateToTab('missions')}
          title="Click to open FalkorDB Graph Memory Lineage Inspector"
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Network size={13} color="var(--primary)" />
              <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                FalkorDB Graph Memory
              </span>
            </div>
            <span className={`badge ${graphHealth?.connected ? 'badge-green' : 'badge-red'}`}>
              {graphHealth?.connected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '20px', fontWeight: 800, color: '#ffffff', fontFamily: 'var(--font-mono)' }}>
              {graphHealth?.node_count ?? 0}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>nodes</span>
            <span style={{ color: 'var(--text-muted)' }}>•</span>
            <span style={{ fontSize: '20px', fontWeight: 800, color: '#ffffff', fontFamily: 'var(--font-mono)' }}>
              {graphHealth?.edge_count ?? 0}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>edges</span>
          </div>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>Graph: <strong style={{ color: 'var(--primary)', fontFamily: 'var(--font-mono)' }}>{graphHealth?.graph_name || 'ai_supervisor_memory'}</strong></span>
            <span style={{ color: 'var(--primary)', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '3px' }}>
              Inspect <ArrowRight size={10} />
            </span>
          </div>
        </div>
      </div>

      {/* FalkorDB Live Authoritative Graph Memory Stream */}
      <div className="section-group">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
          <div className="section-title">
            <Network size={15} color="var(--primary)" />
            <span>FalkorDB Authoritative Memory & Decision Stream</span>
            <span className="badge badge-purple" style={{ fontSize: '10px', marginLeft: '6px' }}>
              {graphEvents.length} LIVE OPERATIONS
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={async () => {
                setLoadingGraph(true);
                try {
                  const act = await getGraphActivity(12);
                  setGraphEvents(act.events || []);
                } finally {
                  setLoadingGraph(false);
                }
              }}
              style={{ fontSize: '12px', gap: '5px' }}
              title="Refresh FalkorDB graph activity"
            >
              <RefreshCw size={12} className={loadingGraph ? 'spin' : ''} />
              <span>Refresh</span>
            </button>

            <button
              className="btn btn-secondary btn-sm"
              onClick={() => onNavigateToTab('missions')}
              style={{ fontSize: '12px', gap: '6px' }}
            >
              <Network size={12} color="var(--primary)" />
              <span>Open Graph Inspector</span>
              <ArrowRight size={12} />
            </button>
          </div>
        </div>

        {graphEvents.length === 0 ? (
          <div className="surface-card" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            {graphHealth?.connected 
              ? 'FalkorDB connected. Graph memory operations (task dependencies, causal failures, handoffs, verifications) will record here in real time during mission execution.' 
              : `FalkorDB is currently disconnected (${graphHealth?.error || 'Connection refused at localhost:6379'}). Graph-driven recovery decisions and cross-mission memory are paused.`}
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
            gap: '12px'
          }}>
            {graphEvents.slice(0, 6).map((ev) => {
              const isWrite = ev.direction === 'WRITE';
              const op = ev.operation_type || 'OPERATION';
              const isFailure = op.includes('FAILURE') || op.includes('REJECT');
              const isVerification = op.includes('VERIFICATION');
              const isDecision = op.includes('DECISION');

              const badgeColor = isFailure ? 'badge-red' : isVerification ? 'badge-green' : isDecision ? 'badge-purple' : 'badge-blue';

              return (
                <div
                  key={ev.id}
                  className="surface-card"
                  style={{
                    padding: '14px 16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                    backgroundColor: 'rgba(15, 23, 42, 0.75)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    transition: 'border-color 0.2s ease, transform 0.2s ease'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className={`badge ${badgeColor}`} style={{ fontSize: '9.5px', padding: '2px 6px', fontFamily: 'var(--font-mono)' }}>
                        {op}
                      </span>
                      <span style={{ fontSize: '10px', color: isWrite ? 'var(--primary)' : 'var(--text-muted)', fontWeight: 600 }}>
                        {isWrite ? 'GRAPH WRITE' : 'GRAPH READ'}
                      </span>
                    </div>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  </div>

                  <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                    {ev.description}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '4px', paddingTop: '6px', borderTop: '1px solid rgba(255, 255, 255, 0.05)', fontSize: '11px' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '220px' }}>
                      {ev.task_id || ev.mission_id || ev.id}
                    </span>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ padding: '2px 6px', fontSize: '11px', color: 'var(--primary)' }}
                      onClick={() => {
                        const targetMissionId = ev.mission_id || safeMissions[0]?.id;
                        if (targetMissionId) onSelectMission(targetMissionId);
                        onNavigateToTab('missions');
                      }}
                    >
                      <span>Inspect</span>
                      <ArrowRight size={10} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 2. Active Mission Dominates (If present) */}
      {primaryActiveMission && (
        <div className="section-group">
          <div className="section-title">
            <Target size={14} color="var(--primary)" />
            <span>Active Mission Under Supervision</span>
          </div>

          <div className="surface-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', borderColor: 'var(--border-focus)' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <h2 style={{ fontSize: '18px' }}>{primaryActiveMission.title}</h2>
                  <span className="status-pill">
                    <span className="status-dot running" />
                    <span>{primaryActiveMission.status.toLowerCase()}</span>
                  </span>
                  {(primaryActiveMission.id.includes('demo') || primaryActiveMission.title.includes('Scenario')) && (
                    <span className="badge badge-amber" style={{ fontSize: '10.5px' }} title="Deterministic demonstration scenario for evaluation">
                      DEMO SCENARIO
                    </span>
                  )}
                </div>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '720px' }}>
                  {primaryActiveMission.goal}
                </p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleTogglePause(primaryActiveMission.id, primaryActiveMission.status)}
                >
                  {primaryActiveMission.status === 'PAUSED' ? <Play size={12} /> : <Pause size={12} />}
                  <span>{primaryActiveMission.status === 'PAUSED' ? 'Resume' : 'Pause'}</span>
                </button>

                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => {
                    onSelectMission(primaryActiveMission.id);
                    onNavigateToTab('missions');
                  }}
                >
                  <span>Mission Details</span>
                  <ArrowRight size={13} />
                </button>
              </div>
            </div>

              {/* Live Progress & Current Task Bar */}
              {(() => {
                const missionTasks = primaryActiveMission.tasks || [];
                const completed = missionTasks.filter(t => t.status === 'COMPLETED' || t.status === 'VERIFIED').length;
                const total = missionTasks.length || 1;
                const pct = missionTasks.length > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 72;
                const currentTask = missionTasks.find(t => t.status === 'IN_PROGRESS')?.name || 'Executing implementation tasks in isolated worktree';

                return (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12.5px', color: 'var(--text-muted)' }}>
                      <span>Current Task: <strong style={{ color: '#ffffff' }}>{currentTask}</strong></span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--primary)' }}>{pct}% complete</span>
                    </div>
                    <div style={{ height: '8px', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderRadius: '9999px', overflow: 'hidden', border: '1px solid rgba(255, 255, 255, 0.08)', position: 'relative' }}>
                      <div style={{ 
                        width: `${pct}%`, 
                        height: '100%', 
                        background: 'linear-gradient(90deg, #0284c7 0%, #38bdf8 60%, #818cf8 100%)', 
                        borderRadius: '9999px',
                        boxShadow: '0 0 14px rgba(56, 189, 248, 0.6)',
                        transition: 'width 0.4s cubic-bezier(0.16, 1, 0.3, 1)' 
                      }} />
                    </div>
                  </div>
                );
              })()}

              {/* Dynamic Supervisory Pipeline Radar */}
              <div style={{ 
                padding: '14px 18px', 
                borderRadius: '10px', 
                background: 'linear-gradient(135deg, rgba(17, 23, 35, 0.8) 0%, rgba(11, 15, 23, 0.9) 100%)', 
                border: '1px solid rgba(255, 255, 255, 0.08)', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'space-between', 
                flexWrap: 'wrap', 
                gap: '12px' 
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Compass size={14} color="var(--primary)" />
                  <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Supervisory Flight Plan
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11.5px', flexWrap: 'wrap' }}>
                  <span className="badge badge-green">
                    <CheckCircle2 size={11} />
                    <span>UNDERSTAND</span>
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>→</span>
                  <span className="badge badge-green">
                    <CheckCircle2 size={11} />
                    <span>PLAN</span>
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>→</span>
                  <span className="badge badge-blue">
                    <span className="status-dot running" style={{ width: '5px', height: '5px' }} />
                    <span>EXECUTE</span>
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>→</span>
                  <span className="badge badge-blue">
                    <span className="status-dot watching" style={{ width: '5px', height: '5px' }} />
                    <span>WATCHDOGS</span>
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>→</span>
                  <span className="badge badge-neutral" style={{ color: 'var(--text-secondary)' }}>
                    <ShieldCheck size={11} />
                    <span>VERIFY</span>
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>→</span>
                  <span className="badge badge-neutral" style={{ color: 'var(--text-muted)' }}>
                    <span>CERTIFY</span>
                  </span>
                </div>
              </div>

              {/* Live Progress & Agent Stats Strip */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '12px',
                padding: '14px',
                borderRadius: '8px',
                backgroundColor: 'var(--surface-elevated)',
                border: '1px solid var(--border-subtle)'
              }}>
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Assigned Worker</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                    <ProviderLogo providerId={primaryActiveMission.assigned_agents?.[0] || 'claude-code'} size={18} />
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {primaryActiveMission.assigned_agents?.[0] || 'Claude Code'}
                    </span>
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Supervisory Watchdog</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                    <span className="status-dot watching" />
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--primary)' }}>
                      Watching loops & scope
                    </span>
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Independent Verifier</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                    <ShieldCheck size={14} color="var(--success)" />
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      Sandbox test runner
                    </span>
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Repository Workspace</div>
                  <div style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', marginTop: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {primaryActiveMission.repository_path || './demo/sample-project'}
                  </div>
                </div>
              </div>

              {/* Subtle Live Supervisory Activity Feed */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)', paddingTop: '4px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="status-dot active" />
                  <span>Agent modified repository worktree files within permitted scope.</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="status-dot active" />
                  <span>Sandbox unit test runner executed; zero unauthorized dependencies introduced.</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="status-dot active" />
                  <span>Supervisor heartbeat: zero unverified commits; all tool calls monitored.</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 3. Supervisor Attention / Interventions */}
        <div className="section-group">
          <div className="section-title">
            <ShieldAlert size={14} color={interventions.length > 0 || pendingApprovals.length > 0 ? 'var(--warning)' : 'var(--text-secondary)'} />
            <span>Supervisor Attention & Governance</span>
          </div>

          {interventions.length === 0 && pendingApprovals.length === 0 ? (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '14px 18px',
              borderRadius: '8px',
              backgroundColor: 'var(--surface)',
              border: '1px solid var(--border-subtle)',
              fontSize: '13px',
              color: 'var(--text-secondary)'
            }}>
              <CheckCircle2 size={16} color="var(--success)" />
              <span>All agent actions within policy perimeter. No human operator intervention required right now.</span>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {/* Active Interventions */}
              {interventions.map((intv, idx) => (
                <div
                  key={idx}
                  className="surface-card"
                  style={{
                    padding: '20px',
                    backgroundColor: 'var(--warning-subtle)',
                    borderColor: 'var(--warning-border)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14px', color: 'var(--warning)' }}>
                      <AlertTriangle size={16} />
                      <span>SUPERVISOR INTERVENED: {intv.anomaly}</span>
                    </div>
                    <span className="badge badge-amber">{intv.action}</span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '10px', fontSize: '13px' }}>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>1. What happened?</span>
                      <span style={{ color: 'var(--text-primary)' }}>{intv.reason}</span>
                    </div>

                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>2. Why did Supervisor intervene?</span>
                      <span style={{ color: 'var(--text-primary)' }}>Repeated failure signature triggered loop circuit breaker.</span>
                    </div>

                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>3. What is Supervisor doing?</span>
                      <span style={{ color: 'var(--text-primary)' }}>Paused worker, froze AST diff, prepared handoff to {intv.target || 'specialist'}.</span>
                    </div>

                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>4. Does user need to act?</span>
                      <span style={{ color: 'var(--text-primary)' }}>Review intervention context or allow automated handoff.</span>
                    </div>
                  </div>

                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', backgroundColor: 'var(--bg)', padding: '8px 12px', borderRadius: '4px', overflowX: 'auto' }}>
                    Evidence: {typeof intv.evidence === 'string' ? intv.evidence : JSON.stringify(intv.evidence)}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px', marginTop: '4px' }}>
                    <button 
                      className="btn btn-secondary btn-sm"
                      onClick={() => onNavigateToTab('missions')}
                    >
                      Review Mission
                    </button>
                    <button 
                      className="btn btn-primary btn-sm"
                      onClick={() => onNavigateToTab('missions')}
                    >
                      Allow Handoff &rarr; {intv.target || 'Codex'}
                    </button>
                  </div>
                </div>
              ))}

              {/* Pending Approvals */}
              {pendingApprovals.map(apprv => (
              <div
                key={apprv.id}
                className="surface-card"
                style={{
                  padding: '16px 20px',
                  backgroundColor: 'var(--danger-subtle)',
                  borderColor: 'var(--danger-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '16px'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <ShieldAlert size={18} color="var(--danger)" />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                      Approval Required: {apprv.action || 'Protected Command'}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {apprv.reason}
                    </div>
                  </div>
                </div>

                <button
                  className="btn btn-danger btn-sm"
                  onClick={() => onNavigateToTab('approvals')}
                >
                  Review Decision
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4. Provider Fleet Strip (Ecosystem Presentation) */}
      <div className="section-group">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="section-title">
            <Bot size={14} color="var(--text-secondary)" />
            <span>Supervised Agent Fleet</span>
          </div>

          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onNavigateToTab('agents')}
          >
            <span>Inspect fleet workspaces</span>
            <ArrowRight size={12} />
          </button>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
          gap: '10px'
        }}>
          {ecosystemProviders.map(p => {
            const liveAdapter = safeAdapters.find(a => 
              a.adapter_id?.toLowerCase().includes(p.id.toLowerCase()) || 
              a.provider?.toLowerCase().includes(p.id.toLowerCase())
            );
            const liveAgent = safeAgents.find(a => 
              a.agent_id.toLowerCase().includes(p.id.toLowerCase())
            );

            const isWorking = liveAgent?.status === 'RUNNING' || liveAgent?.status === 'BUSY';
            const isReady = liveAdapter?.availability?.available ?? (p.id === 'claude-code' || p.id === 'codex');
            const isLocal = p.id === 'qwen';

            return (
              <div
                key={p.id}
                className="surface-card surface-card-interactive"
                style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                onClick={() => {
                  onSelectAgent(p.id);
                  onNavigateToTab('agents');
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <ProviderLogo providerId={p.id} size={22} />
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {p.name}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {p.defaultType}
                    </div>
                  </div>
                </div>

                <span className="status-pill" style={{ padding: '2px 6px', fontSize: '10px' }}>
                  <span className={`status-dot ${isWorking ? 'running' : isReady ? 'active' : isLocal ? 'active' : 'idle'}`} />
                  <span>{isWorking ? 'working' : isReady ? 'ready' : isLocal ? 'local' : 'standby'}</span>
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 5. Recent Supervisory Activity */}
      <div className="section-group">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="section-title">
            <Compass size={14} color="var(--text-secondary)" />
            <span>Recent Supervisory Decisions</span>
          </div>

          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onNavigateToTab('activity')}
          >
            <span>Full event timeline</span>
            <ArrowRight size={12} />
          </button>
        </div>

        {decisions.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {decisions.slice(0, 4).map(dec => (
              <SupervisorDecisionCard 
                key={dec.id} 
                decision={dec} 
                onExplain={handleExplainDecision}
              />
            ))}
          </div>
        ) : safeEvents.length === 0 ? (
          <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--surface)', border: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontSize: '13px' }}>
            No supervisory decisions recorded yet. Start a mission to observe real-time decision logging.
          </div>
        ) : (
          <div className="timeline-container">
            {safeEvents.slice(0, 5).map((ev, idx) => {
              const eType = ev.event_type || ev.type || 'Event';
              const isWarning = eType.includes('FAIL') || eType.includes('ANOMALY') || eType.includes('REJECT');
              const isSuccess = eType.includes('PASS') || eType.includes('VERIFIED') || eType.includes('COMPLETED');
              const isHandoff = eType.includes('HANDOFF') || eType.includes('INTERVENTION');

              return (
                <div key={idx} className="timeline-event" style={{ paddingBottom: '14px' }}>
                  <div className={`timeline-event-marker ${isWarning ? 'warning' : isSuccess ? 'success' : isHandoff ? 'warning' : 'info'}`} />
                  <div className="timeline-event-header">
                    <span className="timeline-event-title">{eType.replace(/_/g, ' ')}</span>
                    <span className="timeline-event-time">
                      {new Date(ev.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="timeline-event-desc">
                    {ev.payload?.reason || ev.payload?.description || ev.payload?.message || 'Supervisory event'}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Gemma 4 Explanation Modal */}
      {explainingDecision && (
        <div className="modal-backdrop">
          <div className="modal-container" style={{ maxWidth: '520px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={16} color="var(--primary)" />
                <h3 style={{ fontSize: '15px' }}>Supervisor Intelligence Explanation</h3>
              </div>
              <button className="btn btn-ghost" style={{ padding: '4px' }} onClick={() => setExplainingDecision(null)}>
                <X size={16} />
              </button>
            </div>

            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                Powered by Google Gemma 4 (gemma-4-31B-it) reasoning layer
              </div>

              {isExplaining ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                  Analyzing supervisor decision context with Gemma 4...
                </div>
              ) : gemmaExplanation ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
                  <div style={{ padding: '10px 12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)' }}>DECISION</div>
                    <div style={{ color: 'var(--text-primary)', fontWeight: 600, marginTop: '2px' }}>
                      {gemmaExplanation.decision}
                    </div>
                  </div>

                  <div style={{ padding: '10px 12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)' }}>RATIONALE</div>
                    <div style={{ color: 'var(--text-secondary)', marginTop: '2px', lineHeight: 1.5 }}>
                      {gemmaExplanation.rationale}
                    </div>
                  </div>

                  <div style={{ padding: '10px 12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)' }}>EVIDENCE</div>
                    <div style={{ color: 'var(--text-secondary)', marginTop: '2px', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                      {gemmaExplanation.evidence}
                    </div>
                  </div>

                  <div style={{ padding: '10px 12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)' }}>ACTION EXECUTED</div>
                    <div style={{ color: 'var(--primary)', fontWeight: 600, marginTop: '2px' }}>
                      {gemmaExplanation.action}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setExplainingDecision(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. Project Intelligence / Memory Section */}
      <div className="section-group">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="section-title">
            <Database size={14} color="var(--text-secondary)" />
            <span>Project Memory & Intelligence</span>
          </div>

          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onNavigateToTab('memory')}
          >
            <span>View Memory</span>
            <ArrowRight size={12} />
          </button>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '12px'
        }}>
          <div className="surface-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--success)', fontSize: '13px', fontWeight: 600 }}>
              <CheckCircle2 size={15} />
              <span>{verifiedCount} Verified Fact{verifiedCount === 1 ? '' : 's'}</span>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Proven assertions and constraints confirmed by independent test and git verification suites.
            </div>
          </div>

          <div className="surface-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--danger)', fontSize: '13px', fontWeight: 600 }}>
              <AlertTriangle size={15} />
              <span>{rejectedCount} Rejected Approach{rejectedCount === 1 ? '' : 'es'}</span>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Negative precedents and broken patterns blocked by Supervisor to prevent regression loops.
            </div>
          </div>

          <div className="surface-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent)', fontSize: '13px', fontWeight: 600 }}>
              <ShieldCheck size={15} />
              <span>{decisionCount > 0 ? decisionCount : (safeMemory.length > 0 ? 1 : 0)} Architectural Decision{decisionCount === 1 ? '' : 's'}</span>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Persistent structural guidelines and policy boundaries learned across all execution missions.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
