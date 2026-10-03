import React, { useState } from 'react';
import { 
  ShieldAlert, 
  CheckCircle2, 
  XCircle, 
  AlertTriangle, 
  Clock 
} from 'lucide-react';
import type { ApprovalRequest } from '../types';
import { resolveApproval } from '../api';

interface ApprovalQueueProps {
  approvals: ApprovalRequest[];
  onRefresh: () => void;
}

export const ApprovalQueue: React.FC<ApprovalQueueProps> = ({
  approvals,
  onRefresh
}) => {
  const [operatorNotes, setOperatorNotes] = useState<Record<string, string>>({});
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const pendingApprovals = approvals.filter(a => a.status === 'PENDING');
  const historicalApprovals = approvals.filter(a => a.status !== 'PENDING');

  const handleResolve = async (requestId: string, status: 'APPROVE_ONCE' | 'DENY') => {
    setSubmittingId(requestId);
    setErrorMsg(null);
    try {
      const feedback = operatorNotes[requestId] || (status === 'APPROVE_ONCE' ? 'Approved once by operator' : 'Denied by operator');
      await resolveApproval(requestId, status, 'control_room_operator', feedback);
      onRefresh();
    } catch (e: any) {
      setErrorMsg(e.message || 'Failed to resolve approval request');
    } finally {
      setSubmittingId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Policy Warning Banner */}
      <div style={{
        backgroundColor: 'var(--status-crimson-bg)',
        border: '1px solid var(--status-crimson-border)',
        borderRadius: '4px',
        padding: '12px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontFamily: 'var(--font-mono)',
        fontSize: '11px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--status-crimson)' }}>
          <ShieldAlert size={16} />
          <strong>HUMAN SUPERVISOR GATE: STRICT ZERO IMPLICIT APPROVAL</strong>
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Absence of operator response is strictly DENIED upon timeout. One-time approval only.
        </div>
      </div>

      {errorMsg && (
        <div style={{
          backgroundColor: 'var(--status-crimson-bg)',
          border: '1px solid var(--status-crimson-border)',
          borderRadius: '4px',
          padding: '10px',
          color: 'var(--status-crimson)',
          fontFamily: 'var(--font-mono)',
          fontSize: '11px'
        }}>
          Error: {errorMsg}
        </div>
      )}

      {/* Pending Approval Requests Section */}
      <div className="cr-panel">
        <div className="cr-panel-header">
          <div className="cr-panel-title">
            <AlertTriangle size={15} color="var(--status-crimson)" />
            <span>Pending High-Risk Action Approvals</span>
          </div>
          <span className="badge badge-crimson">
            {pendingApprovals.length} ACTION REQUIRED
          </span>
        </div>

        {pendingApprovals.length === 0 ? (
          <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            NO PENDING HIGH-RISK APPROVAL REQUESTS. ALL AGENTS WITHIN NOMINAL SAFE ENVELOPE.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {pendingApprovals.map((req) => (
              <div 
                key={req.id}
                style={{
                  backgroundColor: 'var(--bg-core)',
                  border: '1px solid var(--status-crimson-border)',
                  borderLeft: '4px solid var(--status-crimson)',
                  borderRadius: '4px',
                  padding: '16px'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span className="badge badge-crimson">HIGH RISK ACTION</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600 }}>
                      AGENT: {req.agent_id}
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                      MISSION: {req.mission_id}
                    </span>
                  </div>

                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                    REQUEST ID: {req.id} &bull; {new Date(req.created_at).toLocaleTimeString()}
                  </div>
                </div>

                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: '4px' }}>
                    AGENT WANTS TO EXECUTE:
                  </div>
                  <pre style={{
                    backgroundColor: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-default)',
                    padding: '10px',
                    borderRadius: '3px',
                    fontSize: '12px',
                    color: 'var(--status-crimson)',
                    fontFamily: 'var(--font-mono)',
                    whiteSpace: 'pre-wrap'
                  }}>
                    {req.action || req.action_type}
                  </pre>
                </div>

                {req.target && (
                  <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', marginBottom: '10px' }}>
                    <strong style={{ color: 'var(--text-muted)' }}>TARGET RESOURCE: </strong>
                    <span style={{ color: 'var(--text-primary)' }}>{req.target}</span>
                  </div>
                )}

                {/* Operator Note Input */}
                <div style={{ marginBottom: '12px' }}>
                  <input 
                    type="text" 
                    placeholder="Operator rationale or feedback notes (optional)..."
                    value={operatorNotes[req.id] || ''}
                    onChange={(e) => setOperatorNotes({ ...operatorNotes, [req.id]: e.target.value })}
                    style={{ fontSize: '11px' }}
                  />
                </div>

                {/* Action Buttons: Explicit DENY vs APPROVE ONCE */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                  <button 
                    className="btn btn-danger"
                    onClick={() => handleResolve(req.id, 'DENY')}
                    disabled={submittingId === req.id}
                    style={{ padding: '8px 18px' }}
                  >
                    <XCircle size={14} />
                    <span>[DENY]</span>
                  </button>

                  <button 
                    className="btn btn-success"
                    onClick={() => handleResolve(req.id, 'APPROVE_ONCE')}
                    disabled={submittingId === req.id}
                    style={{ padding: '8px 18px' }}
                  >
                    <CheckCircle2 size={14} />
                    <span>[APPROVE ONCE]</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Historical Approvals Table */}
      <div className="cr-panel">
        <div className="cr-panel-header">
          <div className="cr-panel-title">
            <Clock size={15} color="var(--text-muted)" />
            <span>Approval Audit Log</span>
          </div>
          <span className="badge badge-neutral">
            {historicalApprovals.length} HISTORICAL
          </span>
        </div>

        {historicalApprovals.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
            NO AUDIT ENTRIES YET
          </div>
        ) : (
          <table className="cr-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Request ID</th>
                <th>Agent</th>
                <th>Action Requested</th>
                <th>Decision</th>
                <th>Operator Feedback</th>
              </tr>
            </thead>
            <tbody>
              {historicalApprovals.map((req) => (
                <tr key={req.id}>
                  <td className="font-mono">{new Date(req.created_at).toLocaleTimeString()}</td>
                  <td className="font-mono">{req.id}</td>
                  <td className="font-mono">{req.agent_id}</td>
                  <td className="font-mono" style={{ color: 'var(--status-amber)' }}>{req.action || req.action_type}</td>
                  <td>
                    {req.status === 'APPROVED' ? (
                      <span className="badge badge-emerald">APPROVED ONCE</span>
                    ) : (
                      <span className="badge badge-crimson">DENIED</span>
                    )}
                  </td>
                  <td className="font-mono" style={{ color: 'var(--text-secondary)' }}>
                    {req.feedback || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
