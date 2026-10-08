import React, { useState } from 'react';
import { 
  ShieldCheck, 
  ShieldAlert, 
  CheckCircle2, 
  XCircle, 
  Clock,
  AlertTriangle,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import type { ApprovalRequest } from '../types';
import { resolveApproval } from '../api';
import { ProviderLogo } from '../components/ProviderLogo';

interface ApprovalsProps {
  approvals: ApprovalRequest[];
  onRefresh: () => void;
}

export const Approvals: React.FC<ApprovalsProps> = ({
  approvals,
  onRefresh
}) => {
  const [actingId, setActingId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [expandedDetailsId, setExpandedDetailsId] = useState<string | null>(null);

  const safeApprovals = Array.isArray(approvals) ? approvals : [];
  const pending = safeApprovals.filter(a => a.status === 'PENDING');
  const resolved = safeApprovals.filter(a => a.status !== 'PENDING');

  const handleResolve = async (id: string, action: 'APPROVE_ONCE' | 'DENY') => {
    setActingId(id);
    setErrorMsg(null);
    try {
      const note = action === 'APPROVE_ONCE' ? 'Approved by supervisor' : 'Denied by supervisor';
      await resolveApproval(id, action, 'human_supervisor', note);
      onRefresh();
    } catch (e: any) {
      setErrorMsg(e.message || 'Failed to submit decision');
    } finally {
      setActingId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1080px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-title">
          <h1>Approvals</h1>
          <p>
            Safety control center. Review operations requested by autonomous agents before execution.
          </p>
        </div>
      </div>

      {errorMsg && (
        <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'var(--danger-subtle)', border: '1px solid var(--danger-border)', color: 'var(--danger)', fontSize: '13px' }}>
          {errorMsg}
        </div>
      )}

      {/* Pending Approvals */}
      <div className="section-group">
        <div className="section-title">
          <ShieldAlert size={14} color={pending.length > 0 ? 'var(--warning)' : 'var(--text-secondary)'} />
          <span>Pending Decisions ({pending.length})</span>
        </div>

        {pending.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <ShieldCheck size={20} color="var(--success)" />
            </div>
            <div className="empty-state-title" style={{ fontSize: '16px', fontWeight: 600 }}>You're clear.</div>
            <div className="empty-state-desc" style={{ maxWidth: '440px' }}>
              No agent is waiting for permission. All current agent tasks remain within policy boundaries and sandbox safety constraints.
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {pending.map(req => {
              const actionStr = req.action || '';
              const isHighRisk = actionStr.includes('rm') || actionStr.includes('delete') || actionStr.includes('drop') || actionStr.includes('reset') || actionStr.includes('force');
              const isExpanded = expandedDetailsId === req.id;

              return (
                <div 
                  key={req.id} 
                  className="surface-card"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '14px',
                    padding: '20px',
                    borderColor: isHighRisk ? 'var(--danger-border)' : 'var(--warning-border)',
                    backgroundColor: isHighRisk ? 'rgba(239, 68, 68, 0.03)' : 'var(--surface)'
                  }}
                >
                  {/* Top Bar: Action Requires Your Approval & Risk Tag */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <AlertTriangle size={16} color={isHighRisk ? 'var(--danger)' : 'var(--warning)'} />
                      <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        ACTION REQUIRES YOUR APPROVAL
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className={`badge ${isHighRisk ? 'badge-red' : 'badge-amber'}`} style={{ fontSize: '10px' }}>
                        Risk: {isHighRisk ? 'HIGH' : 'MEDIUM'}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        req-{req.id.slice(0, 8)}
                      </span>
                    </div>
                  </div>

                  {/* Structured Operational Assessment */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px', fontSize: '13px' }}>
                    <div style={{ padding: '10px 12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                      <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', display: 'block' }}>1. WHAT IS ABOUT TO HAPPEN?</span>
                      <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                        {req.agent_id || 'Agent'} is attempting to execute: <code style={{ color: 'var(--primary)' }}>{actionStr}</code>
                      </span>
                    </div>

                    <div style={{ padding: '10px 12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                      <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', display: 'block' }}>2. WHY?</span>
                      <span style={{ color: 'var(--text-primary)' }}>
                        {req.reason || 'Requested operation targets sensitive workspace perimeter or files outside active task scope.'}
                      </span>
                    </div>

                    <div style={{ padding: '10px 12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                      <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', display: 'block' }}>3. WHAT IS ALLOWED?</span>
                      <span style={{ color: 'var(--success)' }}>
                        Scoped modifications strictly within task git worktree and non-destructive shell commands.
                      </span>
                    </div>

                    <div style={{ padding: '10px 12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                      <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', display: 'block' }}>4. WHAT IS BLOCKED?</span>
                      <span style={{ color: 'var(--danger)' }}>
                        Direct modifications of protected paths (.env, git history) or force operations without explicit approval.
                      </span>
                    </div>
                  </div>

                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', padding: '8px 12px', backgroundColor: 'var(--bg)', borderRadius: '6px' }}>
                    <strong style={{ color: 'var(--text-primary)' }}>WHAT WILL HAPPEN IF APPROVED? </strong>
                    Supervisor will grant a one-time execution token for this exact command, log the audit event, and continue watchdog observation.
                  </div>

                  {/* Metadata Row */}
                  <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between', 
                    flexWrap: 'wrap',
                    gap: '12px',
                    paddingTop: '10px', 
                    borderTop: '1px solid var(--border-subtle)' 
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '12px', color: 'var(--text-muted)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <ProviderLogo providerId={req.agent_id} size={14} />
                        <span>Agent: <strong style={{ color: 'var(--text-primary)' }}>{req.agent_id || 'Worker'}</strong></span>
                      </div>
                      <div>
                        Mission: <strong style={{ color: 'var(--text-primary)' }}>{req.mission_id || 'General'}</strong>
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        style={{ fontSize: '11px', color: 'var(--text-muted)' }}
                        onClick={() => setExpandedDetailsId(isExpanded ? null : req.id)}
                      >
                        <span>{isExpanded ? 'Hide Details' : 'View Details'}</span>
                        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      </button>

                      <button
                        className="btn btn-danger btn-sm"
                        disabled={actingId === req.id}
                        onClick={() => handleResolve(req.id, 'DENY')}
                      >
                        <XCircle size={13} />
                        <span>Deny</span>
                      </button>

                      <button
                        className="btn btn-primary btn-sm"
                        disabled={actingId === req.id}
                        onClick={() => handleResolve(req.id, 'APPROVE_ONCE')}
                      >
                        <CheckCircle2 size={13} />
                        <span>Approve Once</span>
                      </button>
                    </div>
                  </div>

                  {/* Expandable Technical Details */}
                  {isExpanded && (
                    <div style={{
                      padding: '12px',
                      borderRadius: '6px',
                      backgroundColor: 'var(--surface-elevated)',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '11px',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-secondary)'
                    }}>
                      <pre>{JSON.stringify(req, null, 2)}</pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Decision History */}
      {resolved.length > 0 && (
        <div className="section-group">
          <div className="section-title">
            <Clock size={14} color="var(--text-muted)" />
            <span>Decision History</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {resolved.map(req => {
              const isApproved = req.status === 'APPROVED';
              return (
                <div key={req.id} className="surface-card" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {isApproved ? <CheckCircle2 size={15} color="var(--success)" /> : <XCircle size={15} color="var(--danger)" />}
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
                        {req.action || 'Protected action'}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        Resolved by: {req.resolved_by || 'human_supervisor'} &bull; {req.agent_id || 'agent'}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span className={`badge ${isApproved ? 'badge-green' : 'badge-red'}`}>
                      {req.status.toLowerCase()}
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {req.created_at ? new Date(req.created_at).toLocaleDateString() : 'Recent'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
