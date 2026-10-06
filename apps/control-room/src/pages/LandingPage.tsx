import React from 'react';
import { 
  ArrowRight, 
  CheckCircle2, 
  ShieldAlert, 
  RotateCcw, 
  Target, 
  Bot, 
  Terminal, 
  FlaskConical, 
  Database
} from 'lucide-react';

interface LandingPageProps {
  onStartSupervising: () => void;
  onRunDemo: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onStartSupervising,
  onRunDemo
}) => {
  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '48px', paddingBottom: '48px' }}>
      {/* Hero Section */}
      <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', paddingTop: '24px' }}>
        <div className="status-pill" style={{ color: 'var(--primary)', borderColor: 'var(--primary-border)', backgroundColor: 'var(--primary-subtle)' }}>
          <span className="status-dot watching" />
          <span>Operations Layer for Autonomous AI Coding</span>
        </div>

        <h1 style={{ fontSize: '36px', fontWeight: 700, letterSpacing: '-0.025em', maxWidth: '640px', lineHeight: 1.2 }}>
          Your AI agents work.<br />
          Your Supervisor manages them.
        </h1>

        <p style={{ fontSize: '16px', color: 'var(--text-secondary)', maxWidth: '580px', lineHeight: 1.6 }}>
          AI Supervisor coordinates multi-agent fleets, detects failure loops in real time, executes safe handoffs, maintains shared project memory, and independently verifies every line of code.
        </p>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '8px' }}>
          <button className="btn btn-primary" style={{ padding: '8px 18px', fontSize: '14px' }} onClick={onStartSupervising}>
            <span>Start Supervising</span>
            <ArrowRight size={15} />
          </button>

          <button className="btn btn-secondary" style={{ padding: '8px 18px', fontSize: '14px' }} onClick={onRunDemo}>
            <FlaskConical size={15} />
            <span>Load Demo Scenario</span>
          </button>
        </div>
      </div>

      {/* Visual Lifecycle Diagram */}
      <div className="surface-card" style={{ padding: '28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
          <div>
            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              The Supervisory Lifecycle
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Core principle: Agent completion ≠ verified completion
            </div>
          </div>
          <span className="badge badge-blue">Authoritative Control Plane</span>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
          gap: '12px',
          position: 'relative'
        }}>
          {[
            { step: '01', title: 'Goal & Plan', desc: 'DAG task creation with constraints', icon: Target },
            { step: '02', title: 'Agent Route', desc: 'Dispatch to Claude, Codex, or local LLM', icon: Bot },
            { step: '03', title: 'Watchdog', desc: 'Live loop & anomaly detection', icon: Terminal },
            { step: '04', title: 'Intervene', desc: 'Safe pause & context package freeze', icon: ShieldAlert },
            { step: '05', title: 'Handoff', desc: 'Transfer state to specialized agent', icon: RotateCcw },
            { step: '06', title: 'Independent Verify', desc: 'Out-of-band test & sandbox check', icon: CheckCircle2 }
          ].map(item => {
            const Icon = item.icon;
            return (
              <div
                key={item.step}
                style={{
                  backgroundColor: 'var(--surface-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  padding: '14px 12px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{item.step}</span>
                  <Icon size={14} color="var(--primary)" />
                </div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>{item.title}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>{item.desc}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3 Pillars of AI Supervisor */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
        <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: 'var(--primary-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Terminal size={15} color="var(--primary)" />
            </div>
            <h3 style={{ fontSize: '15px' }}>Live Watchdog Interventions</h3>
          </div>
          <p style={{ fontSize: '13px', lineHeight: 1.5 }}>
            Passive logging is insufficient for autonomous agents. AI Supervisor actively intercepts repeated error signatures, token thrashing, and out-of-scope file modifications before runaway spend or corruption occurs.
          </p>
        </div>

        <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: 'var(--success-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CheckCircle2 size={15} color="var(--success)" />
            </div>
            <h3 style={{ fontSize: '15px' }}>Independent Verification</h3>
          </div>
          <p style={{ fontSize: '13px', lineHeight: 1.5 }}>
            Never rely on an agent to grade its own homework. An independent verifier runs isolated test suites, diff checks, and deterministic validation rules before accepting any task as complete.
          </p>
        </div>

        <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: 'var(--purple-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Database size={15} color="var(--purple)" />
            </div>
            <h3 style={{ fontSize: '15px' }}>Cross-Agent Shared Memory</h3>
          </div>
          <p style={{ fontSize: '13px', lineHeight: 1.5 }}>
            When one agent discovers a crucial repository fact or disproves an approach, it is saved to SQLite project memory so subsequent agents don't repeat the exact same mistakes.
          </p>
        </div>
      </div>

      {/* Start Action */}
      <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
        <button className="btn btn-primary" style={{ padding: '8px 20px', fontSize: '14px' }} onClick={onStartSupervising}>
          <span>Open Control Room Workspace</span>
          <ArrowRight size={15} />
        </button>
      </div>
    </div>
  );
};
