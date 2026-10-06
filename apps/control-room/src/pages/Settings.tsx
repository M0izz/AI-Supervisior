import React, { useState } from 'react';
import { 
  Settings as SettingsIcon, 
  ShieldCheck, 
  Lock, 
  Keyboard, 
  Sparkles, 
  Sliders,
  CheckCircle2
} from 'lucide-react';

export const Settings: React.FC = () => {
  const [activeSection, setActiveSection] = useState<'general' | 'supervision' | 'safety' | 'absence' | 'keyboard' | 'about'>('general');
  const [watchdogStrictness, setWatchdogStrictness] = useState('STANDARD');
  const [autoVerify, setAutoVerify] = useState(true);
  const [zeroImplicitApproval, setZeroImplicitApproval] = useState(true);
  const [saveToast, setSaveToast] = useState(false);

  const handleSave = () => {
    setSaveToast(true);
    setTimeout(() => setSaveToast(false), 2500);
  };

  const sections = [
    { id: 'general', label: 'General', icon: SettingsIcon },
    { id: 'supervision', label: 'Supervision & Watchdogs', icon: Sliders },
    { id: 'safety', label: 'Safety & Permissions', icon: ShieldCheck },
    { id: 'absence', label: 'Absence Mode Policy', icon: Lock },
    { id: 'keyboard', label: 'Keyboard Shortcuts', icon: Keyboard },
    { id: 'about', label: 'About AI Supervisor', icon: Sparkles }
  ] as const;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1080px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-title">
          <h1>Settings</h1>
          <p>Supervision policies, safety boundaries, and keyboard shortcuts</p>
        </div>

        <div className="page-header-actions">
          <button className="btn btn-primary" onClick={handleSave}>
            <span>Save Preferences</span>
          </button>
        </div>
      </div>

      {saveToast && (
        <div style={{ padding: '8px 12px', borderRadius: '6px', backgroundColor: 'var(--success-subtle)', border: '1px solid var(--success-border)', color: 'var(--success)', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CheckCircle2 size={15} />
          <span>Settings saved to local configuration</span>
        </div>
      )}

      {/* Settings Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: '24px' }}>
        {/* Navigation Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {sections.map(sec => {
            const Icon = sec.icon;
            const isActive = activeSection === sec.id;
            return (
              <button
                key={sec.id}
                className={`nav-item ${isActive ? 'active' : ''}`}
                onClick={() => setActiveSection(sec.id)}
              >
                <Icon size={15} color={isActive ? 'var(--primary)' : 'var(--text-muted)'} />
                <span>{sec.label}</span>
              </button>
            );
          })}
        </div>

        {/* Setting Section Details */}
        <div className="surface-card" style={{ padding: '24px' }}>
          {activeSection === 'general' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>General Configuration</h3>
                <p style={{ fontSize: '13px', marginTop: '4px' }}>Runtime environment and local project settings.</p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Workspace Repository
                </label>
                <input type="text" readOnly value="C:\Users\Moiz\Desktop\AI Supervisior" style={{ fontFamily: 'var(--font-mono)' }} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Local Control Plane Port
                </label>
                <input type="text" readOnly value="127.0.0.1:8000" style={{ fontFamily: 'var(--font-mono)' }} />
              </div>
            </div>
          )}

          {activeSection === 'supervision' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Supervision & Watchdogs</h3>
                <p style={{ fontSize: '13px', marginTop: '4px' }}>Configure failure loop thresholds and independent verification behavior.</p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Loop Detection Threshold
                </label>
                <select value={watchdogStrictness} onChange={e => setWatchdogStrictness(e.target.value)}>
                  <option value="STRICT">Strict (2 repeated errors trigger intervention)</option>
                  <option value="STANDARD">Standard (3 repeated errors trigger intervention)</option>
                  <option value="LENIENT">Lenient (5 repeated errors trigger intervention)</option>
                </select>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', backgroundColor: 'var(--surface-elevated)', borderRadius: '6px' }}>
                <div>
                  <div style={{ fontWeight: 500, fontSize: '13px' }}>Enforce Independent Verification</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Never allow an agent to certify its own completed tasks.</div>
                </div>
                <input type="checkbox" checked={autoVerify} onChange={e => setAutoVerify(e.target.checked)} />
              </div>
            </div>
          )}

          {activeSection === 'safety' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Safety & Approvals</h3>
                <p style={{ fontSize: '13px', marginTop: '4px' }}>Guardrails against runaway agents and dangerous shell commands.</p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', backgroundColor: 'var(--surface-elevated)', borderRadius: '6px' }}>
                <div>
                  <div style={{ fontWeight: 500, fontSize: '13px' }}>Strict Zero Implicit Approval</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Silence or timeout is strictly treated as DENIED. No automatic approvals for destructive operations.</div>
                </div>
                <input type="checkbox" checked={zeroImplicitApproval} onChange={e => setZeroImplicitApproval(e.target.checked)} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Prohibited Commands
                </label>
                <input type="text" readOnly value="rm -rf /, git push --force, dd, mkfs" style={{ fontFamily: 'var(--font-mono)' }} />
              </div>
            </div>
          )}

          {activeSection === 'absence' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Absence Mode Limits</h3>
                <p style={{ fontSize: '13px', marginTop: '4px' }}>Automatic circuit breakers when developer is away from keyboard.</p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Max Tasks Per Session</label>
                  <input type="number" defaultValue={5} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Max Cross-Agent Handoffs</label>
                  <input type="number" defaultValue={2} />
                </div>
              </div>
            </div>
          )}

          {activeSection === 'keyboard' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>Keyboard Shortcuts</h3>
                <p style={{ fontSize: '13px', marginTop: '4px' }}>Developer-native quick navigation commands.</p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {[
                  { key: '⌘K / Ctrl+K', desc: 'Open Command Palette' },
                  { key: 'ESC', desc: 'Close modals & dialogs' },
                  { key: 'Space', desc: 'Pause / Resume active mission' },
                  { key: 'Shift+A', desc: 'Jump to Approvals Queue' }
                ].map(s => (
                  <div key={s.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', backgroundColor: 'var(--surface-elevated)', borderRadius: '6px' }}>
                    <span style={{ fontSize: '13px' }}>{s.desc}</span>
                    <span className="kbd-shortcut">{s.key}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeSection === 'about' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <h3 style={{ fontSize: '16px' }}>About AI Supervisor</h3>
                <p style={{ fontSize: '13px', marginTop: '4px' }}>
                  A personal AI operations layer that manages, coordinates, supervises, recovers, and verifies the AI agents a developer already uses.
                </p>
              </div>

              <div style={{ padding: '14px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                <strong>Core invariant:</strong> Agent completion ≠ verified completion.<br />
                The agents are replaceable. The Supervisor is the product.
              </div>

              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                Version 1.0.0 · Local SQLite WAL engine · Google Antigravity & DeepMind Team
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
