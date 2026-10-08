import React, { useState } from 'react';
import { 
  Compass, 
  Search, 
  ChevronDown, 
  ChevronRight,
  Code2
} from 'lucide-react';
import type { Event } from '../types';

interface ActivityProps {
  events: Event[];
  wsConnected: boolean;
}

export const Activity: React.FC<ActivityProps> = ({
  events,
  wsConnected
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [expandedIndices, setExpandedIndices] = useState<Record<string, boolean>>({});

  const safeEvents = Array.isArray(events) ? events : [];

  const filterTabs = [
    { id: 'ALL', label: 'All' },
    { id: 'SUPERVISOR', label: 'Supervisor' },
    { id: 'AGENTS', label: 'Agents' },
    { id: 'WATCHDOGS', label: 'Watchdogs' },
    { id: 'HANDOFFS', label: 'Handoffs' },
    { id: 'VERIFICATION', label: 'Verification' },
    { id: 'APPROVALS', label: 'Approvals' }
  ];

  const filteredEvents = safeEvents.filter(ev => {
    const eType = (ev.event_type || ev.type || '').toUpperCase();
    if (categoryFilter !== 'ALL') {
      if (categoryFilter === 'SUPERVISOR' && !eType.includes('SUPERVISOR') && !eType.includes('INTERVENTION') && !eType.includes('MISSION')) return false;
      if (categoryFilter === 'AGENTS' && !eType.includes('AGENT') && !eType.includes('TASK')) return false;
      if (categoryFilter === 'WATCHDOGS' && !eType.includes('WATCHDOG') && !eType.includes('ANOMALY') && !eType.includes('LOOP')) return false;
      if (categoryFilter === 'HANDOFFS' && !eType.includes('HANDOFF')) return false;
      if (categoryFilter === 'VERIFICATION' && !eType.includes('VERIF')) return false;
      if (categoryFilter === 'APPROVALS' && !eType.includes('APPROVAL')) return false;
    }

    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const inType = eType.toLowerCase().includes(q);
      const inPayload = JSON.stringify(ev.payload || {}).toLowerCase().includes(q);
      const inMission = (ev.mission_id || '').toLowerCase().includes(q);
      return inType || inPayload || inMission;
    }
    return true;
  });

  const toggleExpand = (id: string) => {
    setExpandedIndices(prev => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1080px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-title">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h1>Activity</h1>
            <span className="status-pill">
              <span className={`status-dot ${wsConnected ? 'active' : 'offline'}`} />
              <span style={{ fontSize: '11px' }}>{wsConnected ? 'Live stream' : 'Disconnected'}</span>
            </span>
          </div>
          <p>Supervisory timeline of agent decisions, loop interventions, and independent verification events.</p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {filterTabs.map(tab => (
            <button
              key={tab.id}
              className={`btn btn-sm ${categoryFilter === tab.id ? 'btn-secondary' : 'btn-ghost'}`}
              style={{ fontWeight: categoryFilter === tab.id ? 600 : 400 }}
              onClick={() => setCategoryFilter(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{ position: 'relative', width: '280px' }}>
          <input
            type="text"
            placeholder="Search activity by event or payload..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            style={{ width: '100%', paddingLeft: '32px' }}
          />
          <Search size={14} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
        </div>
      </div>

      {/* Events Timeline */}
      {filteredEvents.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <Compass size={18} />
          </div>
          <div className="empty-state-title">No supervisory activity yet</div>
          <div className="empty-state-desc">
            {searchTerm 
              ? `No events match query "${searchTerm}".` 
              : 'Start a mission to observe real-time Supervisor decisions, watchdog interventions, and verification records.'}
          </div>
        </div>
      ) : (
        <div className="timeline-container">
          {filteredEvents.map((ev, idx) => {
            const eType = ev.event_type || ev.type || 'Supervisory Event';
            const isWarning = eType.includes('FAIL') || eType.includes('ANOMALY') || eType.includes('REJECT');
            const isSuccess = eType.includes('PASS') || eType.includes('VERIFIED') || eType.includes('COMPLETED');
            const isHandoff = eType.includes('HANDOFF') || eType.includes('INTERVENTION') || eType.includes('LOOP');
            
            const evId = ev.id || `evt-${idx}-${ev.timestamp}`;
            const isExpanded = !!expandedIndices[evId];

            // Human language translation
            let humanTitle = eType.replace(/_/g, ' ');
            let humanSummary = ev.payload?.reason || ev.payload?.description || ev.payload?.message || 'Supervisory decision logged';
            let actionTaken = ev.payload?.action || null;

            if (eType.includes('WATCHDOG') || eType.includes('LOOP')) {
              humanTitle = 'Supervisor Intervened';
              humanSummary = ev.payload?.reason || 'Agent repeated failing approach. Paused to prevent loop.';
              actionTaken = actionTaken || 'Agent paused';
            } else if (eType.includes('HANDOFF')) {
              humanTitle = 'Agent Handoff Routed';
              humanSummary = ev.payload?.reason || 'Context package frozen and handed off to specialist.';
              actionTaken = actionTaken || 'Handoff dispatched';
            } else if (eType.includes('VERIFICATION_PASSED')) {
              humanTitle = 'Independent Verification Certified';
              humanSummary = 'Sandbox test suite executed and all deliverables passed without regressions.';
            }

            return (
              <div key={evId} className="timeline-event" style={{ paddingBottom: '20px' }}>
                <div className={`timeline-event-marker ${isWarning ? 'warning' : isSuccess ? 'success' : isHandoff ? 'warning' : 'info'}`} />
                
                <div className="timeline-event-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="timeline-event-title" style={{ fontSize: '13px', fontWeight: 600 }}>
                      {humanTitle}
                    </span>
                    {actionTaken && (
                      <span className="badge badge-amber" style={{ fontSize: '10px' }}>
                        Action: {actionTaken}
                      </span>
                    )}
                  </div>

                  <span className="timeline-event-time">
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </span>
                </div>

                <div className="timeline-event-desc" style={{ marginTop: '3px' }}>
                  {humanSummary}
                </div>

                {/* Progressive Technical Disclosure */}
                <div style={{ marginTop: '8px' }}>
                  <button
                    onClick={() => toggleExpand(evId)}
                    className="btn btn-ghost btn-sm"
                    style={{ padding: '2px 0', fontSize: '11px', color: 'var(--text-muted)' }}
                  >
                    <Code2 size={11} />
                    <span>{isExpanded ? 'Hide technical details' : 'Expand technical details'}</span>
                    {isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                  </button>

                  {isExpanded && (
                    <div style={{
                      marginTop: '8px',
                      padding: '12px',
                      borderRadius: '6px',
                      backgroundColor: 'var(--surface-elevated)',
                      border: '1px solid var(--border-subtle)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '11px',
                      color: 'var(--text-secondary)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
                        <div><strong style={{ color: 'var(--text-muted)' }}>Event ID:</strong> {ev.id || 'N/A'}</div>
                        <div><strong style={{ color: 'var(--text-muted)' }}>Raw Type:</strong> {eType}</div>
                        <div><strong style={{ color: 'var(--text-muted)' }}>Mission ID:</strong> {ev.mission_id || 'N/A'}</div>
                        <div><strong style={{ color: 'var(--text-muted)' }}>Target:</strong> {ev.payload?.target || ev.payload?.agent_id || 'N/A'}</div>
                      </div>

                      <div>
                        <div style={{ color: 'var(--text-muted)', marginBottom: '4px' }}>Payload:</div>
                        <pre style={{ overflowX: 'auto', maxHeight: '200px' }}>
                          {JSON.stringify(ev.payload || {}, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
