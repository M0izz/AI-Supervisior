import React, { useState, useEffect } from 'react';
import { 
  Target, 
  Play, 
  Pause, 
  CheckCircle2, 
  Bot, 
  FileCode, 
  ArrowLeft, 
  Plus, 
  Search, 
  ShieldCheck, 
  Layers, 
  Lock,
  Compass
} from 'lucide-react';
import type { Mission, Task } from '../types';
import { 
  pauseMission, 
  resumeMission, 
  getMissionTasks, 
  getMissionEvents,
  getMissionAbsence
} from '../api';

interface MissionsProps {
  missions: Mission[];
  selectedMissionId: string | null;
  onSelectMission: (id: string | null) => void;
  onRefresh: () => void;
  onOpenCreateMission: () => void;
}

export const Missions: React.FC<MissionsProps> = ({
  missions,
  selectedMissionId,
  onSelectMission,
  onRefresh,
  onOpenCreateMission
}) => {
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [absenceInfo, setAbsenceInfo] = useState<any>(null);
  const [isActing, setIsActing] = useState(false);
  const [activeTab, setActiveTab] = useState<'timeline' | 'tasks' | 'verification' | 'absence'>('timeline');

  const safeMissions = Array.isArray(missions) ? missions : [];
  const selectedMission = safeMissions.find(m => m.id === selectedMissionId);

  // Load tasks and events when selected mission changes
  useEffect(() => {
    if (!selectedMission) return;

    // Load tasks
    if (selectedMission.tasks && selectedMission.tasks.length > 0) {
      setTasks(selectedMission.tasks);
    } else {
      getMissionTasks(selectedMission.id)
        .then(res => {
          if (res?.tasks) setTasks(res.tasks);
        })
        .catch(() => setTasks([]));
    }

    // Load mission timeline events
    getMissionEvents(selectedMission.id, 50)
      .then(res => {
        if (Array.isArray(res)) setEvents(res);
      })
      .catch(() => setEvents([]));

    // Load absence mode state
    getMissionAbsence(selectedMission.id)
      .then(res => setAbsenceInfo(res))
      .catch(() => setAbsenceInfo(null));
  }, [selectedMission]);

  // Handle Pause/Resume
  const handleTogglePause = async () => {
    if (!selectedMission) return;
    setIsActing(true);
    try {
      if (selectedMission.status === 'PAUSED') {
        await resumeMission(selectedMission.id);
      } else {
        await pauseMission(selectedMission.id, 'Operator paused from mission detail view');
      }
      onRefresh();
    } finally {
      setIsActing(false);
    }
  };

  // Filtered missions list
  const filteredMissions = safeMissions.filter(m => {
    if (filterStatus === 'ACTIVE') {
      if (!['RUNNING', 'INVESTIGATING', 'RECOVERING', 'VERIFYING', 'WAITING_APPROVAL'].includes(m.status)) return false;
    } else if (filterStatus === 'COMPLETED') {
      if (m.status !== 'COMPLETED') return false;
    } else if (filterStatus === 'FAILED') {
      if (m.status !== 'FAILED') return false;
    }

    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return m.title.toLowerCase().includes(q) || m.goal.toLowerCase().includes(q) || m.id.toLowerCase().includes(q);
    }
    return true;
  });

  // =========================================================================
  // MISSION DETAIL VIEW
  // =========================================================================
  if (selectedMission) {
    const assigned = selectedMission.assigned_agents || selectedMission.assigned_agent_ids || [];
    const completedTasksCount = tasks.filter(t => t.status === 'COMPLETED' || t.status === 'VERIFIED').length;
    const totalTasksCount = tasks.length || 1;
    const progressPercent = Math.min(100, Math.round((completedTasksCount / totalTasksCount) * 100));

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1080px' }}>
        {/* Top Back Nav & Actions */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button 
            className="btn btn-ghost btn-sm"
            onClick={() => onSelectMission(null)}
            style={{ color: 'var(--text-secondary)' }}
          >
            <ArrowLeft size={14} />
            <span>Back to All Missions</span>
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={handleTogglePause}
              disabled={isActing}
            >
              {selectedMission.status === 'PAUSED' ? <Play size={13} /> : <Pause size={13} />}
              <span>{selectedMission.status === 'PAUSED' ? 'Resume Mission' : 'Pause'}</span>
            </button>
          </div>
        </div>

        {/* Mission Title Card */}
        <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <h1 style={{ fontSize: '22px' }}>{selectedMission.title}</h1>
                <span className="status-pill">
                  <span className={`status-dot ${selectedMission.status === 'RUNNING' ? 'running' : selectedMission.status === 'COMPLETED' ? 'active' : 'waiting'}`} />
                  <span>{selectedMission.status.toLowerCase()}</span>
                </span>
              </div>
              <p style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '780px' }}>
                {selectedMission.goal}
              </p>
            </div>

            <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Assigned Agents</div>
              <div style={{ fontSize: '13px', fontWeight: 500, fontFamily: 'var(--font-mono)' }}>
                {assigned.length > 0 ? assigned.join(' → ') : 'Claude Code'}
              </div>
            </div>
          </div>

          {/* Progress Bar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-muted)' }}>
              <span>Task Progress</span>
              <span>{completedTasksCount} of {tasks.length} tasks completed ({progressPercent}%)</span>
            </div>
            <div style={{ height: '6px', backgroundColor: 'var(--surface-elevated)', borderRadius: '3px', overflow: 'hidden' }}>
              <div style={{ width: `${progressPercent}%`, height: '100%', backgroundColor: 'var(--primary)', transition: 'width 0.3s ease' }} />
            </div>
          </div>
        </div>

        {/* Detail Tabs */}
        <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '4px' }}>
          {[
            { id: 'timeline', label: 'Mission Story & Timeline', icon: Compass },
            { id: 'tasks', label: `Tasks (${tasks.length})`, icon: Layers },
            { id: 'verification', label: 'Independent Verification', icon: ShieldCheck },
            { id: 'absence', label: 'Absence Mode Policy', icon: Lock }
          ].map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                className={`btn btn-sm ${isActive ? 'btn-secondary' : 'btn-ghost'}`}
                style={{ borderBottom: isActive ? '2px solid var(--primary)' : 'none', borderRadius: '4px 4px 0 0' }}
                onClick={() => setActiveTab(tab.id as any)}
              >
                <Icon size={13} color={isActive ? 'var(--primary)' : 'var(--text-muted)'} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab 1: Timeline Story */}
        {activeTab === 'timeline' && (
          <div className="surface-card" style={{ padding: '20px' }}>
            {events.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center', padding: '24px' }}>
                No events recorded for this mission yet. Tasks are scheduled to run.
              </div>
            ) : (
              <div className="timeline-container">
                {events.map((ev, idx) => {
                  const eType = ev.event_type || ev.type || 'Event';
                  const isWarning = eType.includes('FAIL') || eType.includes('ANOMALY') || eType.includes('REJECT');
                  const isSuccess = eType.includes('PASS') || eType.includes('VERIFIED') || eType.includes('COMPLETED');
                  const isHandoff = eType.includes('HANDOFF') || eType.includes('INTERVENTION');

                  return (
                    <div key={idx} className="timeline-event">
                      <div className={`timeline-event-marker ${isWarning ? 'warning' : isSuccess ? 'success' : isHandoff ? 'warning' : 'info'}`} />
                      <div className="timeline-event-header">
                        <span className="timeline-event-title">{eType.replace(/_/g, ' ')}</span>
                        <span className="timeline-event-time">
                          {new Date(ev.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <div className="timeline-event-desc">
                        {ev.payload?.reason || ev.payload?.description || ev.payload?.message || JSON.stringify(ev.payload || {})}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Tasks List */}
        {activeTab === 'tasks' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {tasks.length === 0 ? (
              <div className="empty-state">
                <Layers size={18} />
                <div className="empty-state-title">No tasks generated yet</div>
                <div className="empty-state-desc">The Supervisor decomposes goals into a directed acyclic task graph.</div>
              </div>
            ) : (
              tasks.map((task, idx) => (
                <div key={task.id || idx} className="surface-card" style={{ padding: '14px 16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span className={`status-dot ${task.status === 'COMPLETED' ? 'active' : task.status === 'IN_PROGRESS' ? 'running' : 'idle'}`} />
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{task.title || task.name}</div>
                    </div>
                    <span className="badge badge-neutral" style={{ fontSize: '11px' }}>{task.status.toLowerCase()}</span>
                  </div>

                  {task.description && (
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '6px' }}>
                      {task.description}
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginTop: '10px', fontSize: '11px', color: 'var(--text-muted)' }}>
                    {task.assigned_agent_id && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Bot size={12} />
                        <span>Agent: {task.assigned_agent_id}</span>
                      </span>
                    )}

                    {task.expected_files && task.expected_files.length > 0 && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <FileCode size={12} />
                        <span>Expected files: {task.expected_files.join(', ')}</span>
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab 3: Verification */}
        {activeTab === 'verification' && (
          <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <div style={{ fontSize: '14px', fontWeight: 600 }}>Independent Verifier Perimeter</div>
              <p style={{ fontSize: '13px', marginTop: '4px' }}>
                Every completed task passes through independent testing and scope validation before the mission is marked verified.
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div style={{ padding: '12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px' }}>
                  <CheckCircle2 size={15} color="var(--success)" />
                  <span>Deterministic Test Runner</span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Executes automated test suites in isolated sandbox. No agent self-certification permitted.
                </div>
              </div>

              <div style={{ padding: '12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px' }}>
                  <ShieldCheck size={15} color="var(--primary)" />
                  <span>Scope & Diff Analysis</span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Verifies that only expected files were modified. Prohibited file writes trigger immediate rollback.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: Absence Mode */}
        {activeTab === 'absence' && (
          <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: '14px', fontWeight: 600 }}>Absence Mode Supervision</div>
                <p style={{ fontSize: '13px', marginTop: '4px' }}>
                  Run missions autonomously while away from keyboard under strict policy limits.
                </p>
              </div>
              <span className={`status-pill ${absenceInfo?.active ? 'running' : 'idle'}`}>
                <span>{absenceInfo?.active ? 'Armed & Active' : 'Standby'}</span>
              </span>
            </div>

            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Policy guarantees: Emergency auto-pause upon error loops, token ceiling limits, no destructive git operations without human signoff, and fail-closed restart reconciliation.
            </div>
          </div>
        )}
      </div>
    );
  }

  // =========================================================================
  // MISSIONS LIST VIEW
  // =========================================================================
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1080px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-title">
          <h1>Missions</h1>
          <p>Autonomous coding tasks under real-time supervision and independent verification</p>
        </div>

        <div className="page-header-actions">
          <button className="btn btn-primary" onClick={onOpenCreateMission}>
            <Plus size={14} />
            <span>New Mission</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          {['ALL', 'ACTIVE', 'COMPLETED', 'FAILED'].map(f => (
            <button
              key={f}
              className={`btn btn-sm ${filterStatus === f ? 'btn-secondary' : 'btn-ghost'}`}
              style={{ fontWeight: filterStatus === f ? 600 : 400 }}
              onClick={() => setFilterStatus(f)}
            >
              {f.toLowerCase()}
            </button>
          ))}
        </div>

        <div style={{ position: 'relative', width: '260px' }}>
          <input
            type="text"
            placeholder="Search missions..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            style={{ width: '100%', paddingLeft: '32px' }}
          />
          <Search size={14} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
        </div>
      </div>

      {/* Missions List */}
      {filteredMissions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <Target size={18} />
          </div>
          <div className="empty-state-title">No missions match your filter</div>
          <div className="empty-state-desc">
            {searchTerm ? `No missions found matching "${searchTerm}".` : 'You have not created any missions yet.'}
          </div>
          <button className="btn btn-primary btn-sm" onClick={onOpenCreateMission} style={{ marginTop: '8px' }}>
            <Plus size={13} />
            <span>Create First Mission</span>
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {filteredMissions.map(m => {
            const assigned = m.assigned_agents || m.assigned_agent_ids || [];
            return (
              <div
                key={m.id}
                className="item-row"
                onClick={() => onSelectMission(m.id)}
              >
                <div className="item-row-primary">
                  <span className={`status-dot ${m.status === 'RUNNING' ? 'running' : m.status === 'COMPLETED' ? 'active' : 'waiting'}`} />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>
                      {m.title}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {m.goal}
                    </div>
                  </div>
                </div>

                <div className="item-row-meta">
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                    {assigned.length > 0 ? assigned.join(' → ') : 'Claude Code'}
                  </span>
                  <span className="badge badge-blue">{m.status.toLowerCase()}</span>
                  <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                    {new Date(m.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
