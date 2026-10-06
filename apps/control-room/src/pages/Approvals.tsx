import React, { useState } from 'react';
import { 
  ShieldCheck, 
  ShieldAlert, 
  CheckCircle2, 
  XCircle, 
  Clock 
} from 'lucide-react';
import type { ApprovalRequest } from '../types';
import { resolveApproval } from '../api';

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
            Human-in-the-loop safety gates. Review operations requested by autonomous agents before execution.
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
          <ShieldAlert size={14} color="var(--warning)" />
          <span>Pending Decisions ({pending.length})</span>
        </div>

        {pending.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <ShieldCheck size={18} color="var(--success)" />
            </div>
            <div className="empty-state-title">No pending approval requests</div>
            <div className="empty-state-desc">
              All agent operations are within normal policy boundaries. Protected file edits or destructive commands will appear here for one-time signoff.
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {pending.map(req => {
              const isDestructive = (req.action || '').includes('reset') || (req.action || '').includes('delete');
              return (
                <div 
                  key={req.id} 
                  className="surface-card"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '14px',
                    borderColor: isDestructive ? 'var(--danger-border)' : 'var(--warning-border)'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className={`badge ${isDestructive ? 'badge-red' : 'badge-amber'}`}>
                          {isDestructive ? 'High Risk Action' : 'Approval Required'}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          id: {req.id}
                        </span>
                      </div>

                      <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '4px' }}>
                        Agent wants to execute:
                      </div>

                      <div style={{ 
                        fontFamily: 'var(--font-mono)', 
                        fontSize: '12px', 
                        padding: '8px 12px', 
                        backgroundColor: 'var(--surface-elevated)', 
                        borderRadius: '6px', 
                        border: '1px solid var(--border)',
                        color: 'var(--text-primary)',
                        marginTop: '4px'
                      }}>
                        {req.action || 'Protected command invocation'}
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
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
                        <span>Allow Once</span>
                      </button>
                    </div>
                  </div>

                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    <strong>Reason:</strong> {req.reason || 'Operation touches safety perimeter or restricted repository resource'}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '11px', color: 'var(--text-muted)', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
                    <span>Agent: {req.agent_id || 'unknown'}</span>
                    <span>Mission: {req.mission_id || 'unassigned'}</span>
                    <span>Requested: {new Date(req.created_at || Date.now()).toLocaleTimeString()}</span>
                  </div>
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
                <div key={req.id} className="item-row" style={{ cursor: 'default' }}>
                  <div className="item-row-primary">
                    {isApproved ? <CheckCircle2 size={15} color="var(--success)" /> : <XCircle size={15} color="var(--danger)" />}
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 500 }}>{req.action || 'Protected action'}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        Resolved by: {req.resolved_by || 'human_supervisor'}
                      </div>
                    </div>
                  </div>

                  <div className="item-row-meta">
                    <span className={`badge ${isApproved ? 'badge-green' : 'badge-red'}`}>
                      {req.status.toLowerCase()}
                    </span>
                    <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                      {new Date(req.created_at || Date.now()).toLocaleDateString()}
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
