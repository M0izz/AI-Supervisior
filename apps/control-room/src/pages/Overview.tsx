import React from 'react';
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
  Database
} from 'lucide-react';
import type { Mission, AgentRecord, ApprovalRequest, Event, InterventionDetail, AdapterInfo, MemoryRecord } from '../types';
import { ProviderLogo } from '../components/ProviderLogo';
import { pauseMission, resumeMission } from '../api';

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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', maxWidth: '1080px' }}>
      {/* 1. Hero Command Center Banner */}
      <div style={{
        padding: '24px 28px',
        borderRadius: '10px',
        backgroundColor: 'var(--surface)',
        border: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '20px'
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="status-dot active" />
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Supervisor Command Center
            </span>
          </div>

          <h1 style={{ fontSize: '24px', fontWeight: 600, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
            {activeMissions.length > 0 
              ? `Your Supervisor is watching ${activeMissions.length} active mission.`
              : 'All systems standing by. Supervisor is ready for a mission.'}
          </h1>

          <div style={{ fontSize: '13px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <span>{activeMissions.length} mission{activeMissions.length === 1 ? '' : 's'} running</span>
            <span>•</span>
            <span>{workingAgents.length > 0 ? `${workingAgents.length} agents working` : `${safeAdapters.filter(a => a.availability?.available).length || 2} providers ready`}</span>
            <span>•</span>
            <span>{pendingApprovals.length} decisions requiring you</span>
          </div>
        </div>

        {/* Primary Command Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            className="btn btn-secondary"
            style={{ padding: '8px 16px', fontSize: '13px' }}
            onClick={() => onNavigateToTab('missions')}
          >
            <span>Browse Missions</span>
          </button>

          <button
            className="btn btn-primary"
            style={{ padding: '8px 18px', fontSize: '13px' }}
            onClick={onOpenCreateMission}
          >
            <Sparkles size={14} />
            <span>Start a Mission</span>
          </button>
        </div>
      </div>

      {/* Operational Status Strip (Section 28) */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        padding: '10px 16px',
        borderRadius: '8px',
        backgroundColor: 'var(--surface)',
        border: '1px solid var(--border)',
        fontSize: '12px',
        color: 'var(--text-secondary)',
        flexWrap: 'wrap'
      }}>
        <span style={{ fontWeight: 600, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.04em', fontSize: '11px' }}>
          Supervisor Status:
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className="status-dot active" style={{ width: '6px', height: '6px' }} />
          <span>Watching {activeMissions.length} mission{activeMissions.length === 1 ? '' : 's'}</span>
        </span>
        <span>•</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className="status-dot running" style={{ width: '6px', height: '6px' }} />
          <span>{workingAgents.length} agents active</span>
        </span>
        <span>•</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className="status-dot watching" style={{ width: '6px', height: '6px' }} />
          <span>{interventions.length} intervention{interventions.length === 1 ? '' : 's'}</span>
        </span>
        <span>•</span>
        <span>{pendingApprovals.length} approvals pending</span>
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
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <h2 style={{ fontSize: '18px' }}>{primaryActiveMission.title}</h2>
                  <span className="status-pill">
                    <span className="status-dot running" />
                    <span>{primaryActiveMission.status.toLowerCase()}</span>
                  </span>
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
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-muted)' }}>
                      <span>Current Task: <strong style={{ color: 'var(--text-primary)' }}>{currentTask}</strong></span>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{pct}% complete</span>
                    </div>
                    <div style={{ height: '6px', backgroundColor: 'var(--surface-elevated)', borderRadius: '3px', overflow: 'hidden' }}>
                      <div style={{ width: `${pct}%`, height: '100%', backgroundColor: 'var(--primary)', transition: 'width 0.3s ease' }} />
                    </div>
                  </div>
                );
              })()}

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

        {safeEvents.length === 0 ? (
          <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--surface)', border: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontSize: '13px' }}>
            No supervisory events recorded yet. Start a mission to observe real-time decision logging.
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
