import React, { useState } from 'react';
import { 
  RotateCcw, 
  ShieldAlert, 
  CheckCircle2, 
  ArrowRight, 
  ChevronDown, 
  ChevronUp,
  Cpu,
  ShieldCheck,
  Terminal
} from 'lucide-react';
import { ProviderLogo } from './ProviderLogo';

interface HandoffSequenceProps {
  sourceAgent?: string;
  targetAgent?: string;
  reason?: string;
  status?: 'active' | 'completed';
  isCompleted?: boolean;
}

export const HandoffSequence: React.FC<HandoffSequenceProps> = ({
  sourceAgent = 'claude-code',
  targetAgent = 'codex',
  reason = 'Watchdog detected repeated test failure loop (3 identical stack traces). Supervisor paused worker, preserved AST diff, and routed handoff.',
  status = 'completed',
  isCompleted = false
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isDone = isCompleted || status === 'completed';

  const stages = [
    {
      num: 1,
      title: 'Claude Code',
      subtitle: 'Working on implementation',
      status: 'Initial Worker',
      state: 'done',
      icon: Terminal,
      provider: sourceAgent,
      detail: 'Executed initial edits on authentication token expiry logic.'
    },
    {
      num: 2,
      title: 'Supervisor Intervened',
      subtitle: 'Loop watchdog intercepted failure',
      status: 'Supervisory Pause',
      state: 'done',
      icon: ShieldAlert,
      isSupervisor: true,
      detail: 'Repeated regex failure detected on test_csv_parser.py. Agent paused to prevent token waste.'
    },
    {
      num: 3,
      title: 'Codex Taking Over',
      subtitle: 'Context & diff package transferred',
      status: 'Handoff Protocol',
      state: 'done',
      icon: RotateCcw,
      provider: targetAgent,
      detail: 'Clean worktree diff frozen; failure diagnosis attached to prompt memory.'
    },
    {
      num: 4,
      title: 'Codex',
      subtitle: 'Resolving root-cause error',
      status: 'Specialist Worker',
      state: isDone ? 'done' : 'active',
      icon: Cpu,
      provider: targetAgent,
      detail: 'Refactored unescaped delimiter handling and patched unit test suite.'
    },
    {
      num: 5,
      title: 'Independent Verification',
      subtitle: 'Out-of-band test runner executing',
      status: 'Supervisor Sandbox',
      state: isDone ? 'done' : 'active',
      icon: ShieldCheck,
      isSupervisor: true,
      detail: 'Full test suite executed in isolated sandbox with zero unverified agent claims.'
    },
    {
      num: 6,
      title: 'Verified Result',
      subtitle: 'Certified and ready to merge',
      status: 'Certified Complete',
      state: isDone ? 'done' : 'pending',
      icon: CheckCircle2,
      isSuccess: true,
      detail: 'All 6 independent verification criteria passed without regressions.'
    }
  ];

  return (
    <div style={{
      borderRadius: '8px',
      backgroundColor: 'var(--surface-elevated)',
      border: '1px solid var(--border)',
      overflow: 'hidden',
      transition: 'border-color 0.2s ease'
    }}>
      {/* Header Banner */}
      <div style={{
        padding: '16px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            backgroundColor: 'var(--warning-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <RotateCcw size={15} color="var(--warning)" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                Autonomous Agent Handoff Sequence
              </span>
              <span className="badge badge-amber" style={{ fontSize: '10px' }}>
                SUPERVISOR INTERVENTION
              </span>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
              {reason}
            </div>
          </div>
        </div>

        <button
          type="button"
          className="btn btn-ghost btn-sm"
          style={{ fontSize: '11px', color: 'var(--text-muted)' }}
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <span>{isExpanded ? 'Collapse sequence' : 'Inspect 6-stage lifecycle'}</span>
          {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>

      {/* Compact Visual Sequence Chain */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 18px',
        backgroundColor: 'var(--bg)',
        borderTop: '1px solid var(--border-subtle)',
        gap: '10px',
        overflowX: 'auto'
      }}>
        {/* Source Agent */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '150px' }}>
          <ProviderLogo providerId={sourceAgent} size={22} />
          <div>
            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {sourceAgent}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
              Initial Worker (Paused)
            </div>
          </div>
        </div>

        {/* Transition: Supervisor Intervention */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
          <ArrowRight size={12} color="var(--text-muted)" />
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '3px 8px',
            borderRadius: '4px',
            backgroundColor: 'var(--warning-subtle)',
            border: '1px solid var(--warning-border)',
            fontSize: '11px',
            fontWeight: 500,
            color: 'var(--warning)'
          }}>
            <span className="status-dot watching" />
            <span>Supervisor Intervened</span>
          </div>
          <ArrowRight size={12} color="var(--text-muted)" />
        </div>

        {/* Target Agent */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '150px' }}>
          <ProviderLogo providerId={targetAgent} size={22} />
          <div>
            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {targetAgent}
            </div>
            <div style={{ fontSize: '10px', color: isDone ? 'var(--text-secondary)' : 'var(--warning)' }}>
              Specialist Worker
            </div>
          </div>
        </div>

        {/* Transition: Independent Verification */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
          <ArrowRight size={12} color="var(--text-muted)" />
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '3px 8px',
            borderRadius: '4px',
            backgroundColor: isDone ? 'var(--success-subtle)' : 'var(--primary-subtle)',
            border: `1px solid ${isDone ? 'var(--success-border)' : 'var(--primary-border)'}`,
            fontSize: '11px',
            fontWeight: 500,
            color: isDone ? 'var(--success)' : 'var(--primary)'
          }}>
            <ShieldCheck size={12} />
            <span>{isDone ? 'Verified Pass' : 'Verifying...'}</span>
          </div>
        </div>
      </div>

      {/* Expanded 6-Stage Timeline */}
      {isExpanded && (
        <div style={{
          padding: '16px 20px',
          borderTop: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--surface)',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '12px'
        }}>
          {stages.map(st => {
            const Icon = st.icon;
            const isStageDone = st.state === 'done';
            return (
              <div
                key={st.num}
                style={{
                  padding: '12px',
                  borderRadius: '6px',
                  backgroundColor: 'var(--surface-elevated)',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{
                      fontSize: '10px',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-muted)',
                      backgroundColor: 'var(--bg)',
                      padding: '1px 5px',
                      borderRadius: '3px'
                    }}>
                      0{st.num}
                    </span>
                    <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {st.title}
                    </span>
                  </div>

                  {st.provider ? (
                    <ProviderLogo providerId={st.provider} size={14} />
                  ) : (
                    <Icon size={13} color={isStageDone ? 'var(--success)' : 'var(--primary)'} />
                  )}
                </div>

                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                  {st.subtitle}
                </div>

                <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '4px', lineHeight: 1.4 }}>
                  {st.detail}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
