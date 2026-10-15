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
  Check,
  Terminal,
  Cpu
} from 'lucide-react';
import type { PlanVersion, PlanTaskItem } from '../types';
import {
  getMissionPlan,
  approveMissionPlan,
  rejectMissionPlan,
  clarifyMissionPlan,
  editMissionPlan,
  regenerateMissionPlan,
  executeMission
} from '../api';

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
      <div className="flex flex-col items-center justify-center p-12 bg-slate-900/40 border border-slate-800 rounded-2xl">
        <RotateCw className="w-8 h-8 text-indigo-400 animate-spin mb-3" />
        <p className="text-sm text-slate-400 font-medium">Synthesizing execution plan and extracting intent...</p>
      </div>
    );
  }

  if (error || !plan) {
    return (
      <div className="p-8 bg-rose-950/20 border border-rose-800/40 rounded-2xl text-center">
        <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto mb-3" />
        <h3 className="text-lg font-semibold text-rose-200 mb-1">Plan Unavailable</h3>
        <p className="text-sm text-rose-400/80 mb-4">{error || 'No active plan found for this mission'}</p>
        <button
          onClick={loadPlan}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition"
        >
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
    <div className="space-y-6">
      {/* Plan Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 bg-gradient-to-r from-slate-900/90 via-slate-900/70 to-slate-800/80 border border-slate-700/60 rounded-2xl backdrop-blur-xl shadow-xl">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-indigo-500/10 border border-indigo-500/20 rounded-xl">
            <ShieldCheck className="w-6 h-6 text-indigo-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-tight">Supervisory Plan Review</h2>
              <span className="px-2 py-0.5 text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 rounded-md">
                v{version}
              </span>
              <span
                className={`px-2 py-0.5 text-xs font-semibold rounded-md border ${
                  isApproved
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                    : isRejected
                    ? 'bg-rose-500/20 text-rose-300 border-rose-500/30'
                    : hasBlockingQuestions
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                    : 'bg-blue-500/20 text-blue-300 border-blue-500/30'
                }`}
              >
                {approval_status}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Mandatory approval gate: agents cannot dispatch tasks until explicit operator sign-off.
            </p>
          </div>
        </div>

        {/* Global Plan Actions */}
        <div className="flex items-center gap-2">
          {!isApproved && !isRejected && (
            <>
              <button
                onClick={() => setIsEditing(!isEditing)}
                disabled={isSubmitting}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-200 rounded-lg flex items-center gap-1.5 transition"
              >
                <Edit3 className="w-3.5 h-3.5 text-slate-400" />
                {isEditing ? 'Cancel Edit' : 'Edit Plan'}
              </button>
              <button
                onClick={() => setShowRegenModal(true)}
                disabled={isSubmitting}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-200 rounded-lg flex items-center gap-1.5 transition"
              >
                <RotateCw className="w-3.5 h-3.5 text-indigo-400" />
                Regenerate
              </button>
              <button
                onClick={() => setShowRejectModal(true)}
                disabled={isSubmitting}
                className="px-3 py-1.5 bg-rose-950/40 hover:bg-rose-900/60 border border-rose-800/50 text-xs font-medium text-rose-300 rounded-lg flex items-center gap-1.5 transition"
              >
                <XCircle className="w-3.5 h-3.5 text-rose-400" />
                Reject
              </button>
              <button
                onClick={handleApproveAndStart}
                disabled={isSubmitting || hasBlockingQuestions}
                title={hasBlockingQuestions ? 'Resolve blocking clarification questions before approval' : 'Approve plan and dispatch execution'}
                className={`px-4 py-1.5 rounded-lg text-xs font-bold flex items-center gap-2 shadow-lg transition ${
                  hasBlockingQuestions
                    ? 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                    : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/30 cursor-pointer'
                }`}
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                Approve & Start Execution
              </button>
            </>
          )}

          {isApproved && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-xs font-semibold text-emerald-400">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              Approved by {plan.approved_by || 'operator'} (v{version})
            </div>
          )}
        </div>
      </div>

      {/* SECTION E: BLOCKING QUESTIONS ALERT BANNER */}
      {hasBlockingQuestions && (
        <div className="p-5 bg-amber-950/30 border border-amber-600/40 rounded-2xl shadow-lg">
          <div className="flex items-start gap-3">
            <div className="p-2 bg-amber-500/20 border border-amber-500/30 rounded-xl text-amber-400 mt-0.5">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-bold text-amber-200 tracking-tight">
                Blocking Clarification Required ({blockingQuestions.length})
              </h3>
              <p className="text-xs text-amber-300/80 mt-1 mb-3">
                Execution cannot safely proceed. Ambiguity in requirements was flagged by the Supervisor. Clarify below to unblock plan approval.
              </p>

              <div className="space-y-3">
                {blockingQuestions.map((q, idx) => (
                  <div key={idx} className="p-3.5 bg-slate-900/80 border border-amber-500/20 rounded-xl">
                    <p className="text-xs font-medium text-slate-200 mb-2 flex items-center gap-1.5">
                      <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                      {q}
                    </p>
                    <input
                      type="text"
                      placeholder="Type clarification or operator constraint..."
                      value={clarifyAnswers[q] || ''}
                      onChange={e => setClarifyAnswers({ ...clarifyAnswers, [q]: e.target.value })}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
                    />
                  </div>
                ))}
              </div>

              <div className="mt-3 flex justify-end">
                <button
                  onClick={handleClarifySubmit}
                  disabled={isSubmitting || Object.keys(clarifyAnswers).length === 0}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold rounded-lg shadow-md transition disabled:opacity-50"
                >
                  Submit Clarifications & Advance Plan
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION A: ORIGINAL REQUEST (VERBATIM) */}
      <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-2xl shadow-md">
        <div className="flex items-center gap-2 mb-2">
          <Terminal className="w-4 h-4 text-indigo-400" />
          <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">A. Original Request</h3>
          <span className="text-[10px] text-slate-500 font-mono">Immutable audit record</span>
        </div>
        <div className="p-4 bg-slate-950/80 border border-slate-800/80 rounded-xl font-mono text-xs text-slate-200 leading-relaxed whitespace-pre-wrap">
          {interpretation.original_request}
        </div>
      </div>

      {/* SECTION B: WHAT I UNDERSTOOD (INTERPRETATION) */}
      <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-2xl shadow-md space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">B. Intent Extraction & Boundaries</h3>
          </div>
          {isEditing && (
            <button
              onClick={handleSaveEdit}
              disabled={isSubmitting}
              className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-md transition"
            >
              Save Changes
            </button>
          )}
        </div>

        {/* Interpreted Goal */}
        <div>
          <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
            Interpreted Goal
          </label>
          {isEditing ? (
            <textarea
              value={editedGoal}
              onChange={e => setEditedGoal(e.target.value)}
              className="w-full p-2.5 bg-slate-950 border border-indigo-500/50 rounded-lg text-xs text-slate-200 focus:outline-none"
              rows={2}
            />
          ) : (
            <p className="text-xs font-semibold text-indigo-200 bg-indigo-950/20 border border-indigo-500/20 p-3 rounded-lg">
              {interpretation.interpreted_goal}
            </p>
          )}
        </div>

        {/* Deliverables, In-Scope & Exclusions Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Deliverables */}
          <div className="p-3.5 bg-slate-950/60 border border-slate-800 rounded-xl">
            <h4 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Expected Deliverables
            </h4>
            <ul className="space-y-1.5">
              {interpretation.expected_deliverables?.map((d, i) => (
                <li key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                  <span className="text-emerald-400 font-bold">•</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* In-Scope */}
          <div className="p-3.5 bg-slate-950/60 border border-slate-800 rounded-xl">
            <h4 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-blue-400" /> In-Scope Work
            </h4>
            <ul className="space-y-1.5">
              {interpretation.in_scope?.map((s, i) => (
                <li key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                  <span className="text-blue-400 font-bold">•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Explicit Exclusions */}
          <div className="p-3.5 bg-slate-950/60 border border-slate-800 rounded-xl">
            <h4 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <XCircle className="w-3.5 h-3.5 text-rose-400" /> Explicit Exclusions
            </h4>
            <ul className="space-y-1.5">
              {interpretation.explicit_exclusions?.map((x, i) => (
                <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                  <span className="text-rose-400 font-bold">•</span>
                  <span>{x}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* SECTION C & D: PROPOSED EXECUTION PLAN & AGENT ASSIGNMENTS */}
      <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-2xl shadow-md space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileCode className="w-4 h-4 text-indigo-400" />
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
              C & D. Proposed Tasks & Genuine Agent Runtime Assignments
            </h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">{tasks.length} ordered tasks</span>
        </div>

        <div className="space-y-3">
          {tasks.map((task: PlanTaskItem, idx: number) => (
            <div
              key={task.task_id || idx}
              className="p-4 bg-slate-950/70 border border-slate-800 hover:border-slate-700/80 rounded-xl transition space-y-2.5"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <span className="px-2 py-0.5 bg-slate-800 border border-slate-700 text-slate-300 font-mono text-[11px] font-bold rounded">
                    {task.task_id}
                  </span>
                  <h4 className="text-xs font-bold text-white">{task.title}</h4>
                </div>

                <div className="flex items-center gap-2">
                  {/* Agent assignment chip */}
                  <span className="px-2.5 py-0.5 bg-indigo-950/50 border border-indigo-700/50 text-indigo-300 text-[11px] font-medium rounded-full flex items-center gap-1.5">
                    <Cpu className="w-3 h-3 text-indigo-400" />
                    {task.proposed_agent} (Worker Runtime)
                  </span>

                  {/* Verification strategy badge */}
                  <span className="px-2 py-0.5 bg-emerald-950/40 border border-emerald-700/40 text-emerald-300 text-[10px] font-semibold rounded">
                    {task.verification_strategy}
                  </span>

                  {/* Risk chip */}
                  <span
                    className={`px-2 py-0.5 text-[10px] font-semibold rounded ${
                      task.risk_classification === 'HIGH'
                        ? 'bg-rose-950/40 text-rose-300 border border-rose-800/40'
                        : task.risk_classification === 'MEDIUM'
                        ? 'bg-amber-950/40 text-amber-300 border border-amber-800/40'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    Risk: {task.risk_classification}
                  </span>
                </div>
              </div>

              {task.description && (
                <p className="text-xs text-slate-400">{task.description}</p>
              )}

              {/* Dependencies & Acceptance Criteria */}
              <div className="pt-2 border-t border-slate-900 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                    Acceptance Criteria:
                  </span>
                  <ul className="space-y-1">
                    {task.acceptance_criteria?.map((ac, aci) => (
                      <li key={aci} className="text-slate-300 text-[11px] flex items-center gap-1.5">
                        <Check className="w-3 h-3 text-emerald-400 flex-shrink-0" />
                        <span>{ac}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div>
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                    Dependencies & Scope:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {task.dependencies?.length > 0 ? (
                      task.dependencies.map((dep, di) => (
                        <span key={di} className="px-1.5 py-0.5 bg-slate-900 text-slate-400 text-[10px] font-mono rounded">
                          dep: {dep}
                        </span>
                      ))
                    ) : (
                      <span className="text-slate-500 text-[10px]">None (Entry task)</span>
                    )}
                    {task.expected_files?.map((ef, efi) => (
                      <span key={efi} className="px-1.5 py-0.5 bg-indigo-950/40 text-indigo-300 text-[10px] font-mono rounded">
                        file: {ef}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* SECTION E & F: RISKS, ASSUMPTIONS & INDEPENDENT VERIFICATION */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Risks & Assumptions */}
        <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-2xl shadow-md space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">E. Risks & Disclosed Assumptions</h3>
          </div>

          <div className="space-y-2">
            <div>
              <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                Non-Blocking Assumptions:
              </span>
              <ul className="space-y-1">
                {interpretation.non_blocking_assumptions?.map((a, i) => (
                  <li key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                    <span className="text-indigo-400 font-bold">•</span>
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="pt-2 border-t border-slate-800">
              <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                Material Risks & Destructive Guardrails:
              </span>
              <ul className="space-y-1">
                {interpretation.risks?.map((r, i) => (
                  <li key={i} className="text-xs text-amber-300/90 flex items-start gap-1.5">
                    <span className="text-amber-400 font-bold">!</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {/* Definition of Success & Independent Verification */}
        <div className="p-5 bg-slate-900/60 border border-slate-800 rounded-2xl shadow-md space-y-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">F. Success Definition & Verification</h3>
          </div>

          <div>
            <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
              Definition of Success:
            </span>
            <p className="text-xs text-slate-200 bg-slate-950 p-2.5 rounded-lg border border-slate-800 font-medium">
              {interpretation.definition_of_success || 'All acceptance criteria certified by independent test execution.'}
            </p>
          </div>

          <div className="pt-2 border-t border-slate-800">
            <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
              Proposed Verification Methods:
            </span>
            <div className="flex flex-wrap gap-1.5">
              {interpretation.proposed_verification_methods?.map((vm, i) => (
                <span key={i} className="px-2.5 py-1 bg-emerald-950/30 border border-emerald-500/30 text-emerald-300 text-xs font-semibold rounded-lg flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  {vm}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Regeneration Modal */}
      {showRegenModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <RotateCw className="w-4 h-4 text-indigo-400" />
              Regenerate Execution Plan (v{version + 1})
            </h3>
            <p className="text-xs text-slate-400">
              Provide feedback or adjustments for the Supervisor to incorporate into the updated plan.
            </p>
            <textarea
              placeholder="e.g. Focus on JWT cookie renewal rather than custom sessions, add pytest fixture..."
              value={regenFeedback}
              onChange={e => setRegenFeedback(e.target.value)}
              className="w-full p-3 bg-slate-950 border border-slate-700 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
              rows={4}
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowRegenModal(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition"
              >
                Cancel
              </button>
              <button
                onClick={handleRegenerateSubmit}
                disabled={isSubmitting}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-lg transition shadow"
              >
                Regenerate Plan
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rejection Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-rose-300 flex items-center gap-2">
              <XCircle className="w-4 h-4 text-rose-400" />
              Reject Proposed Plan
            </h3>
            <p className="text-xs text-slate-400">
              State the reason for rejection. The mission will transition to REJECTED and no tasks will execute.
            </p>
            <input
              type="text"
              placeholder="e.g. Plan violates sprint timeline or architectural boundary..."
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-rose-500"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowRejectModal(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition"
              >
                Cancel
              </button>
              <button
                onClick={handleRejectSubmit}
                disabled={isSubmitting || !rejectReason.trim()}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-lg transition shadow disabled:opacity-50"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
