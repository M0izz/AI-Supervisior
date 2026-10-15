import React, { useState, useMemo } from 'react';
import { 
  Compass, 
  Search, 
  ShieldAlert, 
  CheckCircle2, 
  ArrowRightLeft, 
  Lock, 
  Layers, 
  Sliders, 
  Database, 
  Copy, 
  Check, 
  Play, 
  Pause, 
  X, 
  ExternalLink,
  Activity as ActivityIcon
} from 'lucide-react';
import type { Event, Mission } from '../types';
import { ProviderLogo } from '../components/ProviderLogo';

interface ActivityProps {
  events: Event[];
  wsConnected: boolean;
  missions?: Mission[];
  onSelectMission?: (missionId: string) => void;
  onRefresh?: () => void;
}

export const Activity: React.FC<ActivityProps> = ({
  events,
  wsConnected,
  missions = [],
  onSelectMission
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [isStreamPaused, setIsStreamPaused] = useState(false);
  const [frozenEvents, setFrozenEvents] = useState<Event[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Toggle freeze stream
  const handleToggleStream = () => {
    if (!isStreamPaused) {
      setFrozenEvents([...events]);
      setIsStreamPaused(true);
    } else {
      setIsStreamPaused(false);
    }
  };

  const activeEvents = isStreamPaused ? frozenEvents : events;
  const safeEvents = Array.isArray(activeEvents) ? activeEvents : [];

  // Helper to resolve mission title
  const getMissionTitle = (mid?: string | null) => {
    if (!mid) return null;
    const m = missions.find(x => x.id === mid);
    return m ? m.title : mid;
  };

  // Humanized event metadata extraction
  const parseEventDetails = (ev: Event) => {
    const rawType = (ev.event_type || ev.type || '').toLowerCase();
    const payload = ev.payload || {};
    const severity = (ev.severity || 'info').toLowerCase();

    let category = 'SUPERVISOR';
    let icon = Sliders;
    let title = rawType.replace(/[_.]/g, ' ').toUpperCase();
    let summary = 'Supervisory event logged.';
    let agentId = ev.agent_id || payload.agent_id || payload.target_agent || payload.created_by || null;

    if (rawType.includes('mission.created')) {
      category = 'SUPERVISOR';
      icon = Compass;
      title = payload.title ? `Mission Created: "${payload.title}"` : 'Mission Created';
      summary = payload.goal ? `Goal: ${payload.goal}` : 'Mission initialized under supervisory oversight.';
    } else if (rawType.includes('mission.status') || rawType.includes('mission.paused') || rawType.includes('operator')) {
      category = 'SUPERVISOR';
      icon = Sliders;
      title = payload.old_status 
        ? `Mission Status: ${payload.old_status} → ${payload.new_status}`
        : `Mission State: ${payload.status || 'Updated'}`;
      summary = payload.reason ? `Reason: ${payload.reason}` : 'Supervisory policy state update dispatched.';
    } else if (rawType.includes('task.created')) {
      category = 'AGENTS';
      icon = Layers;
      title = payload.title ? `Task Initialized: "${payload.title}"` : `Task Initialized (${ev.task_id || payload.task_id || 'TASK'})`;
      const files = payload.expected_files?.length ? `Files: ${payload.expected_files.join(', ')}` : null;
      summary = files ? `${files} • Order: #${payload.order || 1}` : `Order #${payload.order || 1} awaiting dispatch.`;
    } else if (rawType.includes('task.status') || rawType.includes('task.completed')) {
      category = 'AGENTS';
      icon = CheckCircle2;
      title = `Task ${payload.status || 'Updated'}: "${payload.title || ev.task_id || 'TASK'}"`;
      summary = payload.result_summary || `Task execution transitioned to ${payload.status || 'COMPLETED'}.`;
    } else if (rawType.includes('memory')) {
      category = 'SUPERVISOR';
      icon = Database;
      const catLabel = (payload.category || 'INVARIANT').replace(/_/g, ' ').toUpperCase();
      title = `Memory Invariant: ${catLabel}`;
      summary = payload.fact ? `"${payload.fact}"` : 'Knowledge invariant recorded in supervisory memory.';
    } else if (rawType.includes('watchdog') || rawType.includes('loop') || rawType.includes('anomaly')) {
      category = 'WATCHDOGS';
      icon = ShieldAlert;
      title = 'Watchdog Loop Interception';
      summary = payload.reason || payload.failure_signature 
        ? `Repeated failure signature: ${payload.failure_signature || payload.reason}`
        : 'Worker agent paused after repetitive failure signatures detected.';
    } else if (rawType.includes('handoff')) {
      category = 'HANDOFFS';
      icon = ArrowRightLeft;
      title = 'Agent Handoff Routed';
      summary = payload.reason || 'Context package frozen and handed off to target specialist runtime.';
    } else if (rawType.includes('verif')) {
      category = 'VERIFICATION';
      icon = CheckCircle2;
      const passed = payload.passed !== false && !rawType.includes('fail') && !rawType.includes('reject');
      title = passed ? 'Independent Verification Certified' : 'Verification Rejection Recorded';
      summary = payload.reason || (payload.tests_run 
        ? `${payload.tests_run} tests executed in isolated worktree sandbox without side effects.`
        : 'Authoritative test perimeter executed.');
    } else if (rawType.includes('approval')) {
      category = 'APPROVALS';
      icon = Lock;
      title = `Mandatory Approval Gate: ${payload.action_type || 'Operator Clearance'}`;
      summary = payload.reason || 'Operator sign-off required before execution can proceed.';
    }

    return {
      category,
      icon,
      title,
      summary,
      agentId,
      rawType,
      severity
    };
  };

  // KPI Metrics calculation
  const metrics = useMemo(() => {
    let watchdogs = 0;
    let verifications = 0;
    let agentTasks = 0;

    safeEvents.forEach(ev => {
      const t = (ev.event_type || ev.type || '').toLowerCase();
      if (t.includes('watchdog') || t.includes('loop') || t.includes('anomaly')) watchdogs++;
      if (t.includes('verif')) verifications++;
      if (t.includes('task') || t.includes('agent')) agentTasks++;
    });

    return {
      total: safeEvents.length,
      watchdogs,
      verifications,
      agentTasks
    };
  }, [safeEvents]);

  // Filtering
  const filteredEvents = useMemo(() => {
    return safeEvents.filter(ev => {
      const { category, severity, rawType, title, summary, agentId } = parseEventDetails(ev);

      // Category filter
      if (categoryFilter !== 'ALL') {
        if (categoryFilter !== category) return false;
      }

      // Severity filter
      if (severityFilter !== 'ALL') {
        if (severityFilter === 'CRITICAL' && severity !== 'critical' && severity !== 'error') return false;
        if (severityFilter === 'WARNING' && severity !== 'warning') return false;
        if (severityFilter === 'SUCCESS' && severity !== 'success') return false;
        if (severityFilter === 'INFO' && severity !== 'info') return false;
      }

      // Search query filter
      if (searchTerm) {
        const q = searchTerm.toLowerCase();
        const inTitle = title.toLowerCase().includes(q);
        const inSummary = summary.toLowerCase().includes(q);
        const inType = rawType.includes(q);
        const inMission = (ev.mission_id || '').toLowerCase().includes(q);
        const inTask = (ev.task_id || '').toLowerCase().includes(q);
        const inAgent = (agentId || '').toLowerCase().includes(q);
        const inPayload = JSON.stringify(ev.payload || {}).toLowerCase().includes(q);

        return inTitle || inSummary || inType || inMission || inTask || inAgent || inPayload;
      }

      return true;
    });
  }, [safeEvents, categoryFilter, severityFilter, searchTerm]);

  // Selected event for deep inspector
  const selectedEvent = useMemo(() => {
    if (!selectedEventId) return filteredEvents[0] || null;
    return safeEvents.find(e => (e.id || e.event_id) === selectedEventId) || filteredEvents[0] || null;
  }, [selectedEventId, safeEvents, filteredEvents]);

  const handleCopyJson = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleExportAll = () => {
    const jsonStr = JSON.stringify(filteredEvents, null, 2);
    handleCopyJson(jsonStr, 'all');
  };

  const filterTabs = [
    { id: 'ALL', label: 'All Events', count: safeEvents.length },
    { id: 'SUPERVISOR', label: 'Supervisor', count: safeEvents.filter(e => parseEventDetails(e).category === 'SUPERVISOR').length },
    { id: 'AGENTS', label: 'Agents & Tasks', count: safeEvents.filter(e => parseEventDetails(e).category === 'AGENTS').length },
    { id: 'WATCHDOGS', label: 'Watchdogs & Loops', count: safeEvents.filter(e => parseEventDetails(e).category === 'WATCHDOGS').length },
    { id: 'HANDOFFS', label: 'Handoffs', count: safeEvents.filter(e => parseEventDetails(e).category === 'HANDOFFS').length },
    { id: 'VERIFICATION', label: 'Verification', count: safeEvents.filter(e => parseEventDetails(e).category === 'VERIFICATION').length },
    { id: 'APPROVALS', label: 'Approvals & Gates', count: safeEvents.filter(e => parseEventDetails(e).category === 'APPROVALS').length }
  ];

  return (
    <div className="activity-container">
      {/* Top Header */}
      <div className="page-header" style={{ marginBottom: 0 }}>
        <div className="page-header-title">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h1>Activity & Audit Log</h1>
            <span className="status-pill">
              <span className={`status-dot ${isStreamPaused ? 'watching' : wsConnected ? 'active' : 'offline'}`} />
              <span style={{ fontSize: '11px', fontWeight: 600 }}>
                {isStreamPaused ? 'Stream Paused' : wsConnected ? 'Live Real-Time' : 'Offline'}
              </span>
            </span>
          </div>
          <p>Immutable supervisory audit record of agent decisions, loop watchdog interventions, memory invariants, and independent verification certifications.</p>
        </div>

        <div className="page-header-actions" style={{ display: 'flex', gap: '8px' }}>
          <button 
            className={`btn btn-sm ${isStreamPaused ? 'btn-primary' : 'btn-secondary'}`}
            onClick={handleToggleStream}
            title={isStreamPaused ? 'Resume live WebSocket stream' : 'Pause stream to freeze and inspect activity'}
          >
            {isStreamPaused ? <Play size={13} /> : <Pause size={13} />}
            <span>{isStreamPaused ? 'Resume Stream' : 'Pause Stream'}</span>
          </button>

          <button 
            className="btn btn-secondary btn-sm"
            onClick={handleExportAll}
            title="Copy all currently filtered events to clipboard as formatted JSON"
          >
            {copiedId === 'all' ? <Check size={13} color="var(--success)" /> : <Copy size={13} />}
            <span>{copiedId === 'all' ? 'Copied Log!' : 'Export JSON'}</span>
          </button>
        </div>
      </div>

      {/* 4-KPI Overview Bar */}
      <div className="activity-kpi-bar">
        <div className="activity-kpi-card">
          <div>
            <div className="activity-kpi-val">{metrics.total}</div>
            <div className="activity-kpi-label">Audited Events</div>
          </div>
          <ActivityIcon size={22} color="var(--primary)" />
        </div>

        <div className="activity-kpi-card">
          <div>
            <div className="activity-kpi-val" style={{ color: metrics.watchdogs > 0 ? '#fbbf24' : 'var(--text-primary)' }}>
              {metrics.watchdogs}
            </div>
            <div className="activity-kpi-label">Watchdog Interceptions</div>
          </div>
          <ShieldAlert size={22} color={metrics.watchdogs > 0 ? '#fbbf24' : 'var(--text-muted)'} />
        </div>

        <div className="activity-kpi-card">
          <div>
            <div className="activity-kpi-val" style={{ color: 'var(--success)' }}>
              {metrics.verifications}
            </div>
            <div className="activity-kpi-label">Independent Verifications</div>
          </div>
          <CheckCircle2 size={22} color="var(--success)" />
        </div>

        <div className="activity-kpi-card">
          <div>
            <div className="activity-kpi-val">{metrics.agentTasks}</div>
            <div className="activity-kpi-label">Task Dispatches</div>
          </div>
          <Layers size={22} color="var(--text-secondary)" />
        </div>
      </div>

      {/* Controls & Filter Bar */}
      <div className="activity-filter-bar">
        {/* Category Tabs */}
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {filterTabs.map(tab => (
            <button
              key={tab.id}
              className={`btn btn-sm ${categoryFilter === tab.id ? 'btn-primary' : 'btn-ghost'}`}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              onClick={() => setCategoryFilter(tab.id)}
            >
              <span>{tab.label}</span>
              <span className={`badge ${categoryFilter === tab.id ? 'badge-neutral' : 'badge-blue'}`} style={{ fontSize: '10px', padding: '1px 5px' }}>
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        {/* Severity Selector & Search Bar */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Severity Chips */}
          <div style={{ display: 'flex', gap: '4px', backgroundColor: 'var(--surface)', padding: '2px 4px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            {[
              { id: 'ALL', label: 'All Sev' },
              { id: 'CRITICAL', label: 'Errors' },
              { id: 'WARNING', label: 'Warnings' },
              { id: 'SUCCESS', label: 'Success' },
              { id: 'INFO', label: 'Info' }
            ].map(sev => (
              <button
                key={sev.id}
                className="btn btn-ghost btn-sm"
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  borderRadius: 'var(--radius-xs)',
                  backgroundColor: severityFilter === sev.id ? 'var(--surface-elevated)' : 'transparent',
                  color: severityFilter === sev.id ? 'var(--text-primary)' : 'var(--text-muted)',
                  fontWeight: severityFilter === sev.id ? 600 : 400
                }}
                onClick={() => setSeverityFilter(sev.id)}
              >
                {sev.label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div style={{ position: 'relative', width: '260px' }}>
            <input
              type="text"
              placeholder="Search by event, payload, agent..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              style={{ width: '100%', paddingLeft: '32px', paddingRight: searchTerm ? '28px' : '10px' }}
            />
            <Search size={14} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
            {searchTerm && (
              <button 
                onClick={() => setSearchTerm('')}
                style={{ position: 'absolute', right: '8px', top: '9px', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={13} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Main Split Layout: Activity Feed + Inspector Drawer */}
      {filteredEvents.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <Compass size={20} />
          </div>
          <div className="empty-state-title">No matching activity records</div>
          <div className="empty-state-desc">
            {searchTerm 
              ? `No audit events matched "${searchTerm}".` 
              : 'No events found for this filter category. Trigger a mission in Control Room to start receiving live telemetry.'}
          </div>
        </div>
      ) : (
        <div className="activity-split-grid">
          {/* Left: Interactive Feed */}
          <div className="activity-feed">
            {filteredEvents.map((ev, idx) => {
              const evId = ev.id || ev.event_id || `evt-${idx}`;
              const { icon: Icon, title, summary, agentId, severity } = parseEventDetails(ev);
              const isSelected = selectedEvent && (selectedEvent.id || selectedEvent.event_id) === evId;
              const missionName = getMissionTitle(ev.mission_id);

              return (
                <div
                  key={evId}
                  className={`activity-event-card severity-${severity} ${isSelected ? 'selected' : ''}`}
                  onClick={() => setSelectedEventId(evId)}
                >
                  {/* Card Header */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                      <div style={{
                        width: '28px',
                        height: '28px',
                        borderRadius: 'var(--radius-sm)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: severity === 'error' || severity === 'critical'
                          ? 'rgba(239, 68, 68, 0.15)'
                          : severity === 'warning'
                            ? 'rgba(245, 158, 11, 0.15)'
                            : severity === 'success'
                              ? 'rgba(16, 185, 129, 0.15)'
                              : 'rgba(52, 120, 246, 0.15)',
                        color: severity === 'error' || severity === 'critical'
                          ? 'var(--danger)'
                          : severity === 'warning'
                            ? 'var(--warning)'
                            : severity === 'success'
                              ? 'var(--success)'
                              : 'var(--primary)',
                        flexShrink: 0
                      }}>
                        <Icon size={15} />
                      </div>

                      <div style={{ minWidth: 0 }}>
                        <div style={{ 
                          fontSize: '13.5px', 
                          fontWeight: 600, 
                          color: 'var(--text-primary)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}>
                          {title}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
                      <span className={`badge ${
                        severity === 'error' || severity === 'critical'
                          ? 'badge-red'
                          : severity === 'warning'
                            ? 'badge-amber'
                            : severity === 'success'
                              ? 'badge-green'
                              : 'badge-neutral'
                      }`} style={{ fontSize: '10px' }}>
                        {severity.toUpperCase()}
                      </span>

                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                    </div>
                  </div>

                  {/* Card Description */}
                  <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {summary}
                  </div>

                  {/* Card Footer Badges */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', paddingTop: '4px' }}>
                    {/* Mission Badge */}
                    {ev.mission_id && (
                      <span 
                        className="badge badge-neutral" 
                        style={{ fontSize: '10.5px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        onClick={(e) => {
                          if (onSelectMission && ev.mission_id) {
                            e.stopPropagation();
                            onSelectMission(ev.mission_id);
                          }
                        }}
                        title="Click to view mission in Missions view"
                      >
                        <Compass size={11} color="var(--primary)" />
                        <span>{missionName ? `${missionName} (${ev.mission_id})` : ev.mission_id}</span>
                      </span>
                    )}

                    {/* Task Badge */}
                    {ev.task_id && (
                      <span className="badge badge-neutral" style={{ fontSize: '10.5px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Layers size={11} />
                        <span>{ev.task_id}</span>
                      </span>
                    )}

                    {/* Agent Badge with authentic logo */}
                    {agentId && (
                      <span className="badge badge-neutral" style={{ fontSize: '10.5px', display: 'flex', alignItems: 'center', gap: '5px' }}>
                        <ProviderLogo providerId={agentId} size={13} />
                        <span style={{ fontFamily: 'var(--font-mono)' }}>{agentId}</span>
                      </span>
                    )}

                    {/* Raw Event Tag */}
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginLeft: 'auto' }}>
                      {ev.event_type || ev.type}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right: Live Event Detail Inspector */}
          {selectedEvent && (() => {
            const evId = selectedEvent.id || selectedEvent.event_id || 'evt-selected';
            const { icon: Icon, title, summary, agentId, rawType, severity } = parseEventDetails(selectedEvent);
            const missionName = getMissionTitle(selectedEvent.mission_id);
            const jsonText = JSON.stringify(selectedEvent.payload || {}, null, 2);

            return (
              <div className="activity-inspector-card">
                {/* Inspector Header */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '10px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: 'var(--radius-sm)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: 'rgba(52, 120, 246, 0.15)',
                      color: 'var(--primary)',
                      flexShrink: 0
                    }}>
                      <Icon size={17} />
                    </div>
                    <div>
                      <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
                        Event Inspector
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {evId}
                      </div>
                    </div>
                  </div>

                  <span className={`badge ${
                    severity === 'error' || severity === 'critical'
                      ? 'badge-red'
                      : severity === 'warning'
                        ? 'badge-amber'
                        : severity === 'success'
                          ? 'badge-green'
                          : 'badge-neutral'
                  }`}>
                    {severity.toUpperCase()}
                  </span>
                </div>

                {/* Event Title & Summary */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {title}
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {summary}
                  </div>
                </div>

                {/* Key Context Grid */}
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '10px',
                  padding: '12px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: 'var(--surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '11.5px'
                }}>
                  <div>
                    <div style={{ color: 'var(--text-muted)', marginBottom: '2px' }}>Event Type</div>
                    <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 600 }}>
                      {rawType}
                    </div>
                  </div>

                  <div>
                    <div style={{ color: 'var(--text-muted)', marginBottom: '2px' }}>Timestamp</div>
                    <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                      {new Date(selectedEvent.timestamp).toLocaleTimeString()}
                    </div>
                  </div>

                  {agentId && (
                    <div>
                      <div style={{ color: 'var(--text-muted)', marginBottom: '2px' }}>Assigned Agent</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <ProviderLogo providerId={agentId} size={14} />
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{agentId}</span>
                      </div>
                    </div>
                  )}

                  {selectedEvent.task_id && (
                    <div>
                      <div style={{ color: 'var(--text-muted)', marginBottom: '2px' }}>Task Reference</div>
                      <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--primary)' }}>
                        {selectedEvent.task_id}
                      </div>
                    </div>
                  )}
                </div>

                {/* Mission Link */}
                {selectedEvent.mission_id && (
                  <div style={{
                    padding: '10px 12px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'rgba(52, 120, 246, 0.08)',
                    border: '1px solid rgba(52, 120, 246, 0.2)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '10px'
                  }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '10.5px', color: 'var(--primary)', fontWeight: 600, textTransform: 'uppercase' }}>
                        Associated Mission
                      </div>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {missionName || selectedEvent.mission_id}
                      </div>
                    </div>

                    {onSelectMission && (
                      <button 
                        className="btn btn-primary btn-sm"
                        style={{ fontSize: '11px', padding: '4px 8px', flexShrink: 0 }}
                        onClick={() => onSelectMission(selectedEvent.mission_id!)}
                      >
                        <span>Open</span>
                        <ExternalLink size={11} />
                      </button>
                    )}
                  </div>
                )}

                {/* Raw Payload Inspector */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Payload Data
                    </span>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ fontSize: '11px', padding: '2px 6px' }}
                      onClick={() => handleCopyJson(jsonText, evId)}
                    >
                      {copiedId === evId ? <Check size={12} color="var(--success)" /> : <Copy size={12} />}
                      <span>{copiedId === evId ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>

                  <pre className="activity-payload-pre">
                    {jsonText}
                  </pre>
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
};
