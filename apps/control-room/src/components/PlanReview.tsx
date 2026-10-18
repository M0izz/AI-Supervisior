import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  HelpCircle,
  CheckCircle2,
  XCircle,
  RotateCw,
  Edit3,
  Play,
  FileCode,
  Layers,
  Sparkles,
  Terminal,
  Lock,
  X
} from 'lucide-react';
import type { PlanVersion, AdapterInfo } from '../types';
import {
  getMissionPlan,
  approveMissionPlan,
  rejectMissionPlan,
  clarifyMissionPlan,
  editMissionPlan,
  regenerateMissionPlan,
  executeMission,
  getAdapters,
  assignTaskAgent
} from '../api';
import { ProviderLogo } from './ProviderLogo';

interface PlanReviewProps {
  missionId: string;
  onPlanApproved?: () => void;
  onPlanRejected?: () => void;
  onRefresh?: () => void;
}

export const PlanReview: React.FC<PlanReviewProps> = ({
  missionId,
  onPlanApproved,
  onPlanRejected,
  onRefresh
}) => {
  const [plan, setPlan] = useState<PlanVersion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Clarification answering state
  const [clarifyAnswers, setClarifyAnswers] = useState<Record<string, string>>({});
  
  // Feedback for regeneration
  const [regenFeedback, setRegenFeedback] = useState('');
  const [showRegenModal, setShowRegenModal] = useState(false);

  // Edit mode
  const [isEditing, setIsEditing] = useState(false);
  const [editedGoal, setEditedGoal] = useState('');
  const [editedDeliverables, setEditedDeliverables] = useState<string[]>([]);
  const [editedInScope, setEditedInScope] = useState<string[]>([]);
  const [editedExclusions, setEditedExclusions] = useState<string[]>([]);

  // Rejection modal
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  // Available adapters for assignment
  const [adapters, setAdapters] = useState<AdapterInfo[]>([]);

  useEffect(() => {
    getAdapters()
      .then(res => setAdapters(res.adapters || []))
      .catch(() => {});
  }, []);

  const handleAgentSelect = async (taskId: string, newAgentId: string) => {
    setIsSubmitting(true);
    try {
      await assignTaskAgent(missionId, taskId, newAgentId);
      await loadPlan();
      if (onRefresh) onRefresh();
    } catch (err: any) {
      alert(`Failed to assign agent: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const loadPlan = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMissionPlan(missionId);
      setPlan(data);
      if (data?.interpretation) {
        setEditedGoal(data.interpretation.interpreted_goal || '');
        setEditedDeliverables([...(data.interpretation.expected_deliverables || [])]);
        setEditedInScope([...(data.interpretation.in_scope || [])]);
        setEditedExclusions([...(data.interpretation.explicit_exclusions || [])]);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load plan');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (missionId) {
      loadPlan();
    }
  }, [missionId]);

  if (loading) {
    return (
      <div className="surface-card" style={{ padding: '40px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
        <RotateCw size={24} color="var(--primary)" style={{ animation: 'spin 1s linear infinite' }} />
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Synthesizing execution plan and extracting intent...</p>
      </div>
    );
  }

  if (error || !plan) {
    return (
      <div className="surface-card" style={{ padding: '30px', textAlign: 'center', borderColor: 'var(--danger-border)', backgroundColor: 'var(--danger-subtle)' }}>
        <AlertTriangle size={28} color="var(--danger)" style={{ margin: '0 auto 10px' }} />
        <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>Plan Unavailable</h3>
        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '14px' }}>{error || 'No active plan found for this mission'}</p>
        <button onClick={loadPlan} className="btn btn-secondary btn-sm">
          Retry
        </button>
      </div>
    );
  }

  const { interpretation, tasks, version, approval_status } = plan;
  const blockingQuestions = interpretation.blocking_questions || [];
  const hasBlockingQuestions = blockingQuestions.length > 0;
  const isApproved = approval_status === 'APPROVED';
  const isRejected = approval_status === 'REJECTED';

  // Handle Clarify Submission
  const handleClarifySubmit = async () => {
    setIsSubmitting(true);
    try {
      const updated = await clarifyMissionPlan(missionId, clarifyAnswers);
      setPlan(updated);
      setClarifyAnswers({});
      onRefresh?.();
    } catch (err: any) {
      setError(err?.message || 'Failed to submit clarifications');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Approve & Dispatch
  const handleApproveAndStart = async () => {
    if (hasBlockingQuestions) {
      alert('Cannot approve while blocking questions remain unresolved.');
      return;
    }
    setIsSubmitting(true);
    try {
      await approveMissionPlan(missionId, version, 'operator');
      await executeMission(missionId, { agent_id: 'worker_01', use_worktree: false });
      onPlanApproved?.();
      onRefresh?.();
      await loadPlan();
    } catch (err: any) {
      setError(err?.message || 'Approval / dispatch failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Rejection
  const handleRejectSubmit = async () => {
    if (!rejectReason.trim()) return;
    setIsSubmitting(true);
    try {
      await rejectMissionPlan(missionId, rejectReason);
      setShowRejectModal(false);
      onPlanRejected?.();
      onRefresh?.();
      await loadPlan();
    } catch (err: any) {
      setError(err?.message || 'Failed to reject plan');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Regeneration
  const handleRegenerateSubmit = async () => {
    setIsSubmitting(true);
    try {
      const updated = await regenerateMissionPlan(missionId, regenFeedback);
      setPlan(updated);
      setShowRegenModal(false);
      setRegenFeedback('');
      onRefresh?.();
    } catch (err: any) {
      setError(err?.message || 'Failed to regenerate plan');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Edit Save
  const handleSaveEdit = async () => {
    setIsSubmitting(true);
    try {
      const updated = await editMissionPlan(missionId, {
        interpretation: {
          interpreted_goal: editedGoal,
          expected_deliverables: editedDeliverables,
          in_scope: editedInScope,
          explicit_exclusions: editedExclusions
        }
      });
      setPlan(updated);
      setIsEditing(false);
      onRefresh?.();
    } catch (err: any) {
      setError(err?.message || 'Failed to save plan edits');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="plan-review-container">
      {/* 1. Plan Header Bar */}
      <div className="plan-header-card">
        <div className="plan-header-meta">
          <div style={{
            padding: '10px',
            borderRadius: '10px',
            backgroundColor: 'var(--primary-subtle)',
            border: '1px solid var(--primary-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <ShieldCheck size={24} color="var(--primary-ice)" />
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <h2 style={{ fontSize: '17px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
                Supervisory Plan Review
              </h2>
              <span className="badge badge-blue" style={{ fontSize: '11px', fontWeight: 700 }}>
                v{version}
              </span>
              <span className={`badge ${
                isApproved 
                  ? 'badge-green' 
                  : isRejected 
                    ? 'badge-red' 
                    : hasBlockingQuestions 
                      ? 'badge-amber' 
                      : 'badge-blue'
              }`} style={{ fontSize: '11px', fontWeight: 700 }}>
                {approval_status}
              </span>
            </div>

            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
              Mandatory approval gate: agents cannot dispatch tasks until explicit operator sign-off.
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {!isApproved && !isRejected && (
            <>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setIsEditing(!isEditing)}
                disabled={isSubmitting}
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Edit3 size={13} />
                <span>{isEditing ? 'Cancel Edit' : 'Edit Plan'}</span>
              </button>

              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setShowRegenModal(true)}
                disabled={isSubmitting}
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <RotateCw size={13} />
                <span>Regenerate</span>
              </button>

              <button
                className="btn btn-danger btn-sm"
                onClick={() => setShowRejectModal(true)}
                disabled={isSubmitting}
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <XCircle size={13} />
                <span>Reject</span>
              </button>

              <button
                className="btn btn-primary btn-sm"
                onClick={handleApproveAndStart}
                disabled={isSubmitting || hasBlockingQuestions}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: hasBlockingQuestions ? 'var(--surface-hover)' : 'var(--success)',
                  borderColor: hasBlockingQuestions ? 'var(--border)' : 'var(--success-border)',
                  color: hasBlockingQuestions ? 'var(--text-muted)' : '#FFFFFF',
                  fontWeight: 600,
                  boxShadow: hasBlockingQuestions ? 'none' : '0 0 16px rgba(16, 185, 129, 0.35)'
                }}
              >
                <Play size={13} fill="currentColor" />
                <span>Approve & Start Execution</span>
              </button>
            </>
          )}

          {isApproved && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--success-subtle)',
              border: '1px solid var(--success-border)',
              color: 'var(--success)',
              fontSize: '12px',
              fontWeight: 600
            }}>
              <CheckCircle2 size={15} />
              <span>Approved by {plan.approved_by || 'operator'} (v{version})</span>
            </div>
          )}
        </div>
      </div>

      {/* 2. SECTION E: BLOCKING CLARIFICATION QUESTIONS (IF ANY) */}
      {hasBlockingQuestions && (
        <div className="surface-card" style={{
          backgroundColor: 'var(--warning-subtle)',
          borderColor: 'var(--warning-border)',
          padding: '18px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={18} color="var(--warning)" />
            <h3 style={{ fontSize: '14px', fontWeight: 700, color: 'var(--warning)' }}>
              Blocking Clarification Required ({blockingQuestions.length})
            </h3>
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Execution cannot safely proceed. Ambiguity in requirements was flagged by the Supervisor. Clarify below to unblock plan approval.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {blockingQuestions.map((q, idx) => (
              <div key={idx} style={{
                backgroundColor: 'var(--surface-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '12px 14px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', color: 'var(--text-primary)', fontWeight: 600 }}>
                  <HelpCircle size={14} color="var(--warning)" />
                  <span>{q}</span>
                </div>
                <input
                  type="text"
                  className="input input-sm"
                  placeholder="Type clarification or operator constraint..."
                  value={clarifyAnswers[q] || ''}
                  onChange={e => setClarifyAnswers({ ...clarifyAnswers, [q]: e.target.value })}
                />
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px' }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleClarifySubmit}
              disabled={isSubmitting || Object.keys(clarifyAnswers).length === 0}
            >
              Submit Clarifications & Advance Plan
            </button>
          </div>
        </div>
      )}

      {/* 3. SECTION A: ORIGINAL REQUEST (VERBATIM AUDIT RECORD) */}
      <div className="plan-section-card">
        <div className="plan-section-header">
          <div className="plan-section-title">
            <Terminal size={15} color="var(--primary-ice)" />
            <span>A. Original Request</span>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            Immutable audit record
          </span>
        </div>

        <div className="plan-terminal-box">
          <span style={{ color: 'var(--primary)', userSelect: 'none', marginRight: '8px' }}>&gt;_</span>
          {interpretation.original_request}
        </div>
      </div>

      {/* 4. SECTION B: INTENT EXTRACTION & BOUNDARIES */}
      <div className="plan-section-card">
        <div className="plan-section-header">
          <div className="plan-section-title">
            <Sparkles size={15} color="var(--cyan)" />
            <span>B. Intent Extraction & Boundaries</span>
          </div>
          {isEditing && (
            <button
              className="btn btn-primary btn-sm"
              onClick={handleSaveEdit}
              disabled={isSubmitting}
            >
              Save Changes
            </button>
          )}
        </div>

        {/* Interpreted Goal */}
        <div>
          <label style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '6px' }}>
            Interpreted Goal
          </label>
          {isEditing ? (
            <textarea
              className="input"
              value={editedGoal}
              onChange={e => setEditedGoal(e.target.value)}
              rows={2}
              style={{ width: '100%', fontSize: '13px' }}
            />
          ) : (
            <div style={{
              padding: '12px 14px',
              backgroundColor: 'var(--primary-subtle)',
              border: '1px solid var(--primary-border)',
              borderRadius: 'var(--radius-md)',
              fontSize: '13px',
              fontWeight: 600,
              color: 'var(--primary-ice)',
              lineHeight: 1.5
            }}>
              "{interpretation.interpreted_goal}"
            </div>
          )}
        </div>

        {/* Deliverables, In-Scope, and Exclusions Grid */}
        <div className="plan-grid-3">
          {/* Deliverables Card */}
          <div className="plan-sub-card">
            <div className="plan-sub-card-title">
              <CheckCircle2 size={14} color="var(--success)" />
              <span>Expected Deliverables</span>
            </div>
            <ul className="plan-bullet-list">
              {interpretation.expected_deliverables?.map((d, i) => (
                <li key={i} className="plan-bullet-item">
                  <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* In-Scope Card */}
          <div className="plan-sub-card">
            <div className="plan-sub-card-title">
              <Layers size={14} color="var(--primary)" />
              <span>In-Scope Work</span>
            </div>
            <ul className="plan-bullet-list">
              {interpretation.in_scope?.map((s, i) => (
                <li key={i} className="plan-bullet-item">
                  <span style={{ color: 'var(--primary)', fontWeight: 700 }}>•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Explicit Exclusions Card */}
          <div className="plan-sub-card" style={{ borderColor: 'var(--danger-border)' }}>
            <div className="plan-sub-card-title">
              <XCircle size={14} color="var(--danger)" />
              <span style={{ color: 'var(--danger)' }}>Explicit Exclusions</span>
            </div>
            <ul className="plan-bullet-list">
              {interpretation.explicit_exclusions?.map((x, i) => (
                <li key={i} className="plan-bullet-item" style={{ color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--danger)', fontWeight: 700 }}>✕</span>
                  <span>{x}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* 5. SECTIONS C & D: PROPOSED TASKS & GENUINE AGENT RUNTIME ASSIGNMENTS */}
      <div className="plan-section-card">
        <div className="plan-section-header">
          <div className="plan-section-title">
            <FileCode size={15} color="var(--purple)" />
            <span>C & D. Proposed Tasks & Genuine Agent Runtime Assignments</span>
          </div>
          <span className="badge badge-neutral" style={{ fontSize: '11px' }}>
            {tasks.length} ordered tasks
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {tasks.map((task, idx) => (
            <div key={task.task_id} className="plan-task-item">
              <div className="plan-task-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className="plan-badge-step">STEP {idx + 1}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                    {task.task_id}
                  </span>
                  <h4 style={{ fontSize: '13.5px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {task.title}
                  </h4>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {/* Interactive Agent Runtime Selector */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <ProviderLogo providerId={task.proposed_agent || (task as any).assigned_agent_id || 'worker_01'} size={14} />
                    <select
                      className="select select-sm"
                      style={{
                        fontSize: '11px',
                        padding: '2px 8px',
                        fontFamily: 'var(--font-mono)',
                        backgroundColor: 'var(--surface)',
                        borderColor: isApproved ? 'var(--border-subtle)' : 'var(--primary)',
                        cursor: isApproved ? 'default' : 'pointer',
                        borderRadius: 'var(--radius-sm)'
                      }}
                      value={task.proposed_agent || (task as any).assigned_agent_id || 'worker_01'}
                      disabled={isApproved || isSubmitting}
                      onChange={e => handleAgentSelect(task.task_id, e.target.value)}
                      title={isApproved ? "Plan is approved. Click 'Edit Plan' or reject to reassign." : "Select execution agent runtime"}
                    >
                      <option value="worker_01">worker_01 (Local Sandbox) [AVAILABLE]</option>
                      <option value="auto">auto (Supervisor Optimal Route)</option>
                      {adapters.filter(a => a.availability?.available).map(a => (
                        <option key={a.adapter_id} value={a.adapter_id}>
                          {a.adapter_id} ({a.display_name}) [AVAILABLE]
                        </option>
                      ))}
                      {adapters.filter(a => !a.availability?.available).map(a => (
                        <option key={a.adapter_id} value={a.adapter_id} disabled>
                          {a.adapter_id} ({a.display_name}) [{a.availability?.status?.replace(/_/g, ' ') || 'UNAVAILABLE'}]
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Action Type */}
                  <span className="badge badge-neutral" style={{ fontSize: '10px' }}>
                    {(task as any).action_type || 'EXECUTE'}
                  </span>

                  {/* Risk Badge */}
                  <span className={`badge ${
                    (task.risk_classification || (task as any).risk_level) === 'HIGH' 
                      ? 'badge-red' 
                      : (task.risk_classification || (task as any).risk_level) === 'MEDIUM' 
                        ? 'badge-amber' 
                        : 'badge-green'
                  }`} style={{ fontSize: '10px' }}>
                    Risk: {task.risk_classification || (task as any).risk_level || 'LOW'}
                  </span>
                </div>
              </div>

              {/* Compatibility Rationale & Recommendation Explanation */}
              <div style={{
                marginTop: '6px',
                marginBottom: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '8px',
                fontSize: '11px',
                color: 'var(--text-muted)',
                backgroundColor: 'var(--surface)',
                padding: '5px 10px',
                borderRadius: '4px',
                border: '1px solid var(--border-subtle)'
              }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                  <CheckCircle2 size={12} color="var(--success)" />
                  <span>Compatible capabilities: <code>{(task.required_capabilities || ['code_execution', 'file_editing']).join(', ')}</code></span>
                </span>
                <span style={{ color: 'var(--text-secondary)' }}>
                  {task.proposed_agent === 'worker_01'
                    ? 'Recommended: Local Python tool sandbox with strict worktree isolation.'
                    : task.proposed_agent === 'auto'
                      ? 'Dynamic auto-routing: Supervisor will select verified runtime at dispatch.'
                      : `Assigned: ${task.proposed_agent} runtime adapter.`}
                </span>
              </div>

              {/* Description */}
              <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)', lineHeight: 1.5, margin: '2px 0' }}>
                {task.description}
              </p>

              {/* Acceptance Criteria */}
              {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
                <div style={{
                  padding: '10px 12px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: 'var(--surface)',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px'
                }}>
                  <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Acceptance Criteria:
                  </span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {task.acceptance_criteria.map((crit, cIdx) => (
                      <div key={cIdx} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                        <CheckCircle2 size={13} color="var(--success)" />
                        <span>{crit}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 6. SECTION F: SAFETY & VERIFICATION INVARIANTS */}
      <div className="plan-section-card">
        <div className="plan-section-header">
          <div className="plan-section-title">
            <Lock size={15} color="var(--primary)" />
            <span>F. Safety Perimeter & Independent Verification Gates</span>
          </div>
        </div>

        <div className="plan-grid-3">
          <div className="plan-sub-card">
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Execution Sandbox
            </span>
            <div style={{ fontSize: '12.5px', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
              <span>✓ Git Worktree Strict Isolation</span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Primary repository root protected from direct mutation.
            </div>
          </div>

          <div className="plan-sub-card">
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Watchdog Supervision
            </span>
            <div style={{ fontSize: '12.5px', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
              <span>✓ Loop & Anomaly Detection</span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Intervenes automatically on 3 repetitive failure signatures.
            </div>
          </div>

          <div className="plan-sub-card">
            <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Independent Verification
            </span>
            <div style={{ fontSize: '12.5px', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
              <span>✓ Objective Test Evaluation</span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Agent cannot self-certify completion. Verification perimeter runs clean test suite.
            </div>
          </div>
        </div>
      </div>

      {/* Modal: Regenerate Plan */}
      {showRegenModal && (
        <div className="modal-overlay" onClick={() => setShowRegenModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '480px' }}>
            <div className="modal-header">
              <h2 style={{ fontSize: '15px', fontWeight: 600 }}>Regenerate Execution Plan</h2>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowRegenModal(false)}>
                <X size={16} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                Provide feedback or additional constraints. The supervisor will synthesize an updated plan version (v{version + 1}).
              </p>
              <textarea
                className="input"
                placeholder="e.g. Focus only on unit tests; do not modify configuration files..."
                value={regenFeedback}
                onChange={e => setRegenFeedback(e.target.value)}
                rows={3}
                style={{ width: '100%', fontSize: '13px' }}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button className="btn btn-secondary" onClick={() => setShowRegenModal(false)}>
                  Cancel
                </button>
                <button className="btn btn-primary" onClick={handleRegenerateSubmit} disabled={isSubmitting}>
                  Regenerate Plan
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Reject Plan */}
      {showRejectModal && (
        <div className="modal-overlay" onClick={() => setShowRejectModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '480px' }}>
            <div className="modal-header">
              <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--danger)' }}>Reject Execution Plan</h2>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowRejectModal(false)}>
                <X size={16} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                Please specify why this plan is being rejected. The rejection reason is permanently stored in the SQLite audit ledger.
              </p>
              <textarea
                className="input"
                placeholder="e.g. Incorrect scope, missing acceptance criteria..."
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
                rows={3}
                style={{ width: '100%', fontSize: '13px' }}
                required
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button className="btn btn-secondary" onClick={() => setShowRejectModal(false)}>
                  Cancel
                </button>
                <button className="btn btn-danger" onClick={handleRejectSubmit} disabled={isSubmitting || !rejectReason.trim()}>
                  Confirm Rejection
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
