import React, { useState } from 'react';
import { 
  Cpu, 
  Search, 
  ArrowDown, 
  Radio
} from 'lucide-react';
import type { Event } from '../types';

interface SupervisorEventsProps {
  events: Event[];
  wsConnected: boolean;
  onClearEvents?: () => void;
}

export const SupervisorEvents: React.FC<SupervisorEventsProps> = ({
  events,
  wsConnected
}) => {
  const [filterType, setFilterType] = useState<string>('ALL');
  const [filterSeverity, setFilterSeverity] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);
  const [viewMode, setViewMode] = useState<'timeline' | 'table'>('timeline');

  // Filter events
  const safeEvents = Array.isArray(events) ? events : [];
  const filteredEvents = safeEvents.filter((ev) => {
    const eventType = ev.event_type || ev.type || '';
    if (filterType !== 'ALL' && eventType !== filterType) return false;
    if (filterSeverity !== 'ALL') {
      const sev = (ev.payload?.severity as string || ev.severity || 'INFO').toUpperCase();
      if (sev !== filterSeverity) return false;
    }
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const inType = eventType.toLowerCase().includes(term);
      const inMission = (ev.mission_id || '').toLowerCase().includes(term);
      const inPayload = JSON.stringify(ev.payload || {}).toLowerCase().includes(term);
      if (!inType && !inMission && !inPayload) return false;
    }
    return true;
  });

  const getEventBadge = (type: string) => {
    if (type.includes('ANOMALY') || type.includes('FAIL') || type.includes('REJECT')) {
      return <span className="badge badge-crimson">{type}</span>;
    }
    if (type.includes('INTERVENTION') || type.includes('LOOP') || type.includes('PAUSED')) {
      return <span className="badge badge-amber">{type}</span>;
    }
    if (type.includes('COMPLETED') || type.includes('RECOVERED') || type.includes('PASS')) {
      return <span className="badge badge-emerald">{type}</span>;
    }
    return <span className="badge badge-cyan">{type}</span>;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Top Filter and Mode Bar */}
      <div className="cr-panel" style={{ marginBottom: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Radio size={14} color={wsConnected ? 'var(--status-emerald)' : 'var(--status-amber)'} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600 }}>
                {wsConnected ? 'LIVE EVENT STREAM' : 'OFFLINE / RECONNECTING'}
              </span>
              <span className="badge badge-neutral" style={{ fontSize: '10px' }}>
                {filteredEvents.length} EVENTS
              </span>
            </div>
          </div>

          {/* Toggle View Mode */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button 
              className={`btn ${viewMode === 'timeline' ? 'btn-primary' : ''}`}
              onClick={() => setViewMode('timeline')}
            >
              SUPERVISOR TIMELINE
            </button>
            <button 
              className={`btn ${viewMode === 'table' ? 'btn-primary' : ''}`}
              onClick={() => setViewMode('table')}
            >
              RAW STREAM TABLE
            </button>
          </div>
        </div>

        {/* Filter Controls Row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '12px', flexWrap: 'wrap' }}>
          <div style={{ flex: '1', minWidth: '200px' }}>
            <div style={{ position: 'relative' }}>
              <input 
                type="text" 
                placeholder="Search event type, mission ID, or payload details..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{ paddingLeft: '28px' }}
              />
              <Search size={14} style={{ position: 'absolute', left: '8px', top: '9px', color: 'var(--text-muted)' }} />
            </div>
          </div>

          <div style={{ width: '180px' }}>
            <select 
              value={filterType} 
              onChange={(e) => setFilterType(e.target.value)}
            >
              <option value="ALL">All Event Types</option>
              <option value="ANOMALY_DETECTED">Anomaly Detected</option>
              <option value="INTERVENTION_TRIGGERED">Intervention Triggered</option>
              <option value="TASK_FAILED">Task Failed</option>
              <option value="TASK_COMPLETED">Task Completed</option>
              <option value="RECOVERY_COMPLETED">Recovery Completed</option>
              <option value="TOOL_CALL_EXECUTED">Tool Call Executed</option>
            </select>
          </div>

          <div style={{ width: '140px' }}>
            <select 
              value={filterSeverity} 
              onChange={(e) => setFilterSeverity(e.target.value)}
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="WARNING">Warning</option>
              <option value="INFO">Info</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main View: Timeline vs Table */}
      {viewMode === 'timeline' ? (
        <div className="cr-panel">
          <div className="cr-panel-header">
            <div className="cr-panel-title">
              <Cpu size={15} color="var(--status-cyan)" />
              <span>Supervisor Dynamic Story Timeline</span>
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
              LIVE CAUSAL CHAIN RECONSTRUCTION
            </span>
          </div>

          {filteredEvents.length === 0 ? (
            <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              NO EVENTS MATCHING FILTER CRITERIA
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {filteredEvents.map((ev, idx) => {
                const eventType = ev.event_type || ev.type || 'EVENT';
                const eventId = ev.id || ev.event_id || `ev-${idx}`;
                const isIntervention = eventType.includes('INTERVENTION') || eventType.includes('ANOMALY') || eventType.includes('LOOP');
                const isRecovery = eventType.includes('RECOVERY') || eventType.includes('COMPLETED');
                const isFailure = eventType.includes('FAILED') || eventType.includes('REJECT');

                return (
                  <React.Fragment key={eventId}>
                    {idx > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'center', padding: '2px 0' }}>
                        <ArrowDown size={14} color="var(--border-strong)" />
                      </div>
                    )}

                    <div 
                      onClick={() => setSelectedEvent(ev)}
                      style={{
                        backgroundColor: isIntervention ? 'var(--status-amber-bg)' : isFailure ? 'var(--status-crimson-bg)' : isRecovery ? 'var(--status-emerald-bg)' : 'var(--bg-core)',
                        border: isIntervention ? '1px solid var(--status-amber-border)' : isFailure ? '1px solid var(--status-crimson-border)' : isRecovery ? '1px solid var(--status-emerald-border)' : '1px solid var(--border-default)',
                        borderRadius: '4px',
                        padding: '12px 14px',
                        cursor: 'pointer'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                            {new Date(ev.timestamp).toLocaleTimeString()}
                          </span>
                          {getEventBadge(eventType)}
                          {ev.mission_id && (
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                              MISSION: {ev.mission_id}
                            </span>
                          )}
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                          ID: {eventId}
                        </span>
                      </div>

                      {/* Event Headline */}
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-primary)', marginBottom: '6px' }}>
                        {ev.payload?.message || ev.payload?.reason || ev.payload?.action || JSON.stringify(ev.payload)}
                      </div>

                      {/* Event Extra Meta */}
                      {ev.payload && typeof ev.payload === 'object' && Object.keys(ev.payload).length > 0 && (
                        <div style={{
                          backgroundColor: 'var(--bg-surface)',
                          padding: '6px 8px',
                          borderRadius: '2px',
                          fontSize: '11px',
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-secondary)',
                          border: '1px solid var(--border-subtle)',
                          overflowX: 'auto'
                        }}>
                          {Object.entries(ev.payload).slice(0, 4).map(([k, v]) => (
                            <span key={k} style={{ marginRight: '14px' }}>
                              <strong style={{ color: 'var(--text-muted)' }}>{k}:</strong> {String(v)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </React.Fragment>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        /* Raw Stream Table */
        <div className="cr-panel">
          <table className="cr-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Type</th>
                <th>Mission</th>
                <th>Payload Summary</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.map((ev, i) => {
                const eventType = ev.event_type || ev.type || 'EVENT';
                const eventId = ev.id || ev.event_id || `ev-${i}`;

                return (
                  <tr key={eventId} onClick={() => setSelectedEvent(ev)} style={{ cursor: 'pointer' }}>
                    <td className="font-mono">{new Date(ev.timestamp).toLocaleTimeString()}</td>
                    <td>{getEventBadge(eventType)}</td>
                    <td className="font-mono">{ev.mission_id || '-'}</td>
                    <td className="font-mono" style={{ maxWidth: '400px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {JSON.stringify(ev.payload)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Selected Event Payload Modal / Drawer */}
      {selectedEvent && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          width: '500px',
          maxHeight: '400px',
          backgroundColor: 'var(--bg-surface-elevated)',
          border: '1px solid var(--border-strong)',
          borderRadius: '4px',
          boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
          zIndex: 50,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}>
          <div style={{
            padding: '10px 14px',
            backgroundColor: 'var(--bg-core)',
            borderBottom: '1px solid var(--border-default)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600 }}>
              EVENT INSPECTOR // {selectedEvent.event_type || selectedEvent.type}
            </span>
            <button 
              className="btn" 
              style={{ padding: '2px 6px', fontSize: '10px' }}
              onClick={() => setSelectedEvent(null)}
            >
              CLOSE
            </button>
          </div>
          <div style={{ padding: '14px', overflowY: 'auto', flex: 1 }}>
            <pre style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--status-cyan)', whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(selectedEvent, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};
