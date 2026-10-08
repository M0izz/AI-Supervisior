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
  Database,
  Layers,
  ShieldCheck
} from 'lucide-react';

interface LandingPageProps {
  onStartSupervising: () => void;
  onRunDemo: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onStartSupervising,
  onRunDemo
}) => {
  const coreLoop = [
    { step: '01', title: 'Give Supervisor a Goal', desc: 'Describe the outcome in plain human language. No task IDs or worktree flags required.', icon: Target },
    { step: '02', title: 'Supervisor Builds the Plan', desc: 'Decomposes intent into a directed acyclic graph (DAG) of isolated tasks.', icon: Layers },
    { step: '03', title: 'Agents Execute', desc: 'Dispatches tasks to the best suited worker: Claude Code, Codex, or local models.', icon: Bot },
    { step: '04', title: 'Supervisor Watches', desc: 'Real-time watchdogs observe all tool invocations, AST diffs, and stack traces.', icon: Terminal },
    { step: '05', title: 'Intervenes When Necessary', desc: 'Detects failure loops & runaway spend immediately. Freezes diff and pauses worker.', icon: ShieldAlert },
    { step: '06', title: 'Another Agent Takes Over', desc: 'Specialist agent takes over with preserved context without repeating mistakes.', icon: RotateCcw },
    { step: '07', title: 'Independent Verification', desc: 'Independent test runner validates code in an isolated sandbox. Never trust agent claims.', icon: ShieldCheck },
    { step: '08', title: 'You Receive the Result', desc: 'Human-readable summary delivered with full git traceability and zero unverified commits.', icon: CheckCircle2 }
  ];

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '44px', paddingBottom: '48px' }}>
      {/* Hero Section */}
      <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', paddingTop: '20px' }}>
        <div className="status-pill" style={{ color: 'var(--primary)', borderColor: 'var(--primary-border)', backgroundColor: 'var(--primary-subtle)' }}>
          <span className="status-dot watching" />
          <span>The Supervisory Layer for Autonomous AI Coding</span>
        </div>

        <h1 style={{ fontSize: '36px', fontWeight: 700, letterSpacing: '-0.025em', maxWidth: '680px', lineHeight: 1.2 }}>
          The agents are replaceable.<br />
          The Supervisor is the product.
        </h1>

        <p style={{ fontSize: '15px', color: 'var(--text-secondary)', maxWidth: '580px', lineHeight: 1.6 }}>
          AI Supervisor coordinates multi-agent fleets, detects failure loops in real time, executes safe handoffs, maintains shared project memory, and independently verifies every line of code.
        </p>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '6px' }}>
          <button className="btn btn-primary" style={{ padding: '8px 20px', fontSize: '13px' }} onClick={onStartSupervising}>
            <span>Start Supervising</span>
            <ArrowRight size={14} />
          </button>

          <button className="btn btn-secondary" style={{ padding: '8px 18px', fontSize: '13px' }} onClick={onRunDemo}>
            <FlaskConical size={14} />
            <span>Run Interactive Demo Mission</span>
          </button>
        </div>
      </div>

      {/* The 8-Step Core Loop */}
      <div className="surface-card" style={{ padding: '28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
              The 8-Step Supervisory Core Loop
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
              Human language in &rarr; Structured, verified execution out.
            </div>
          </div>
          <span className="badge badge-blue">Authoritative Control Plane</span>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: '12px'
        }}>
          {coreLoop.map(item => {
            const Icon = item.icon;
            return (
              <div
                key={item.step}
                style={{
                  backgroundColor: 'var(--surface-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  padding: '14px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', backgroundColor: 'var(--bg)', padding: '2px 6px', borderRadius: '4px' }}>
                    {item.step}
                  </span>
                  <Icon size={15} color="var(--primary)" />
                </div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>{item.title}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{item.desc}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3 Pillars of AI Supervisor */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
        <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: 'var(--warning-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <ShieldAlert size={15} color="var(--warning)" />
            </div>
            <h3 style={{ fontSize: '14px' }}>Watchdog Loop Interventions</h3>
          </div>
          <p style={{ fontSize: '12px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            Passive logging is insufficient. AI Supervisor actively intercepts repeated error signatures and out-of-scope modifications before runaway spend or corruption occurs.
          </p>
        </div>

        <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: 'var(--success-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CheckCircle2 size={15} color="var(--success)" />
            </div>
            <h3 style={{ fontSize: '14px' }}>Independent Verification</h3>
          </div>
          <p style={{ fontSize: '12px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            Never rely on an agent to grade its own homework. An independent verifier runs isolated test suites, AST diff checks, and deterministic validation rules before accepting results.
          </p>
        </div>

        <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: 'rgba(168, 85, 247, 0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Database size={15} color="var(--purple)" />
            </div>
            <h3 style={{ fontSize: '14px' }}>Cross-Agent Shared Memory</h3>
          </div>
          <p style={{ fontSize: '12px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            When one agent discovers a crucial repository constraint or disproves an approach, it is saved to SQLite project memory so subsequent agents never repeat the same mistakes.
          </p>
        </div>
      </div>
    </div>
  );
};
