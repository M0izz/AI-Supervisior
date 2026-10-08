import React, { useState } from 'react';
import { 
  ShieldCheck, 
  Lock, 
  Keyboard, 
  Sparkles, 
  Sliders,
  CheckCircle2,
  FolderGit2,
  Bot,
  Server
} from 'lucide-react';
import { ProviderLogo } from '../components/ProviderLogo';

export const Settings: React.FC = () => {
  const [activeSection, setActiveSection] = useState<'workspace' | 'supervision' | 'safety' | 'autonomy' | 'interface' | 'providers' | 'integrations' | 'about'>('workspace');
  const [watchdogStrictness, setWatchdogStrictness] = useState('STANDARD');
  const [autoVerify, setAutoVerify] = useState(true);
  const [zeroImplicitApproval, setZeroImplicitApproval] = useState(true);
  const [maxTurnsBudget, setMaxTurnsBudget] = useState(10);
  const [saveToast, setSaveToast] = useState(false);

  const handleSave = () => {
    setSaveToast(true);
    setTimeout(() => setSaveToast(false), 2500);
  };

  const sections = [
    { id: 'workspace', label: 'Workspace', icon: FolderGit2, desc: 'Repository, control plane, environment' },
    { id: 'supervision', label: 'Supervision', icon: Sliders, desc: 'Watchdogs, budgets, interventions' },
    { id: 'safety', label: 'Safety', icon: ShieldCheck, desc: 'Permissions, dangerous actions, approvals' },
    { id: 'autonomy', label: 'Autonomy', icon: Lock, desc: 'Absence mode, retries, handoffs' },
    { id: 'providers', label: 'Agent Fleet', icon: Bot, desc: 'Agent adapters & CLI detection' },
    { id: 'integrations', label: 'Integrations', icon: Server, desc: 'Nebius, Gemini, Gemma & Cloud' },
    { id: 'interface', label: 'Interface', icon: Keyboard, desc: 'Shortcuts, appearance, notifications' },
    { id: 'about', label: 'About', icon: Sparkles, desc: 'Diagnostics, version & system status' }
  ] as const;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1080px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-title">
          <h1>Settings</h1>
          <p>Supervision policies, safety boundaries, agent runtimes, and keyboard shortcuts.</p>
        </div>

        <div className="page-header-actions">
          <button className="btn btn-primary" onClick={handleSave}>
            <span>Save Preferences</span>
          </button>
        </div>
      </div>

      {saveToast && (
        <div style={{ padding: '10px 14px', borderRadius: '6px', backgroundColor: 'var(--success-subtle)', border: '1px solid var(--success-border)', color: 'var(--success)', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CheckCircle2 size={15} />
          <span>Settings saved to local supervisor configuration.</span>
        </div>
      )}

      {/* Settings Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: '24px' }}>
        {/* Navigation Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {sections.map(sec => {
            const Icon = sec.icon;
            const isActive = activeSection === sec.id;
            return (
              <button
                key={sec.id}
                className={`nav-item ${isActive ? 'active' : ''}`}
                style={{ textAlign: 'left', display: 'flex', flexDirection: 'column', alignItems: 'flex-start', padding: '10px 12px', gap: '2px' }}
                onClick={() => setActiveSection(sec.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Icon size={15} color={isActive ? 'var(--primary)' : 'var(--text-muted)'} />
                  <span style={{ fontWeight: isActive ? 600 : 500, fontSize: '13px' }}>{sec.label}</span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', paddingLeft: '23px' }}>
                  {sec.desc}
                </div>
              </button>
            );
          })}
        </div>

        {/* Setting Section Details */}
        <div className="surface-card" style={{ padding: '24px' }}>
          {/* Workspace */}
          {activeSection === 'workspace' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Workspace & Environment</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>Authoritative local repository paths and local IPC control plane.</p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Active Workspace Repository
                </label>
                <input type="text" readOnly value="C:\Users\Moiz\Desktop\AI Supervisior" style={{ fontFamily: 'var(--font-mono)' }} />
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Missions spawn isolated worktrees inside this root repository.</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Control Plane Endpoint
                </label>
                <input type="text" readOnly value={import.meta.env.VITE_API_URL || "127.0.0.1:8000"} style={{ fontFamily: 'var(--font-mono)' }} />
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>FastAPI control plane daemon with WebSocket real-time event pipeline.</span>
              </div>
            </div>
          )}

          {/* Supervision */}
          {activeSection === 'supervision' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Supervision & Watchdogs</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>Configure failure loop thresholds, budgets, and independent verification rules.</p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Failure Loop Detection Threshold
                </label>
                <select value={watchdogStrictness} onChange={e => setWatchdogStrictness(e.target.value)}>
                  <option value="STRICT">Strict (2 repeated identical errors trigger pause & handoff)</option>
                  <option value="STANDARD">Standard (3 repeated identical errors trigger pause & handoff)</option>
                  <option value="LENIENT">Lenient (5 repeated identical errors trigger pause & handoff)</option>
                </select>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Watchdog tracks stack trace hashes and tool call sequences to stop spinning agents.</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Default Turn Budget Limit
                </label>
                <input 
                  type="number" 
                  min={1} 
                  max={50} 
                  value={maxTurnsBudget} 
                  onChange={e => setMaxTurnsBudget(parseInt(e.target.value, 10) || 10)} 
                />
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Maximum number of tool invocations an agent can execute before supervisor review.</span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', backgroundColor: 'var(--surface-elevated)', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>Enforce Independent Verification</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>Never allow an agent to certify its own completed tasks. All diffs must pass independent sandbox checks.</div>
                </div>
                <input type="checkbox" checked={autoVerify} onChange={e => setAutoVerify(e.target.checked)} />
              </div>
            </div>
          )}

          {/* Safety */}
          {activeSection === 'safety' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Safety & Approvals</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>Guardrails against destructive operations and unauthorized perimeter modifications.</p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', backgroundColor: 'var(--surface-elevated)', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>Strict Zero Implicit Approval</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>Silence or operator timeout is strictly treated as DENIED. Prevents destructive modifications when unattended.</div>
                </div>
                <input type="checkbox" checked={zeroImplicitApproval} onChange={e => setZeroImplicitApproval(e.target.checked)} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Hard Prohibited Shell Commands
                </label>
                <input type="text" readOnly value="rm -rf /, git push --force, dd, mkfs, format, shutdown" style={{ fontFamily: 'var(--font-mono)' }} />
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Watchdog intercepts and denies these commands before execution.</span>
              </div>
            </div>
          )}

          {/* Autonomy */}
          {activeSection === 'autonomy' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Autonomy & Absence Mode</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>Governs autonomous background task execution while away from the machine.</p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Max Tasks Per Session</label>
                  <input type="number" defaultValue={5} />
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Circuit breaker ceiling on queued tasks.</span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Max Handoffs Before Operator Pause</label>
                  <input type="number" defaultValue={2} />
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Prevents continuous agent ping-ponging.</span>
                </div>
              </div>
            </div>
          )}

          {/* Interface */}
          {activeSection === 'interface' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Interface & Shortcuts</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>Developer keyboard shortcuts and interaction settings.</p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {[
                  { key: '⌘K / Ctrl+K', desc: 'Open Command Palette & Mission Search' },
                  { key: 'ESC', desc: 'Close modals, drawers, and popovers' },
                  { key: 'Enter', desc: 'Interpret goal in Mission Composer' },
                  { key: 'Shift + Enter', desc: 'Insert newline in Mission Composer' }
                ].map(s => (
                  <div key={s.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', backgroundColor: 'var(--surface-elevated)', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                    <span style={{ fontSize: '13px' }}>{s.desc}</span>
                    <span className="kbd-shortcut">{s.key}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Providers */}
          {activeSection === 'providers' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Agent Adapters & Providers</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>Supervised agent runtime integration channels.</p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {[
                  { id: 'claude-code', name: 'Claude Code', type: 'Anthropic CLI', status: 'Installed & Ready' },
                  { id: 'codex', name: 'OpenAI Codex', type: 'Specialist Engine', status: 'Ready' },
                  { id: 'gemini', name: 'Google Gemini', type: 'CLI Adapter', status: 'Detected' },
                  { id: 'qwen', name: 'Qwen 2.5', type: 'Local Weights', status: 'Local Ready' }
                ].map(p => (
                  <div key={p.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', backgroundColor: 'var(--surface-elevated)', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <ProviderLogo providerId={p.id} size={20} />
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>{p.name}</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{p.type}</div>
                      </div>
                    </div>
                    <span className="badge badge-green" style={{ fontSize: '11px' }}>{p.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Integrations */}
          {activeSection === 'integrations' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Infrastructure & Model Providers</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Configure cloud substrates, remote microVM execution, and token factory inference.
                </p>
              </div>

              {/* Google Gemma 4 */}
              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <ProviderLogo providerId="gemini" size={24} />
                    <div>
                      <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>Google Gemma 4</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Supervisory Intelligence · Bounded Planning · Invariant Extraction · Explanations</div>
                    </div>
                  </div>
                  <span className="badge badge-success" style={{ fontSize: '11px' }}>Local & Cloud Active</span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Model Selection (GEMMA_MODEL)</label>
                    <input type="text" defaultValue="gemma-4-31B-it" style={{ fontSize: '12px' }} />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Endpoint (Local / Remote)</label>
                    <input type="text" defaultValue="local://gemma-engine" style={{ fontSize: '12px' }} />
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '11px', color: 'var(--text-muted)', paddingTop: '6px', borderTop: '1px solid var(--border-subtle)' }}>
                  <span>✓ Bounded goal decomposition</span>
                  <span>✓ Deterministic safety guard</span>
                  <span>✓ Provenance tracking</span>
                </div>
              </div>

              {/* Nebius */}
              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <ProviderLogo providerId="nebius" size={24} />
                    <div>
                      <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>Nebius Token Factory</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>High-throughput Open-Weights Inference · Nemotron · Qwen · DeepSeek</div>
                    </div>
                  </div>
                  <span className="badge badge-amber" style={{ fontSize: '11px' }}>Configuration Optional</span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>API Key (NEBIUS_API_KEY)</label>
                    <input type="password" placeholder="neb_••••••••••••" style={{ fontSize: '12px' }} />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)' }}>Base URL</label>
                    <input type="text" defaultValue="https://api.tokenfactory.nebius.com/v1" style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }} />
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '11px', color: 'var(--text-muted)', paddingTop: '6px', borderTop: '1px solid var(--border-subtle)' }}>
                  <span>✓ Dynamic catalog discovery</span>
                  <span>✓ OpenAI-compatible endpoint</span>
                  <span>✓ Fallback offline safety</span>
                </div>
              </div>
            </div>
          )}

          {/* About */}
          {activeSection === 'about' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>About AI Supervisor</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  The supervisory operations layer for autonomous developer agent fleets.
                </p>
              </div>

              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                <strong>The core product idea:</strong><br />
                The agents are replaceable. The Supervisor is the product.<br />
                Supervisor understands intent, generates structured plans, supervises real-time execution, intercepts loops, coordinates handoffs, and executes independent verification in an isolated sandbox.
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', fontSize: '11px', color: 'var(--text-muted)' }}>
                <div>Control Plane: <strong>v1.0.0</strong></div>
                <div>Storage: <strong>SQLite (WAL mode)</strong></div>
                <div>Architecture: <strong>Event-driven IPC</strong></div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
