import React from 'react';
import { 
  Target, 
  Bot, 
  ShieldAlert, 
  CheckCircle2, 
  AlertTriangle, 
  ArrowRight, 
  Plus, 
  Compass 
} from 'lucide-react';
import type { Mission, AgentRecord, ApprovalRequest, Event, InterventionDetail, AdapterInfo } from '../types';

interface OverviewProps {
  missions: Mission[];
  agents: AgentRecord[];
  adapters: AdapterInfo[];
  approvals: ApprovalRequest[];
  interventions: InterventionDetail[];
  events: Event[];
  onSelectMission: (missionId: string) => void;
  onSelectAgent: (agentId: string) => void;
  onNavigateToTab: (tab: any) => void;
  onOpenCreateMission: () => void;
}

export const Overview: React.FC<OverviewProps> = ({
  missions,
  agents,
  adapters,
  approvals,
  interventions,
  events,
  onSelectMission,
  onSelectAgent,
  onNavigateToTab,
  onOpenCreateMission
}) => {
  const safeMissions = Array.isArray(missions) ? missions : [];
  const safeAgents = Array.isArray(agents) ? agents : [];
  const safeApprovals = Array.isArray(approvals) ? approvals : [];
  const safeEvents = Array.isArray(events) ? events : [];

  const activeMissions = safeMissions.filter(m => 
    ['RUNNING', 'INVESTIGATING', 'RECOVERING', 'VERIFYING', 'WAITING_APPROVAL'].includes(m.status)
  );
  const pendingApprovals = safeApprovals.filter(a => a.status === 'PENDING');

  // Overall status summary
  const hasUrgentIssue = pendingApprovals.length > 0 || interventions.length > 0;
  const statusHeadline = hasUrgentIssue
    ? `${pendingApprovals.length} item(s) require supervisor review`
    : activeMissions.length > 0
      ? `${activeMissions.length} active mission(s) under supervision`
      : 'All systems standing by';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', maxWidth: '1080px' }}>
      {/* Overview Header */}
      <div className="page-header">
        <div className="page-header-title">
          <h1>Overview</h1>
          <p>
            {statusHeadline} · Authoritative local SQLite engine
          </p>
        </div>

        <div className="page-header-actions">
          <button className="btn btn-primary" onClick={onOpenCreateMission}>
            <Plus size={14} />
            <span>New Mission</span>
          </button>
        </div>
      </div>

      {/* 1. What Needs Attention? */}
      <div className="section-group">
        <div className="section-title">
          <ShieldAlert size={14} color="var(--warning)" />
          <span>Needs Attention</span>
        </div>

        {pendingApprovals.length === 0 && interventions.length === 0 ? (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '12px 16px',
            borderRadius: '6px',
            backgroundColor: 'var(--surface)',
            border: '1px solid var(--border-subtle)',
            fontSize: '13px',
            color: 'var(--text-secondary)'
          }}>
            <CheckCircle2 size={16} color="var(--success)" />
            <span>No pending approvals or active watchdog blocks. The supervisory perimeter is clear.</span>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {/* Pending Approvals */}
            {pendingApprovals.map(apprv => (
              <div 
                key={apprv.id} 
                className="item-row"
                style={{ borderColor: 'var(--danger-border)', backgroundColor: 'var(--danger-subtle)' }}
                onClick={() => onNavigateToTab('approvals')}
              >
                <div className="item-row-primary">
                  <ShieldAlert size={16} color="var(--danger)" />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '13px' }}>
                      Approval Required: {apprv.action || 'Protected Operation'}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {apprv.reason || 'Agent requested execution requiring human verification'}
                    </div>
                  </div>
                </div>

                <div className="item-row-meta">
                  <span className="badge badge-red">Needs Decision</span>
                  <button className="btn btn-danger btn-sm">
                    Review
                  </button>
                </div>
              </div>
            ))}

            {/* Active Interventions */}
            {interventions.map((intv, idx) => (
              <div 
                key={idx} 
                className="item-row"
                style={{ borderColor: 'var(--warning-border)', backgroundColor: 'var(--warning-subtle)' }}
              >
                <div className="item-row-primary">
                  <AlertTriangle size={16} color="var(--warning)" />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '13px' }}>
                      Watchdog Intervened: {intv.anomaly}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {intv.reason}
                    </div>
                  </div>
                </div>

                <div className="item-row-meta">
                  <span className="badge badge-amber">{intv.action}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. What is Happening? (Active Missions) */}
      <div className="section-group">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="section-title">
            <Target size={14} color="var(--primary)" />
            <span>Active Work ({activeMissions.length})</span>
          </div>

          <button 
            className="btn btn-ghost btn-sm"
            onClick={() => onNavigateToTab('missions')}
          >
            <span>View all missions ({safeMissions.length})</span>
            <ArrowRight size={12} />
          </button>
        </div>

        {activeMissions.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <Target size={18} />
            </div>
            <div className="empty-state-title">No active missions running</div>
            <div className="empty-state-desc">
              Start a new supervised mission or load a demo scenario. The Supervisor will plan tasks, route agents, and verify work independently.
            </div>
            <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
              <button className="btn btn-primary btn-sm" onClick={onOpenCreateMission}>
                <Plus size={13} />
                <span>Create Mission</span>
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {activeMissions.map(m => {
              const assigned = m.assigned_agents || m.assigned_agent_ids || [];
              return (
                <div 
                  key={m.id} 
                  className="item-row"
                  onClick={() => {
                    onSelectMission(m.id);
                    onNavigateToTab('missions');
                  }}
                >
                  <div className="item-row-primary">
                    <span className={`status-dot ${m.status === 'RUNNING' ? 'running' : 'watching'}`} />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '14px' }}>
                        {m.title}
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {m.goal}
                      </div>
                    </div>
                  </div>

                  <div className="item-row-meta">
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-secondary)' }}>
                      {assigned.length > 0 ? assigned.join(' → ') : 'Claude Code'}
                    </span>
                    <span className="badge badge-blue">
                      {m.status.toLowerCase()}
                    </span>
                    <ArrowRight size={14} color="var(--text-muted)" />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 3. What Are My Agents Doing? */}
      <div className="section-group">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="section-title">
            <Bot size={14} color="var(--text-secondary)" />
            <span>Connected Agents</span>
          </div>

          <button 
            className="btn btn-ghost btn-sm"
            onClick={() => onNavigateToTab('agents')}
          >
            <span>Agent fleet details</span>
            <ArrowRight size={12} />
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '12px' }}>
          {adapters.length === 0 && safeAgents.length === 0 ? (
            <div style={{ padding: '16px', borderRadius: '6px', backgroundColor: 'var(--surface)', border: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontSize: '12px', gridColumn: '1 / -1' }}>
              No connected agent adapters detected. AI Supervisor is ready to receive Claude Code, Codex, or Gemini connections.
            </div>
          ) : (
            adapters.map(adapter => {
              const liveAgent = safeAgents.find(a => a.agent_id.toLowerCase().includes((adapter.adapter_id || '').toLowerCase()));
              const isWorking = liveAgent?.status === 'RUNNING' || liveAgent?.status === 'BUSY';
              const isAvail = adapter.availability?.available ?? true;
              const statusText = isWorking ? 'Working' : isAvail ? 'Available' : 'CLI not detected';

              return (
                <div 
                  key={adapter.adapter_id} 
                  className="surface-card surface-card-interactive"
                  onClick={() => {
                    onSelectAgent(adapter.adapter_id);
                    onNavigateToTab('agents');
                  }}
                  style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>{adapter.display_name}</div>
                    <span className={`status-dot ${isWorking ? 'running' : isAvail ? 'active' : 'idle'}`} />
                  </div>

                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {statusText}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px', flexWrap: 'wrap' }}>
                    {adapter.capabilities.slice(0, 3).map(c => (
                      <span key={c} className="badge badge-neutral" style={{ fontSize: '10px' }}>
                        {c.toLowerCase()}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 4. Recent Supervisory Activity */}
      <div className="section-group">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="section-title">
            <Compass size={14} color="var(--text-secondary)" />
            <span>Recent Supervisory Activity</span>
          </div>

          <button 
            className="btn btn-ghost btn-sm"
            onClick={() => onNavigateToTab('activity')}
          >
            <span>Full timeline</span>
            <ArrowRight size={12} />
          </button>
        </div>

        {safeEvents.length === 0 ? (
          <div style={{ padding: '16px', borderRadius: '6px', backgroundColor: 'var(--surface)', border: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontSize: '12px' }}>
            No recent events recorded. Start a mission to observe supervisory timeline events in real time.
          </div>
        ) : (
          <div className="timeline-container" style={{ paddingLeft: '16px' }}>
            {safeEvents.slice(0, 5).map((ev, idx) => {
              const eType = ev.event_type || ev.type || 'Event';
              const isWarning = eType.includes('FAIL') || eType.includes('ANOMALY') || eType.includes('REJECT');
              const isSuccess = eType.includes('PASS') || eType.includes('VERIFIED') || eType.includes('COMPLETED');

              return (
                <div key={idx} className="timeline-event" style={{ paddingBottom: '14px' }}>
                  <div className={`timeline-event-marker ${isWarning ? 'warning' : isSuccess ? 'success' : 'info'}`} />
                  <div className="timeline-event-header">
                    <span className="timeline-event-title">{eType.replace(/_/g, ' ')}</span>
                    <span className="timeline-event-time">
                      {new Date(ev.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="timeline-event-desc">
                    {ev.payload?.reason || ev.payload?.description || ev.payload?.message || (ev.mission_id ? `Mission: ${ev.mission_id}` : 'Supervisory event')}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
