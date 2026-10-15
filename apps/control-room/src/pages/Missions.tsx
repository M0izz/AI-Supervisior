import React, { useState, useEffect } from 'react';
import { 
  Play, 
  Pause, 
  Plus, 
  ArrowLeft, 
  Layers, 
  Compass, 
  ShieldCheck, 
  Lock, 
  Target, 
  Search,
  AlertTriangle,
  Sparkles,
  CheckCircle2,
  Terminal,
  ChevronRight,
  Activity,
  X
} from 'lucide-react';
import type { Mission, Task, Event, SupervisorDecision } from '../types';
import { 
  pauseMission, 
  resumeMission, 
  getMissionTasks, 
  getMissionEvents, 
  getSupervisorDecisions,
  explainDecision,
  getSyncStatus
} from '../api';
import { HandoffSequence } from '../components/HandoffSequence';
import { SupervisorDecisionCard } from '../components/SupervisorDecisionCard';
import { PlanReview } from '../components/PlanReview';
import { ProviderLogo } from '../components/ProviderLogo';

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
  const [activeTab, setActiveTab] = useState<'plan' | 'story' | 'tasks' | 'verification' | 'policy'>('plan');
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  
  // Mission Detail State
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [missionDecisions, setMissionDecisions] = useState<SupervisorDecision[]>([]);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
  const [isActing, setIsActing] = useState(false);
  const [isSyncingWorktree, setIsSyncingWorktree] = useState(false);

  // Decision explanation modal
  const [explainingDecision, setExplainingDecision] = useState<SupervisorDecision | null>(null);
  const [decisionExplanation, setDecisionExplanation] = useState<any>(null);
  const [isExplaining, setIsExplaining] = useState(false);

  const safeMissions = Array.isArray(missions) ? missions : [];
  const selectedMission = safeMissions.find(m => m.id === selectedMissionId) || null;

  // Auto-switch to 'plan' tab when an unapproved mission is loaded
  useEffect(() => {
    if (selectedMission) {
      if (selectedMission.status === 'WAITING_APPROVAL' || !selectedMission.approved_plan_version) {
        setActiveTab('plan');
      }
    }
  }, [selectedMission?.id, selectedMission?.status]);

  // Load detailed mission telemetry
  useEffect(() => {
    if (!selectedMission) return;

    let isMounted = true;
    const loadDetailData = async () => {
      try {
        const [taskData, e, d] = await Promise.all([
          getMissionTasks(selectedMission.id).catch(() => ({ tasks: [] })),
          getMissionEvents(selectedMission.id, 50).catch(() => []),
          getSupervisorDecisions(selectedMission.id).catch(() => ({ decisions: [] }))
        ]);
        if (isMounted) {
          setTasks(Array.isArray(taskData?.tasks) ? taskData.tasks : []);
          setEvents(Array.isArray(e) ? e : []);
          setMissionDecisions(Array.isArray(d?.decisions) ? d.decisions : []);
        }
      } catch (err) {
        console.error('Failed to load mission telemetry', err);
      }
    };

    loadDetailData();
    const interval = setInterval(loadDetailData, 4000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [selectedMission?.id]);

  const handleTogglePause = async () => {
    if (!selectedMission) return;
    setIsActing(true);
    try {
      if (selectedMission.status === 'PAUSED') {
        await resumeMission(selectedMission.id);
      } else {
        await pauseMission(selectedMission.id, 'Operator requested pause via Missions panel');
      }
      onRefresh();
    } finally {
      setIsActing(false);
    }
  };

  const handleSyncWorktree = async () => {
    if (!selectedMission) return;
    setIsSyncingWorktree(true);
    try {
      await getSyncStatus();
      onRefresh();
    } finally {
      setIsSyncingWorktree(false);
    }
  };

  const handleExplainDecision = async (decision: SupervisorDecision) => {
    setExplainingDecision(decision);
    setIsExplaining(true);
    setDecisionExplanation(null);
    try {
      const res = await explainDecision(decision.decision_type || 'SUPERVISORY_DECISION', {
        id: decision.id,
        title: decision.title,
        why: decision.why,
        action: decision.action
      });
      setDecisionExplanation(res);
    } catch {
      setDecisionExplanation({
        rationale: decision.why || 'Structured supervisory decision executed to preserve mission invariants.',
        policy_reference: decision.action || 'Autonomous Supervision Policy',
        counterfactual: 'Without supervisory intervention, the worker agent would have remained in an infinite failure loop.'
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

  // KPI Metrics for list view
  const activeCount = safeMissions.filter(m => ['RUNNING', 'INVESTIGATING', 'RECOVERING', 'VERIFYING', 'WAITING_APPROVAL'].includes(m.status)).length;
  const attentionCount = safeMissions.filter(m => ['RECOVERING', 'INVESTIGATING', 'WAITING_APPROVAL', 'PAUSED', 'FAILED'].includes(m.status)).length;
  const completedCount = safeMissions.filter(m => m.status === 'COMPLETED').length;

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

    // Determine current stepper stage index (0: Understand, 1: Plan, 2: Execute, 3: Verify, 4: Complete)
    let currentStageIndex = 1; // Default: Plan Review
    if (selectedMission.status === 'COMPLETED') currentStageIndex = 4;
    else if (selectedMission.status === 'VERIFYING') currentStageIndex = 3;
    else if (selectedMission.status === 'RUNNING') currentStageIndex = 2;
    else if (selectedMission.approved_plan_version) currentStageIndex = 2;

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1100px', width: '100%' }}>
        {/* Top Back Nav & Quick Actions */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
          <button 
            className="btn btn-secondary btn-sm"
            onClick={() => onSelectMission(null)}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
          >
            <ArrowLeft size={14} />
            <span>Back to All Missions</span>
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={handleSyncWorktree}
              disabled={isSyncingWorktree}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Activity size={13} />
              <span>{isSyncingWorktree ? 'Syncing...' : 'Sync Worktree'}</span>
            </button>

            <button
              className="btn btn-secondary btn-sm"
              onClick={handleTogglePause}
              disabled={isActing}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              {selectedMission.status === 'PAUSED' ? <Play size={13} fill="currentColor" /> : <Pause size={13} />}
              <span>{selectedMission.status === 'PAUSED' ? 'Resume Mission' : 'Pause'}</span>
            </button>
          </div>
        </div>

        {/* Mission Title Card */}
        <div className="surface-card" style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1, minWidth: '280px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
                  {selectedMission.title}
                </h1>
                <span className="status-pill">
                  <span className={`status-dot ${selectedMission.status === 'RUNNING' ? 'running' : selectedMission.status === 'COMPLETED' ? 'active' : 'idle'}`} />
                  <span style={{ fontSize: '11px', fontWeight: 600 }}>{selectedMission.status.toLowerCase()}</span>
                </span>
                {(selectedMission.id.includes('demo') || selectedMission.title.includes('Scenario')) && (
                  <span className="badge badge-amber" style={{ fontSize: '10.5px' }} title="Deterministic demonstration scenario for evaluation">
                    DEMO SCENARIO
                  </span>
                )}
              </div>
              <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)', lineHeight: 1.5, maxWidth: '820px' }}>
                {selectedMission.goal}
              </p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-end', flexShrink: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                <span className={`status-dot ${supervisorDotClass}`} />
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{supervisorStateLabel}</span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Assigned:</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-primary)' }}>
                  <ProviderLogo providerId={assigned[0] || 'claude-code'} size={16} />
                  <span>{assigned.length > 0 ? assigned.join(' → ') : 'Claude Code'}</span>
                </span>
              </div>
            </div>
          </div>

          {/* 5-Stage Supervisory Pipeline Stepper */}
          <div className="mission-pipeline-stepper">
            {/* Step 1: Understand */}
            <div className={`stepper-stage ${currentStageIndex >= 0 ? 'completed' : ''}`}>
              <CheckCircle2 size={15} color="var(--success)" />
              <span>1. Understand</span>
            </div>

            <div className={`stepper-divider ${currentStageIndex >= 1 ? 'completed' : ''}`} />

            {/* Step 2: Plan Review */}
            <div className={`stepper-stage ${currentStageIndex >= 2 ? 'completed' : currentStageIndex === 1 ? 'active' : ''}`}>
              <ShieldCheck size={15} color={currentStageIndex >= 2 ? 'var(--success)' : currentStageIndex === 1 ? 'var(--primary-ice)' : 'var(--text-muted)'} />
              <span>2. Plan Review</span>
            </div>

            <div className={`stepper-divider ${currentStageIndex >= 2 ? 'completed' : ''}`} />

            {/* Step 3: Execute */}
            <div className={`stepper-stage ${currentStageIndex >= 3 ? 'completed' : currentStageIndex === 2 ? 'active' : ''}`}>
              <Terminal size={15} color={currentStageIndex >= 3 ? 'var(--success)' : currentStageIndex === 2 ? 'var(--primary-ice)' : 'var(--text-muted)'} />
              <span>3. Execute</span>
            </div>

            <div className={`stepper-divider ${currentStageIndex >= 3 ? 'completed' : ''}`} />

            {/* Step 4: Verify */}
            <div className={`stepper-stage ${currentStageIndex >= 4 ? 'completed' : currentStageIndex === 3 ? 'active' : ''}`}>
              <CheckCircle2 size={15} color={currentStageIndex >= 4 ? 'var(--success)' : currentStageIndex === 3 ? 'var(--primary-ice)' : 'var(--text-muted)'} />
              <span>4. Independent Verify</span>
            </div>

            <div className={`stepper-divider ${currentStageIndex >= 4 ? 'completed' : ''}`} />

            {/* Step 5: Complete */}
            <div className={`stepper-stage ${currentStageIndex === 4 ? 'completed' : ''}`}>
              <Sparkles size={15} color={currentStageIndex === 4 ? 'var(--success)' : 'var(--text-muted)'} />
              <span>5. Complete</span>
            </div>
          </div>

          {/* Progress Bar & Summary Stats */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-muted)' }}>
              <span>Supervised Execution Progress</span>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                {completedTasksCount} of {tasks.length} tasks completed ({progressPercent}%)
              </span>
            </div>
            <div style={{ height: '6px', backgroundColor: 'var(--surface-elevated)', borderRadius: '3px', overflow: 'hidden' }}>
              <div style={{ width: `${progressPercent}%`, height: '100%', backgroundColor: 'var(--primary)', transition: 'width 0.3s ease' }} />
            </div>
          </div>
        </div>

        {/* What Supervisor Understood Intelligence Card */}
        <div className="surface-card" style={{ padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: '12px', borderLeft: '3px solid var(--primary)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sparkles size={16} color="var(--primary)" />
              <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                What Supervisor Understood
              </span>
            </div>
            <span className="badge badge-neutral" style={{ fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span>Reasoning Model:</span>
              <strong style={{ color: 'var(--text-primary)' }}>Google Gemma 4 / OpenRouter</strong>
            </span>
          </div>

          <div style={{ fontSize: '13.5px', color: 'var(--text-primary)', lineHeight: 1.5, fontWeight: 500 }}>
            &ldquo;{selectedMission.goal}&rdquo;
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px', paddingTop: '10px', borderTop: '1px solid var(--border-subtle)', fontSize: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span style={{ color: 'var(--text-muted)', fontWeight: 700, fontSize: '11px', textTransform: 'uppercase' }}>
                Detected Constraints
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', color: 'var(--text-secondary)' }}>
                <span>• Scope restricted to repository worktree boundaries</span>
                <span>• Existing test suites and contract invariants must pass</span>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span style={{ color: 'var(--text-muted)', fontWeight: 700, fontSize: '11px', textTransform: 'uppercase' }}>
                Supervision Strategy
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', color: 'var(--text-secondary)' }}>
                <span>• Active loop watchdog (pause on 3 repetitive failure signatures)</span>
                <span>• Independent verification perimeter before completing</span>
              </div>
            </div>
          </div>
        </div>

        {/* Detail Tabs Bar */}
        <div style={{ display: 'flex', gap: '6px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '6px', flexWrap: 'wrap' }}>
          {[
            { id: 'plan', label: 'Mandatory Plan Review', icon: ShieldCheck, badge: selectedMission.approved_plan_version ? `v${selectedMission.approved_plan_version} APPROVED` : 'PLAN GATE' },
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
                className={`btn btn-sm ${isActive ? 'btn-primary' : 'btn-ghost'}`}
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                onClick={() => setActiveTab(tab.id as any)}
              >
                <Icon size={13} />
                <span>{tab.label}</span>
                {tab.badge && (
                  <span className={`badge ${isActive ? 'badge-neutral' : 'badge-blue'}`} style={{ fontSize: '9px', padding: '1px 5px', marginLeft: '2px' }}>
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Tab 0: Mandatory Plan Review & Approval Gate */}
        {activeTab === 'plan' && (
          <PlanReview
            missionId={selectedMission.id}
            onPlanApproved={() => {
              onRefresh();
              setActiveTab('story');
            }}
            onPlanRejected={() => {
              onRefresh();
            }}
            onRefresh={onRefresh}
          />
        )}

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
                            {isExpanded ? 'Hide Payload' : 'Show Payload'}
                          </button>

                          {isExpanded && (
                            <pre style={{
                              marginTop: '8px',
                              padding: '10px 12px',
                              borderRadius: 'var(--radius-sm)',
                              backgroundColor: 'var(--bg-deep)',
                              border: '1px solid var(--border-subtle)',
                              color: 'var(--text-secondary)',
                              fontFamily: 'var(--font-mono)',
                              fontSize: '11px',
                              overflowX: 'auto',
                              whiteSpace: 'pre-wrap',
                              maxHeight: '260px'
                            }}>
                              {JSON.stringify(ev.payload || {}, null, 2)}
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

        {/* Tab 2: Execution Tasks */}
        {activeTab === 'tasks' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {tasks.length === 0 ? (
              <div className="surface-card" style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                No active execution tasks yet. Once the plan is approved, tasks will be dispatched to assigned agents.
              </div>
            ) : (
              tasks.map(t => (
                <div key={t.id} className="surface-card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span className={`status-dot ${t.status === 'IN_PROGRESS' ? 'running' : t.status === 'COMPLETED' || t.status === 'VERIFIED' ? 'active' : 'idle'}`} />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '13.5px', color: 'var(--text-primary)' }}>
                        {t.title}
                      </div>
                      <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                        Agent: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{t.assigned_agent_id || 'unassigned'}</span>
                      </div>
                    </div>
                  </div>
                  <span className={`badge ${t.status === 'COMPLETED' || t.status === 'VERIFIED' ? 'badge-green' : t.status === 'IN_PROGRESS' ? 'badge-blue' : 'badge-neutral'}`}>
                    {t.status.toLowerCase()}
                  </span>
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab 3: Independent Verification */}
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
                    borderRadius: 'var(--radius-md)', 
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
              borderRadius: 'var(--radius-md)', 
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

        {/* Tab 4: Autonomy & Policies */}
        {activeTab === 'policy' && (
          <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <h2 style={{ fontSize: '16px', fontWeight: 600 }}>Supervisory Policy & Guardrail Configuration</h2>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Safety gates, maximum turn limits, and autonomous intervention rules for this mission.
                </p>
              </div>
              <span className="badge badge-green">
                <span>Active & Enforced</span>
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginTop: '4px' }}>
              <div style={{ padding: '14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Watchdog Policy</div>
                <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '2px', color: 'var(--text-primary)' }}>
                  Active Loop Interception
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Pauses worker after 3 identical failure signatures.
                </div>
              </div>

              <div style={{ padding: '14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Workspace Sandbox</div>
                <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '2px', color: 'var(--text-primary)' }}>
                  Isolated Worktree
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Main branch untouched until independent verification passes.
                </div>
              </div>

              <div style={{ padding: '14px', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
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

        {/* Modal: Decision Explanation */}
        {explainingDecision && (
          <div className="modal-overlay" onClick={() => setExplainingDecision(null)}>
            <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '520px' }}>
              <div className="modal-header">
                <h2 style={{ fontSize: '16px', fontWeight: 600 }}>Decision Explanation</h2>
                <button className="btn btn-ghost btn-sm" onClick={() => setExplainingDecision(null)}>
                  <X size={16} />
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                {isExplaining ? (
                  <div style={{ textAlign: 'center', padding: '20px' }}>Loading explanatory rationale...</div>
                ) : decisionExplanation ? (
                  <>
                    <div>
                      <strong style={{ color: 'var(--text-primary)', display: 'block', marginBottom: '4px' }}>Rationale:</strong>
                      <p>{decisionExplanation.rationale}</p>
                    </div>
                    <div>
                      <strong style={{ color: 'var(--text-primary)', display: 'block', marginBottom: '4px' }}>Policy Invariant:</strong>
                      <p style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>{decisionExplanation.policy_reference}</p>
                    </div>
                    <div>
                      <strong style={{ color: 'var(--text-primary)', display: 'block', marginBottom: '4px' }}>Counterfactual Analysis:</strong>
                      <p>{decisionExplanation.counterfactual}</p>
                    </div>
                  </>
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
  // MISSIONS LIST VIEW (REDESIGNED COMMAND DASHBOARD)
  // =========================================================================
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1100px', width: '100%' }}>
      {/* 1. Header & Primary Action */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '14px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            Mission Control Center
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Autonomous coding tasks under real-time supervision, plan approval gates, and independent verification
          </p>
        </div>

        <button 
          className="btn btn-primary" 
          onClick={onOpenCreateMission}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Plus size={15} />
          <span>Start New Mission</span>
        </button>
      </div>

      {/* 2. Executive KPI Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
        <div className="surface-card" style={{ padding: '16px 18px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            padding: '10px',
            borderRadius: '10px',
            backgroundColor: 'var(--primary-subtle)',
            border: '1px solid var(--primary-border)'
          }}>
            <Target size={20} color="var(--primary-ice)" />
          </div>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>{safeMissions.length}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Total Operations</div>
          </div>
        </div>

        <div className="surface-card" style={{ padding: '16px 18px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            padding: '10px',
            borderRadius: '10px',
            backgroundColor: 'rgba(52, 120, 246, 0.15)',
            border: '1px solid rgba(52, 120, 246, 0.3)'
          }}>
            <Terminal size={20} color="var(--primary)" />
          </div>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--primary-ice)' }}>{activeCount}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Active Execution</div>
          </div>
        </div>

        <div className="surface-card" style={{ padding: '16px 18px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            padding: '10px',
            borderRadius: '10px',
            backgroundColor: 'var(--warning-subtle)',
            border: '1px solid var(--warning-border)'
          }}>
            <ShieldCheck size={20} color="var(--warning)" />
          </div>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--warning)' }}>{attentionCount}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Needs Attention</div>
          </div>
        </div>

        <div className="surface-card" style={{ padding: '16px 18px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            padding: '10px',
            borderRadius: '10px',
            backgroundColor: 'var(--success-subtle)',
            border: '1px solid var(--success-border)'
          }}>
            <CheckCircle2 size={20} color="var(--success)" />
          </div>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--success)' }}>{completedCount}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Verified Complete</div>
          </div>
        </div>
      </div>

      {/* 3. Filter Pills and Search Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          {[
            { id: 'ALL', label: 'All Operations', count: safeMissions.length },
            { id: 'ACTIVE', label: 'Active', count: activeCount },
            { id: 'NEEDS_ATTENTION', label: 'Needs Attention', count: attentionCount },
            { id: 'COMPLETED', label: 'Completed', count: completedCount }
          ].map(f => (
            <button
              key={f.id}
              className={`btn btn-sm ${filterStatus === f.id ? 'btn-primary' : 'btn-ghost'}`}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              onClick={() => setFilterStatus(f.id)}
            >
              <span>{f.label}</span>
              <span className={`badge ${filterStatus === f.id ? 'badge-neutral' : 'badge-neutral'}`} style={{ fontSize: '10px', padding: '1px 5px' }}>
                {f.count}
              </span>
            </button>
          ))}
        </div>

        <div style={{ position: 'relative', width: '260px' }}>
          <Search size={14} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }} />
          <input
            type="text"
            className="input input-sm"
            placeholder="Search missions..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            style={{ width: '100%', paddingLeft: '30px' }}
          />
        </div>
      </div>

      {/* 4. Missions List */}
      {filteredMissions.length === 0 ? (
        <div className="surface-card" style={{ padding: '60px 20px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
          <div style={{
            padding: '14px',
            borderRadius: '50%',
            backgroundColor: 'var(--surface-elevated)',
            border: '1px solid var(--border)'
          }}>
            <Target size={26} color="var(--primary)" />
          </div>
          <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>No missions matching filter</div>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', maxWidth: '440px', lineHeight: 1.5 }}>
            {searchTerm 
              ? `No operations found matching "${searchTerm}".` 
              : filterStatus === 'NEEDS_ATTENTION'
                ? "You're clear. No missions currently require intervention or attention."
                : "No active missions. Start an autonomous mission to test supervised execution."}
          </p>
          <button className="btn btn-primary btn-sm" onClick={onOpenCreateMission} style={{ marginTop: '4px' }}>
            <Plus size={14} />
            <span>Start a Mission</span>
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {filteredMissions.map(m => {
            const assigned = m.assigned_agents || m.assigned_agent_ids || [];
            const primaryAgent = assigned[0] || 'Claude Code';
            const isAttention = ['RECOVERING', 'INVESTIGATING', 'WAITING_APPROVAL', 'PAUSED'].includes(m.status);

            return (
              <div
                key={m.id}
                className="surface-card surface-card-interactive"
                style={{
                  padding: '18px 22px',
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
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 600, fontSize: '14.5px', color: 'var(--text-primary)' }}>
                        {m.title}
                      </span>
                      {(m.id.includes('demo') || m.title.includes('Scenario')) && (
                        <span className="badge badge-neutral" style={{ fontSize: '9.5px', color: 'var(--text-muted)' }}>
                          DEMO
                        </span>
                      )}
                      {isAttention && (
                        <span className="badge badge-amber" style={{ fontSize: '10px' }}>
                          <AlertTriangle size={10} /> Needs Attention
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: '3px' }}>
                      {m.goal}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '18px', flexShrink: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                    <ProviderLogo providerId={primaryAgent} size={16} />
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

                  <ChevronRight size={16} color="var(--text-muted)" />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
