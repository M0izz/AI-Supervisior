import React from 'react';
import { AlertTriangle, ShieldCheck, ArrowRight, X, Activity } from 'lucide-react';
import type { InterventionDetail } from '../types';

interface InterventionPanelProps {
  intervention: InterventionDetail | null;
  onDismiss?: () => void;
  isOpen?: boolean;
}

export const InterventionPanel: React.FC<InterventionPanelProps> = ({
  intervention,
  onDismiss,
  isOpen = true
}) => {
  if (!intervention || !isOpen) return null;

  return (
    <div style={{
      backgroundColor: 'var(--bg-surface-elevated)',
      border: '1px solid var(--status-amber-border)',
      borderLeft: '4px solid var(--status-amber)',
      borderRadius: '4px',
      padding: '16px',
      marginBottom: '16px',
      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.4)',
      position: 'relative'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertTriangle size={18} color="var(--status-amber)" />
          <h3 style={{
            fontSize: '13px',
            fontFamily: 'var(--font-mono)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--status-amber)',
            fontWeight: 700
          }}>
            SUPERVISOR INTERVENTION TRIGGERED
          </h3>
          <span className="badge badge-amber" style={{ fontSize: '10px' }}>
            CONFIDENCE {Math.round(intervention.confidence * 100)}%
          </span>
        </div>

        {onDismiss && (
          <button 
            onClick={onDismiss}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center'
            }}
            title="Acknowledge alert"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Grid of Anomaly vs Decision */}
      <div className="grid-2" style={{ gap: '16px' }}>
        {/* Left Column: Anomaly & Evidence */}
        <div style={{
          backgroundColor: 'var(--bg-core)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '3px',
          padding: '12px'
        }}>
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
            marginBottom: '4px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}>
            <Activity size={12} color="var(--status-crimson)" />
            DETECTED ANOMALY
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '14px',
            fontWeight: 700,
            color: 'var(--status-crimson)',
            marginBottom: '6px'
          }}>
            {intervention.anomaly.toUpperCase()}
          </div>
          <div style={{
            fontSize: '12px',
            color: 'var(--text-secondary)',
            lineHeight: 1.4,
            backgroundColor: 'var(--bg-surface)',
            padding: '8px',
            borderRadius: '2px',
            border: '1px solid var(--border-subtle)',
            fontFamily: 'var(--font-mono)'
          }}>
            <strong style={{ color: 'var(--text-primary)' }}>Evidence: </strong>
            {typeof intervention.evidence === 'string' ? intervention.evidence : JSON.stringify(intervention.evidence)}
          </div>
        </div>

        {/* Right Column: Decision & Action */}
        <div style={{
          backgroundColor: 'var(--bg-core)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '3px',
          padding: '12px'
        }}>
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
            marginBottom: '4px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}>
            <ShieldCheck size={12} color="var(--status-emerald)" />
            SUPERVISOR DECISION & ACTION
          </div>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontFamily: 'var(--font-mono)',
            fontSize: '14px',
            fontWeight: 700,
            color: 'var(--status-emerald)',
            marginBottom: '6px'
          }}>
            <span>{intervention.action.toUpperCase()}</span>
            <ArrowRight size={14} />
            <span style={{ color: 'var(--status-cyan)' }}>{intervention.target}</span>
          </div>
          <div style={{
            fontSize: '12px',
            color: 'var(--text-secondary)',
            lineHeight: 1.4,
            backgroundColor: 'var(--bg-surface)',
            padding: '8px',
            borderRadius: '2px',
            border: '1px solid var(--border-subtle)',
            fontFamily: 'var(--font-mono)'
          }}>
            <strong style={{ color: 'var(--text-primary)' }}>Reason: </strong>
            {intervention.reason}
          </div>
        </div>
      </div>
      
      {/* Notice: No Chain-of-thought */}
      <div style={{
        marginTop: '10px',
        fontSize: '10px',
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <span>INTERVENTION TIMELOG: {new Date(intervention.timestamp).toLocaleTimeString()}</span>
        <span>SUPERVISOR AUTONOMOUS ENFORCEMENT &bull; COGNITIVE DEDUCTION VERIFIED</span>
      </div>
    </div>
  );
};
