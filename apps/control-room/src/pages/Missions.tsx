import React, { useState, useEffect } from 'react';
import { 
  Target, 
  Play, 
  Pause, 
  CheckCircle2, 
  ArrowLeft, 
  Plus, 
  Search, 
  ShieldCheck, 
  Layers, 
  Lock, 
  Compass,
  AlertTriangle,
  Code2,
  Sparkles,
  X
} from 'lucide-react';
import type { Mission, Task, SupervisorDecision } from '../types';
import { 
  pauseMission, 
  resumeMission, 
  getMissionTasks, 
  getMissionEvents,
  getMissionAbsence,
  getSupervisorDecisions,
  explainDecision
} from '../api';
import { ProviderLogo } from '../components/ProviderLogo';
import { HandoffSequence } from '../components/HandoffSequence';
import { TaskDAGView } from '../components/TaskDAGView';
import { SupervisorDecisionCard } from '../components/SupervisorDecisionCard';

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
  const [activeTab, setActiveTab] = useState<'story' | 'tasks' | 'verification' | 'policy'>('story');
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
  const [missionDecisions, setMissionDecisions] = useState<SupervisorDecision[]>([]);
  const [explainingDecision, setExplainingDecision] = useState<SupervisorDecision | null>(null);
  const [gemmaExplanation, setGemmaExplanation] = useState<any | null>(null);
  const [isExplaining, setIsExplaining] = useState(false);

  const safeMissions = Array.isArray(missions) ? missions : [];
  const selectedMission = safeMissions.find(m => m.id === selectedMissionId);

  // Load tasks, events, and decisions when selected mission changes
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

    // Load mission decisions
    getSupervisorDecisions(selectedMission.id)
      .then(res => {
        if (res?.decisions) setMissionDecisions(res.decisions);
      })
      .catch(() => setMissionDecisions([]));

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

  // Filtered missions list
  const filteredMissions = safeMissions.filter(m => {
    if (filterStatus === 'ACTIVE') {
      if (!['RUNNING', 'INVESTIGATING', 'RECOVERING', 'VERIFYING', 'WAITING_APPROVAL'].includes(m.status)) return false;
    } else if (filterStatus === 'COMPLETED') {
      if (m.status !== 'COMPLETED') return false;
    } else if (filterStatus === 'NEEDS_ATTENTION') {
      if (!['RECOVERING', 'INVESTIGATING', 'WAITING_APPROVAL', 'PAUSED', 'FAILED'].includes(m.status)) return false;
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

    const isHandoffDetected = events.some(e => 
      (e.event_type || e.type || '').includes('HANDOFF') || 
      (e.event_type || e.type || '').includes('INTERVENTION')
    ) || assigned.length > 1;

    let supervisorStateLabel = 'Supervisor Watching';
    let supervisorDotClass = 'watching';
    if (selectedMission.status === 'COMPLETED') {
      supervisorStateLabel = 'Verified Complete';
      supervisorDotClass = 'active';
    } else if (selectedMission.status === 'RECOVERING' || selectedMission.status === 'INVESTIGATING') {
      supervisorStateLabel = 'Supervisor Intervened';
      supervisorDotClass = 'running';
    } else if (selectedMission.status === 'VERIFYING') {
      supervisorStateLabel = 'Supervisor Verifying';
      supervisorDotClass = 'spin';
    } else if (selectedMission.status === 'PAUSED') {
      supervisorStateLabel = 'Supervision Paused';
      supervisorDotClass = 'idle';
    }

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
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <h1 style={{ fontSize: '22px' }}>{selectedMission.title}</h1>
                <span className="status-pill">
                  <span className={`status-dot ${selectedMission.status === 'RUNNING' ? 'running' : selectedMission.status === 'COMPLETED' ? 'active' : 'idle'}`} />
                  <span>{selectedMission.status.toLowerCase()}</span>
                </span>
              </div>
              <p style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '780px' }}>
                {selectedMission.goal}
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'flex-end' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                <span className={`status-dot ${supervisorDotClass}`} />
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{supervisorStateLabel}</span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '2px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Assigned:</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                  <ProviderLogo providerId={assigned[0] || 'claude-code'} size={15} />
                  <span>{assigned.length > 0 ? assigned.join(' → ') : 'Claude Code'}</span>
                </span>
              </div>
            </div>
          </div>

            {/* 5-Phase Story Flow (Section 32) */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 14px',
              borderRadius: '6px',
              backgroundColor: 'var(--surface-elevated)',
              border: '1px solid var(--border-subtle)',
              fontSize: '12px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: 'var(--success)', fontWeight: 600 }}>✓</span>
                <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>Understand</span>
              </div>
              <span style={{ color: 'var(--text-muted)' }}>&rarr;</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: completedTasksCount >= 1 ? 'var(--success)' : 'var(--text-muted)', fontWeight: 600 }}>
                  {completedTasksCount >= 1 ? '✓' : '●'}
                </span>
                <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>Implement</span>
              </div>
              <span style={{ color: 'var(--text-muted)' }}>&rarr;</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: completedTasksCount >= 2 ? 'var(--success)' : 'var(--primary)', fontWeight: 600 }}>
                  {completedTasksCount >= 2 ? '✓' : '●'}
                </span>
                <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>Test</span>
              </div>
              <span style={{ color: 'var(--text-muted)' }}>&rarr;</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: selectedMission.status === 'COMPLETED' ? 'var(--success)' : 'var(--text-muted)', fontWeight: 600 }}>
                  {selectedMission.status === 'COMPLETED' ? '✓' : '○'}
                </span>
                <span style={{ color: selectedMission.status === 'COMPLETED' ? 'var(--text-primary)' : 'var(--text-muted)' }}>Verify</span>
              </div>
              <span style={{ color: 'var(--text-muted)' }}>&rarr;</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: selectedMission.status === 'COMPLETED' ? 'var(--success)' : 'var(--text-muted)', fontWeight: 600 }}>
                  {selectedMission.status === 'COMPLETED' ? '✓' : '○'}
                </span>
                <span style={{ color: selectedMission.status === 'COMPLETED' ? 'var(--text-primary)' : 'var(--text-muted)' }}>Complete</span>
              </div>
            </div>

            {/* Progress Bar & Summary Stats */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', paddingTop: '10px', borderTop: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-muted)' }}>
                <span>Supervised Execution Progress</span>
                <span>{completedTasksCount} of {tasks.length} tasks completed ({progressPercent}%)</span>
              </div>
              <div style={{ height: '6px', backgroundColor: 'var(--surface-elevated)', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{ width: `${progressPercent}%`, height: '100%', backgroundColor: 'var(--primary)', transition: 'width 0.3s ease' }} />
              </div>
            </div>
          </div>

          {/* What Supervisor Understood (Product Topology Section 10) */}
          <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderLeft: '3px solid var(--primary)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={15} color="var(--primary)" />
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.02em', textTransform: 'uppercase' }}>
                  What Supervisor Understood
                </span>
              </div>
              <span className="badge badge-neutral" style={{ fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span>Intelligence:</span>
                <strong style={{ color: 'var(--text-primary)' }}>Google Gemma 4</strong>
              </span>
            </div>

            <div style={{ fontSize: '14px', color: 'var(--text-primary)', lineHeight: 1.5, fontWeight: 500 }}>
              &ldquo;{selectedMission.goal}&rdquo;
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '10px', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)', fontSize: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ color: 'var(--text-muted)', fontWeight: 600, fontSize: '11px' }}>DETECTED CONSTRAINTS</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', color: 'var(--text-secondary)' }}>
                  <span>• Scope restricted to repository worktree boundaries</span>
                  <span>• Existing test suites and contract invariants must pass</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ color: 'var(--text-muted)', fontWeight: 600, fontSize: '11px' }}>SUPERVISION STRATEGY</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', color: 'var(--text-secondary)' }}>
                  <span>• Active loop watchdog (pause on 3 repetitive failure signatures)</span>
                  <span>• Independent verification perimeter before completing</span>
                </div>
              </div>
            </div>
          </div>

          {/* Detail Tabs */}
          <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '4px' }}>
            {[
              { id: 'story', label: 'Mission Story & Handoffs', icon: Compass },
              { id: 'tasks', label: `Execution Plan (${tasks.length})`, icon: Layers },
              { id: 'verification', label: 'Independent Verification', icon: ShieldCheck },
              { id: 'policy', label: 'Autonomy & Policies', icon: Lock }
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

        {/* Tab 1: Timeline Story & Handoffs */}
        {activeTab === 'story' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Structured Supervisor Decisions */}
            {missionDecisions.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Supervisory Decisions & Interventions ({missionDecisions.length})
                </div>
                {missionDecisions.map(dec => (
                  <SupervisorDecisionCard
                    key={dec.id}
                    decision={dec}
                    onExplain={handleExplainDecision}
                  />
                ))}
              </div>
            )}

            {/* Show Handoff Sequence if handoff occurred or multiple agents assigned */}
            {isHandoffDetected && (
              <HandoffSequence
                sourceAgent={assigned[0] || 'claude-code'}
                targetAgent={assigned[1] || 'codex'}
                reason="Watchdog detected repeated test failure loop (3 identical stack traces). Supervisor paused worker, preserved AST diff, and routed handoff."
                isCompleted={selectedMission.status === 'COMPLETED'}
              />
            )}

            <div className="surface-card" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Human Execution Story
                </div>
                <span className="badge badge-neutral" style={{ fontSize: '11px' }}>
                  {events.length} supervisory milestones
                </span>
              </div>

              {events.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center', padding: '24px' }}>
                  Mission initialized. Supervisor is orchestrating execution tasks and attaching live watchdogs.
                </div>
              ) : (
                <div className="timeline-container">
                  {events.map((ev, idx) => {
                    const eType = ev.event_type || ev.type || 'Event';
                    const isWarning = eType.includes('FAIL') || eType.includes('ANOMALY') || eType.includes('REJECT') || eType.includes('LOOP');
                    const isSuccess = eType.includes('PASS') || eType.includes('VERIFIED') || eType.includes('COMPLETED');
                    const isHandoff = eType.includes('HANDOFF') || eType.includes('INTERVENTION');

                    // Human-readable plain language title
                    let storyTitle = eType.replace(/_/g, ' ');
                    if (eType.includes('MISSION_CREATED')) storyTitle = 'Supervisor Planned Mission';
                    else if (eType.includes('TASK_STARTED')) storyTitle = 'Agent Started Task Execution';
                    else if (eType.includes('WATCHDOG_TRIGGERED')) storyTitle = 'Watchdog Intervened on Loop';
                    else if (eType.includes('HANDOFF')) storyTitle = 'Supervisor Routed Handoff';
                    else if (eType.includes('VERIFICATION_PASSED')) storyTitle = 'Independent Verification Succeeded';

                    const evKey = ev.id || `${idx}-${ev.timestamp}`;
                    const isExpanded = expandedEventId === evKey;

                    return (
                      <div key={idx} className="timeline-event">
                        <div className={`timeline-event-marker ${isWarning ? 'warning' : isSuccess ? 'success' : isHandoff ? 'warning' : 'info'}`} />
                        <div className="timeline-event-header">
                          <span className="timeline-event-title">{storyTitle}</span>
                          <span className="timeline-event-time">
                            {new Date(ev.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                        <div className="timeline-event-desc">
                          {ev.payload?.reason || ev.payload?.description || ev.payload?.message || 'Supervisory event'}
                        </div>

                        {/* Progressive Disclosure of Technical Payload */}
                        <div style={{ marginTop: '6px' }}>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            style={{ padding: '2px 0', fontSize: '11px', color: 'var(--text-muted)' }}
                            onClick={() => setExpandedEventId(isExpanded ? null : evKey)}
                          >
                            <Code2 size={11} />
                            <span>{isExpanded ? 'Hide technical payload' : 'View technical details'}</span>
                          </button>

                          {isExpanded && (
                            <pre style={{
                              marginTop: '6px',
                              padding: '10px',
                              borderRadius: '4px',
                              backgroundColor: 'var(--bg)',
                              border: '1px solid var(--border-subtle)',
                              fontSize: '11px',
                              color: 'var(--text-secondary)',
                              overflowX: 'auto',
                              maxHeight: '180px'
                            }}>
                              {JSON.stringify(ev, null, 2)}
                            </pre>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Task Graph (Visual DAG) */}
        {activeTab === 'tasks' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Visual Flow Pipeline */}
            <div className="surface-card" style={{ padding: '14px 18px', backgroundColor: 'var(--surface-elevated)' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
                SUPERVISED EXECUTION PIPELINE
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', fontSize: '12px' }}>
                <span className="badge badge-blue">1. Understand</span>
                <span style={{ color: 'var(--text-muted)' }}>→</span>
                <span className="badge badge-blue">2. Plan & Decompose</span>
                <span style={{ color: 'var(--text-muted)' }}>→</span>
                <span className={`badge ${selectedMission.status === 'RUNNING' ? 'badge-amber' : 'badge-neutral'}`}>3. Execute</span>
                <span style={{ color: 'var(--text-muted)' }}>→</span>
                <span className="badge badge-blue">4. Watchdogs</span>
                <span style={{ color: 'var(--text-muted)' }}>→</span>
                <span className={`badge ${selectedMission.status === 'COMPLETED' ? 'badge-green' : 'badge-neutral'}`}>5. Independent Verification</span>
              </div>
            </div>

            {/* Task DAG View Component */}
            <TaskDAGView tasks={tasks} />
          </div>
        )}

        {/* Tab 3: Verification (Independent Verification Perimeter) */}
        {activeTab === 'verification' && (
          <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShieldCheck size={20} color="var(--primary)" />
                  <h2 style={{ fontSize: '16px', fontWeight: 600 }}>Independent Verification Perimeter</h2>
                </div>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  The agent does not decide if its own work is complete. The Supervisor executes an independent test suite, validates AST diffs, and inspects git state before certifying.
                </p>
              </div>

              <span className={`badge ${selectedMission.status === 'COMPLETED' ? 'badge-green' : selectedMission.status === 'FAILED' ? 'badge-red' : 'badge-blue'}`}>
                {selectedMission.status === 'COMPLETED' ? 'ALL VERIFIED' : selectedMission.status === 'FAILED' ? 'REJECTED' : 'SUPERVISION ACTIVE'}
              </span>
            </div>

            {/* 6-Point Verification Checklist */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
              {[
                { name: 'Deterministic Test Suite', desc: 'Automated pytest / unit test suite executed in isolated worktree sandbox.', verified: selectedMission.status === 'COMPLETED' },
                { name: 'Allowed File Boundary', desc: 'Ensures agent only edited files declared in mission scope without side effects.', verified: selectedMission.status === 'COMPLETED' },
                { name: 'Scope & AST Invariant Checks', desc: 'No unintended mutations, no prohibited library imports, and zero leaks.', verified: selectedMission.status === 'COMPLETED' },
                { name: 'Git State Cleanliness', desc: 'Worktree verified clean; no temporary debug artefacts or leftover secret tokens.', verified: selectedMission.status === 'COMPLETED' },
                { name: 'Completion Claim Audit', desc: 'Cross-checks agent output against required task deliverables and outputs.', verified: selectedMission.status === 'COMPLETED' },
                { name: 'Regression Test Perimeter', desc: 'Baseline regression tests pass with zero newly failing test cases.', verified: selectedMission.status === 'COMPLETED' },
              ].map(check => (
                <div 
                  key={check.name} 
                  style={{ 
                    padding: '14px', 
                    borderRadius: '6px', 
                    backgroundColor: 'var(--surface-elevated)', 
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <CheckCircle2 size={15} color={check.verified ? 'var(--success)' : 'var(--text-muted)'} />
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {check.name}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', paddingLeft: '23px' }}>
                    {check.desc}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '8px', 
              padding: '12px 14px', 
              borderRadius: '6px', 
              backgroundColor: 'rgba(59, 130, 246, 0.05)', 
              border: '1px solid rgba(59, 130, 246, 0.15)',
              fontSize: '12px', 
              color: 'var(--text-secondary)' 
            }}>
              <CheckCircle2 size={16} color="var(--primary)" style={{ flexShrink: 0 }} />
              <span>Independent verification is authoritative. If an agent attempts to claim completion while tests fail, the Supervisor rejects the result and triggers rollback or handoff.</span>
            </div>
          </div>
        )}

        {/* Tab 4: Policy & Absence Mode */}
        {activeTab === 'policy' && (
          <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <h2 style={{ fontSize: '16px', fontWeight: 600 }}>Supervisory Policy & Absence Perimeter</h2>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Safety gates, maximum turn limits, and absence mode arming for this mission.
                </p>
              </div>
              <span className={`status-pill ${absenceInfo?.active ? 'running' : 'idle'}`}>
                <span>{absenceInfo?.active ? 'Armed & Active' : 'Standby'}</span>
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginTop: '4px' }}>
              <div style={{ padding: '14px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Watchdog Policy</div>
                <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '2px', color: 'var(--text-primary)' }}>
                  Active Loop Interception
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Pauses worker after 3 identical failure signatures.
                </div>
              </div>

              <div style={{ padding: '14px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Workspace Sandbox</div>
                <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '2px', color: 'var(--text-primary)' }}>
                  Isolated Worktree
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Main branch untouched until independent verification passes.
                </div>
              </div>

              <div style={{ padding: '14px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Turn Ceiling</div>
                <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '2px', color: 'var(--text-primary)' }}>
                  10 Turns Max Budget
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Prevents runaway token or command consumption.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Gemma 4 Decision Explanation Modal */}
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

              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary btn-sm" onClick={() => setExplainingDecision(null)}>
                  Close
                </button>
              </div>
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
            <span>Start a Mission</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          {[
            { id: 'ALL', label: 'All' },
            { id: 'ACTIVE', label: 'Active' },
            { id: 'COMPLETED', label: 'Completed' },
            { id: 'NEEDS_ATTENTION', label: 'Needs Attention' }
          ].map(f => (
            <button
              key={f.id}
              className={`btn btn-sm ${filterStatus === f.id ? 'btn-secondary' : 'btn-ghost'}`}
              style={{ fontWeight: filterStatus === f.id ? 600 : 400 }}
              onClick={() => setFilterStatus(f.id)}
            >
              {f.label}
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
          <div className="empty-state-title">No missions matching filter</div>
          <div className="empty-state-desc">
            {searchTerm 
              ? `No missions found matching "${searchTerm}".` 
              : filterStatus === 'NEEDS_ATTENTION'
                ? "You're clear. No missions currently require intervention or attention."
                : "No missions yet. Tell Supervisor what you want accomplished and your first mission will appear here."}
          </div>
          <button className="btn btn-primary btn-sm" onClick={onOpenCreateMission} style={{ marginTop: '8px' }}>
            <Plus size={13} />
            <span>Start a Mission</span>
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {filteredMissions.map(m => {
            const assigned = m.assigned_agents || m.assigned_agent_ids || [];
            const primaryAgent = assigned[0] || 'Claude Code';
            const isAttention = ['RECOVERING', 'INVESTIGATING', 'WAITING_APPROVAL', 'PAUSED'].includes(m.status);

            return (
              <div
                key={m.id}
                className="surface-card surface-card-interactive"
                style={{
                  padding: '16px 20px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '16px',
                  borderColor: isAttention ? 'var(--warning-border)' : 'var(--border)'
                }}
                onClick={() => onSelectMission(m.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flex: 1, minWidth: 0 }}>
                  <span className={`status-dot ${m.status === 'RUNNING' ? 'running' : m.status === 'COMPLETED' ? 'active' : isAttention ? 'watching' : 'idle'}`} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>
                        {m.title}
                      </span>
                      {isAttention && (
                        <span className="badge badge-amber" style={{ fontSize: '10px' }}>
                          <AlertTriangle size={10} /> Needs Attention
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: '2px' }}>
                      {m.goal}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexShrink: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                    <ProviderLogo providerId={primaryAgent} size={15} />
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                      {assigned.length > 0 ? assigned.join(' → ') : 'Claude Code'}
                    </span>
                  </div>

                  <span className={`badge ${m.status === 'COMPLETED' ? 'badge-green' : m.status === 'FAILED' ? 'badge-red' : m.status === 'RUNNING' ? 'badge-blue' : 'badge-amber'}`}>
                    {m.status.toLowerCase()}
                  </span>

                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
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
