import React, { useState } from 'react';
import { 
  Compass, 
  Search, 
  ChevronDown, 
  ChevronRight
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
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [expandedIndices, setExpandedIndices] = useState<Record<number, boolean>>({});

  const safeEvents = Array.isArray(events) ? events : [];

  const filteredEvents = safeEvents.filter(ev => {
    const eType = ev.event_type || ev.type || '';
    if (severityFilter !== 'ALL') {
      const sev = (ev.payload?.severity as string || ev.severity || 'INFO').toUpperCase();
      if (sev !== severityFilter) return false;
    }
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const inType = eType.toLowerCase().includes(q);
      const inPayload = JSON.stringify(ev.payload || {}).toLowerCase().includes(q);
      return inType || inPayload;
    }
    return true;
  });

  const toggleExpand = (idx: number) => {
    setExpandedIndices(prev => ({ ...prev, [idx]: !prev[idx] }));
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
          <p>Chronological supervisory decisions, agent interventions, and independent verification events</p>
        </div>
      </div>

      {/* Filter Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          {['ALL', 'INFO', 'WARNING', 'ERROR'].map(s => (
            <button
              key={s}
              className={`btn btn-sm ${severityFilter === s ? 'btn-secondary' : 'btn-ghost'}`}
              style={{ fontWeight: severityFilter === s ? 600 : 400 }}
              onClick={() => setSeverityFilter(s)}
            >
              {s.toLowerCase()}
            </button>
          ))}
        </div>

        <div style={{ position: 'relative', width: '280px' }}>
          <input
            type="text"
            placeholder="Search activity by event or details..."
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
          <div className="empty-state-title">No events matching filter</div>
          <div className="empty-state-desc">
            {searchTerm ? `No events match query "${searchTerm}".` : 'Supervisory event stream will populate as missions and agents execute.'}
          </div>
        </div>
      ) : (
        <div className="timeline-container">
          {filteredEvents.map((ev, idx) => {
            const eType = ev.event_type || ev.type || 'Supervisory Event';
            const isWarning = eType.includes('FAIL') || eType.includes('ANOMALY') || eType.includes('REJECT');
            const isSuccess = eType.includes('PASS') || eType.includes('VERIFIED') || eType.includes('COMPLETED');
            const isIntervention = eType.includes('INTERVENTION') || eType.includes('HANDOFF') || eType.includes('LOOP');
            const isExpanded = !!expandedIndices[idx];

            const description = ev.payload?.reason || ev.payload?.description || ev.payload?.message || 'Supervisory decision logged';

            return (
              <div key={idx} className="timeline-event" style={{ paddingBottom: '20px' }}>
                <div className={`timeline-event-marker ${isWarning ? 'warning' : isSuccess ? 'success' : isIntervention ? 'warning' : 'info'}`} />
                
                <div className="timeline-event-header">
                  <span className="timeline-event-title" style={{ fontSize: '14px' }}>
                    {eType.replace(/_/g, ' ')}
                  </span>
                  <span className="timeline-event-time">
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </span>
                  {ev.mission_id && (
                    <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                      [{ev.mission_id}]
                    </span>
                  )}
                </div>

                <div className="timeline-event-desc" style={{ marginTop: '2px' }}>
                  {description}
                </div>

                {/* Expandable Technical Details */}
                <div style={{ marginTop: '6px' }}>
                  <button
                    onClick={() => toggleExpand(idx)}
                    className="btn btn-ghost btn-sm"
                    style={{ padding: '2px 6px', fontSize: '11px', color: 'var(--text-muted)' }}
                  >
                    {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    <span>{isExpanded ? 'Hide technical details' : 'View technical details'}</span>
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
                      overflowX: 'auto',
                      maxHeight: '260px'
                    }}>
                      <pre>{JSON.stringify(ev.payload || {}, null, 2)}</pre>
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
