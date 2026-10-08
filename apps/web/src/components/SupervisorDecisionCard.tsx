import React, { useState } from 'react';
import { 
  ShieldAlert, 
  CheckCircle2, 
  ArrowRightLeft, 
  PauseCircle, 
  Sliders, 
  ChevronDown, 
  ChevronUp, 
  Sparkles,
  Bot,
  Lock
} from 'lucide-react';
import type { SupervisorDecision } from '../types';

interface SupervisorDecisionCardProps {
  decision: SupervisorDecision;
  onExplain?: (decision: SupervisorDecision) => void;
}

export const SupervisorDecisionCard: React.FC<SupervisorDecisionCardProps> = ({ 
  decision,
  onExplain 
}) => {
  const [expanded, setExpanded] = useState(false);

  const getTypeBadge = (type: string) => {
    const t = type.toUpperCase();
    if (t === 'ROUTE') return { label: 'ROUTE', className: 'badge-blue', icon: Sliders };
    if (t === 'PAUSE' || t === 'INTERVENE') return { label: 'PAUSE', className: 'badge-amber', icon: PauseCircle };
    if (t === 'HANDOFF') return { label: 'HANDOFF', className: 'badge-purple', icon: ArrowRightLeft };
    if (t === 'VERIFY') return { label: 'VERIFIED', className: 'badge-green', icon: CheckCircle2 };
    if (t === 'WARN') return { label: 'WATCHDOG', className: 'badge-amber', icon: ShieldAlert };
    if (t === 'REQUIRE_APPROVAL') return { label: 'APPROVAL REQ', className: 'badge-red', icon: Lock };
    if (t === 'COMPLETE') return { label: 'COMPLETED', className: 'badge-green', icon: CheckCircle2 };
    return { label: t, className: 'badge-neutral', icon: Sparkles };
  };

  const badge = getTypeBadge(decision.decision_type);
  const Icon = badge.icon;

  return (
    <div 
      className="surface-card" 
      style={{ 
        padding: '16px', 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '12px',
        borderLeft: decision.decision_type.toUpperCase() === 'PAUSE' || decision.decision_type.toUpperCase() === 'REQUIRE_APPROVAL'
          ? '3px solid var(--amber)'
          : decision.decision_type.toUpperCase() === 'VERIFY'
          ? '3px solid var(--green)'
          : '3px solid var(--primary)',
        transition: 'all 150ms ease'
      }}
    >
      {/* Top Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className={`badge ${badge.className}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', fontWeight: 600 }}>
            <Icon size={12} />
            <span>{badge.label}</span>
          </span>
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {decision.title}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {decision.timestamp}
          </span>
          <button 
            className="btn btn-secondary" 
            style={{ padding: '2px 8px', fontSize: '11px', height: '24px' }}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            <span>{expanded ? 'Less' : 'Details'}</span>
          </button>
        </div>
      </div>

      {/* Why / Rationale */}
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
        <strong style={{ color: 'var(--text-primary)' }}>Why: </strong>
        {decision.why}
      </div>

      {/* Target & Action Strip */}
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '12px', fontSize: '11px', color: 'var(--text-muted)' }}>
        {decision.target_agent && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Bot size={12} color="var(--primary)" />
            <span>Target: <strong style={{ color: 'var(--text-primary)' }}>{decision.target_agent}</strong></span>
          </div>
        )}

        {decision.action && (
          <div>
            Action: <span className="kbd-shortcut" style={{ padding: '2px 6px', fontSize: '10px' }}>{decision.action}</span>
          </div>
        )}

        {decision.provenance_model && (
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--text-muted)' }}>
            <Sparkles size={11} color="var(--primary)" />
            <span>{decision.provenance_model}</span>
          </div>
        )}
      </div>

      {/* Expanded Details Drawer */}
      {expanded && (
        <div style={{ marginTop: '6px', paddingTop: '10px', borderTop: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {/* Evidence */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>
              Supervisory Evidence:
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {decision.evidence && decision.evidence.length > 0 ? (
                decision.evidence.map((ev, i) => (
                  <span key={i} className="badge badge-neutral" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                    • {ev}
                  </span>
                ))
              ) : (
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Policy engine evaluated thresholds.</span>
              )}
            </div>
          </div>

          {/* Result */}
          {decision.result && (
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              <strong>Result: </strong> {decision.result}
            </div>
          )}

          {onExplain && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
              <button 
                className="btn btn-secondary" 
                style={{ fontSize: '11px', padding: '4px 10px' }}
                onClick={() => onExplain(decision)}
              >
                <Sparkles size={12} color="var(--primary)" />
                <span>Explain Rationale via Gemma 4</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
