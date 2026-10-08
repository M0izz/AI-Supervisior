import React, { useState, useEffect } from 'react';
import { 
  X, 
  Sparkles, 
  Target, 
  Sliders, 
  ChevronDown, 
  ChevronUp, 
  AlertCircle,
  CheckCircle2,
  Cpu
} from 'lucide-react';
import { draftMission, createMission, type DraftMissionResponse } from '../api';
import type { Mission } from '../types';

interface MissionComposerProps {
  isOpen: boolean;
  onClose: () => void;
  onMissionStarted: (mission: Mission) => void;
  initialPrompt?: string;
}

export const MissionComposer: React.FC<MissionComposerProps> = ({
  isOpen,
  onClose,
  onMissionStarted,
  initialPrompt = ''
}) => {
  const [goalInput, setGoalInput] = useState(initialPrompt);
  const [repositoryPath, setRepositoryPath] = useState('./demo/sample-project');
  const [isUnderstanding, setIsUnderstanding] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Interpretation state from Supervisor
  const [draft, setDraft] = useState<DraftMissionResponse | null>(null);
  const [showConstraints, setShowConstraints] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showPlanTasks, setShowPlanTasks] = useState(false);

  // Optional constraints (Section 2)
  const [noDbSchemaChange, setNoDbSchemaChange] = useState(false);
  const [frontendOnly, setFrontendOnly] = useState(false);
  const [backwardsCompatible, setBackwardsCompatible] = useState(true);
  const [noNewDeps, setNoNewDeps] = useState(false);

  // Advanced overrides (progressive disclosure)
  const [agentPreference, setAgentPreference] = useState('auto');
  const [modelPreference, setModelPreference] = useState('auto');
  const [maxTurns, setMaxTurns] = useState(10);
  const [prohibitedFiles, setProhibitedFiles] = useState('.env, secrets.json, id_rsa');
  const [verificationReq, setVerificationReq] = useState('STRICT');

  useEffect(() => {
    if (isOpen) {
      if (initialPrompt) {
        setGoalInput(prev => prev || initialPrompt);
      }
      setError(null);
    }
  }, [isOpen, initialPrompt]);

  if (!isOpen) return null;

  const examplePrompts = [
    "Fix the authentication bug in my app and make sure existing tests pass",
    "Build a CSV import system with malformed row validation",
    "Make the dashboard faster by optimizing heavy renders",
    "Add dark mode without changing existing navigation",
    "Review this repository for security issues and fix safe ones",
    "Get all failing tests passing cleanly"
  ];

  const handleInterpretGoal = async (promptToUse?: string) => {
    const text = (promptToUse || goalInput).trim();
    if (!text) return;

    if (promptToUse) {
      setGoalInput(promptToUse);
    }

    setIsUnderstanding(true);
    setError(null);
    try {
      const result = await draftMission({
        goal: text,
        repository_path: repositoryPath
      });
      setDraft(result);
    } catch (err: any) {
      setError(err.message || 'Failed to interpret goal');
    } finally {
      setIsUnderstanding(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!draft) {
        handleInterpretGoal();
      }
    }
  };

  const handleStartMission = async () => {
    if (!draft && !goalInput.trim()) return;
    setIsStarting(true);
    setError(null);

    try {
      const prohibitedList = prohibitedFiles
        .split(',')
        .map(f => f.trim())
        .filter(Boolean);

      if (noDbSchemaChange) {
        prohibitedList.push('migrations/*', 'schema.sql', '*.prisma');
      }

      const missionTitle = draft?.title || goalInput.trim();
      const missionGoal = draft?.goal || goalInput.trim();

      const created = await createMission({
        title: missionTitle,
        goal: missionGoal,
        repository_path: repositoryPath.trim() || './demo/sample-project',
        constraints: {
          max_turns: maxTurns,
          timeout_seconds: 3600,
          prohibited_files: prohibitedList,
          allowed_commands: ['pytest', 'git status', 'git diff', 'npm test']
        },
        tasks: draft?.proposed_tasks
      });

      onMissionStarted(created);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to initialize mission on backend');
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div 
        className="modal-content" 
        onClick={e => e.stopPropagation()}
        style={{ maxWidth: '680px', maxHeight: '90vh' }}
      >
        {/* Header */}
        <div className="modal-header" style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{
              width: '26px',
              height: '26px',
              borderRadius: '6px',
              backgroundColor: 'var(--primary-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Sparkles size={14} color="var(--primary)" />
            </div>
            <div>
              <h2 style={{ fontSize: '15px', fontWeight: 600 }}>Start a new mission</h2>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Tell Supervisor what outcome you want accomplished.</div>
            </div>
          </div>

          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="modal-body" style={{ padding: '20px', gap: '18px', overflowY: 'auto' }}>
          {error && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 12px',
              borderRadius: '6px',
              backgroundColor: 'var(--danger-subtle)',
              border: '1px solid var(--danger-border)',
              color: 'var(--danger)',
              fontSize: '13px'
            }}>
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
          )}

          {/* Natural Language Prompt Area */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                What do you want to get done?
              </label>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                Press Enter to generate plan
              </span>
            </div>

            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '2px' }}>
              Describe the outcome in your own words. Supervisor will break it down, choose the right agents, and verify the result.
            </div>

            <textarea
              rows={3}
              placeholder="Fix the authentication bug in my app and make sure existing tests still pass..."
              value={goalInput}
              onChange={e => {
                setGoalInput(e.target.value);
                if (draft) setDraft(null);
              }}
              onKeyDown={handleKeyDown}
              autoFocus
              style={{
                fontSize: '14px',
                lineHeight: '1.5',
                padding: '12px 14px',
                borderRadius: '8px',
                borderColor: draft ? 'var(--primary-border)' : 'var(--border)'
              }}
            />

            {/* Clickable Example Prompts (only when draft not generated) */}
            {!draft && !isUnderstanding && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Examples:</span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {examplePrompts.map(ex => (
                    <button
                      key={ex}
                      type="button"
                      className="badge badge-neutral"
                      style={{ padding: '4px 8px', fontSize: '11px', cursor: 'pointer', textAlign: 'left' }}
                      onClick={() => handleInterpretGoal(ex)}
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Optional Constraints (Section 2) */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '10px' }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ color: 'var(--text-secondary)', fontSize: '12px', padding: '2px 0' }}
              onClick={() => setShowConstraints(!showConstraints)}
            >
              <Sliders size={13} />
              <span>Optional constraints</span>
              {showConstraints ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>

            {showConstraints && (
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '8px',
                marginTop: '10px',
                padding: '12px',
                borderRadius: '6px',
                backgroundColor: 'var(--surface-elevated)',
                border: '1px solid var(--border-subtle)'
              }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={noDbSchemaChange}
                    onChange={e => setNoDbSchemaChange(e.target.checked)}
                  />
                  <span>Don't modify database schema</span>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={frontendOnly}
                    onChange={e => setFrontendOnly(e.target.checked)}
                  />
                  <span>Only modify frontend code</span>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={backwardsCompatible}
                    onChange={e => setBackwardsCompatible(e.target.checked)}
                  />
                  <span>Keep API backwards compatible</span>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={noNewDeps}
                    onChange={e => setNoNewDeps(e.target.checked)}
                  />
                  <span>Don't add new dependencies</span>
                </label>
              </div>
            )}
          </div>

          {/* Supervisor Will Guarantee List (Shown before plan) */}
          {!draft && !isUnderstanding && (
            <div style={{
              padding: '12px 14px',
              borderRadius: '6px',
              backgroundColor: 'var(--surface-elevated)',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px'
            }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Supervisor will:
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={13} color="var(--success)" />
                  <span>Understand the goal</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={13} color="var(--success)" />
                  <span>Break it into tasks</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={13} color="var(--success)" />
                  <span>Choose best available agent</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={13} color="var(--success)" />
                  <span>Watch & supervise execution</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={13} color="var(--success)" />
                  <span>Verify result independently</span>
                </div>
              </div>
            </div>
          )}

          {/* Supervisor Understanding State */}
          {isUnderstanding && (
            <div style={{
              padding: '16px',
              borderRadius: '8px',
              backgroundColor: 'var(--surface-elevated)',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600, color: 'var(--primary)' }}>
                <span className="status-dot watching spin" />
                <span>Supervisor is reasoning about your goal...</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)', paddingLeft: '14px' }}>
                <div>● Decomposing goal with Gemma 4 assistance</div>
                <div>● Verifying repository invariants: {repositoryPath}</div>
                <div>○ Formulating execution plan</div>
                <div>○ Determining agent routing strategy</div>
              </div>
            </div>
          )}

          {/* Smart Preview Before Execution (Section 3, 6) */}
          {draft && !isUnderstanding && (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
              padding: '16px',
              borderRadius: '8px',
              backgroundColor: 'var(--surface-elevated)',
              border: '1px solid var(--border)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sparkles size={15} color="var(--primary)" />
                  <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                    Supervisor understood:
                  </span>
                </div>
                <span className="badge badge-blue">Plan Ready</span>
              </div>

              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Goal</div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {draft.title}
                </div>
              </div>

              {/* 3-Phase High-Level Flow (Section 1, 3) */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: '8px',
                padding: '10px 12px',
                borderRadius: '6px',
                backgroundColor: 'var(--bg)',
                border: '1px solid var(--border-subtle)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                  <span style={{ color: 'var(--success)', fontWeight: 600 }}>✓</span>
                  <span style={{ color: 'var(--text-primary)' }}>Understand Goal</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                  <span className="status-dot running" style={{ width: '8px', height: '8px' }} />
                  <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>Execute Solution</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>○</span>
                  <span style={{ color: 'var(--text-muted)' }}>Verify Independently</span>
                </div>
              </div>

              {/* Detected Invariants if present */}
              {draft.detected_invariants && draft.detected_invariants.length > 0 && (
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                    Preserved Invariants
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {draft.detected_invariants.map((inv: string, idx: number) => (
                      <span key={idx} className="badge badge-neutral" style={{ fontSize: '11px' }}>
                        🛡 {inv}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Agent Strategy & Verification Row */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Agent strategy</div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px', fontFamily: 'var(--font-mono)' }}>
                    {draft.suggested_agents[0] || 'Claude Code'} &rarr; {draft.fallback_agent || 'Codex'} (fallback)
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Verification</div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--success)', marginTop: '2px' }}>
                    Independent Tests + Scope Verification
                  </div>
                </div>
              </div>

              {/* Technical Plan Drawer */}
              <div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ padding: '2px 0', fontSize: '11px', color: 'var(--text-muted)' }}
                  onClick={() => setShowPlanTasks(!showPlanTasks)}
                >
                  {showPlanTasks ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  <span>{showPlanTasks ? 'Hide task graph' : `Inspect ${draft.proposed_tasks.length} technical execution steps`}</span>
                </button>

                {showPlanTasks && (
                  <div style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '11px',
                    backgroundColor: 'var(--bg)',
                    padding: '10px 12px',
                    borderRadius: '6px',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-secondary)',
                    lineHeight: 1.6,
                    marginTop: '8px'
                  }}>
                    {draft.proposed_tasks.map((t, i) => {
                      const isLast = i === draft.proposed_tasks.length - 1;
                      return (
                        <div key={t.id || i}>
                          <span style={{ color: 'var(--text-muted)' }}>{isLast ? '└── ' : '├── '}</span>
                          <span style={{ color: 'var(--text-primary)' }}>{t.title}</span>
                          <span style={{ color: 'var(--text-muted)', marginLeft: '8px' }}>({t.suggested_agent})</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {draft.model_provenance && (
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Cpu size={11} />
                  <span>{draft.model_provenance}</span>
                </div>
              )}
            </div>
          )}

          {/* Progressive Disclosure: Advanced Controls (Section 5) */}
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '10px' }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ color: 'var(--text-muted)', fontSize: '12px', padding: '4px 0' }}
              onClick={() => setShowAdvanced(!showAdvanced)}
            >
              <Sliders size={13} />
              <span>Advanced controls</span>
              {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>

            {showAdvanced && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                    Repository Context
                  </label>
                  <input
                    type="text"
                    value={repositoryPath}
                    onChange={e => setRepositoryPath(e.target.value)}
                    style={{ fontSize: '12px' }}
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                    Preferred Agent Runtime
                  </label>
                  <select
                    value={agentPreference}
                    onChange={e => setAgentPreference(e.target.value)}
                    style={{ fontSize: '12px' }}
                  >
                    <option value="auto">Auto-Route (Supervisor Optimal)</option>
                    <option value="claude-code">Claude Code (Anthropic)</option>
                    <option value="codex">OpenAI Codex</option>
                    <option value="hermes">Hermes Agent (Nous)</option>
                    <option value="gemini">Gemini CLI</option>
                    <option value="goose">Goose (Block)</option>
                    <option value="cline">Cline</option>
                    <option value="qwen">Qwen Local</option>
                    <option value="opencode">OpenCode</option>
                    <option value="kimi">Kimi Code</option>
                  </select>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                    Inference Model Preference
                  </label>
                  <select
                    value={modelPreference}
                    onChange={e => setModelPreference(e.target.value)}
                    style={{ fontSize: '12px' }}
                  >
                    <option value="auto">Auto-Select Model</option>
                    <option value="gemma-4-31B-it">Google Gemma 4 (Supervisory Planning)</option>
                    <option value="gemini-1.5-pro">Google Gemini 1.5 Pro</option>
                    <option value="hermes-4-70b-instruct">Nous Hermes 4 (Nebius)</option>
                    <option value="qwen-2.5-coder-32b">Qwen 2.5 Coder (Nebius)</option>
                    <option value="claude-3-7-sonnet">Claude 3.7 Sonnet</option>
                  </select>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                    Turn Budget Limit
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={maxTurns}
                    onChange={e => setMaxTurns(parseInt(e.target.value, 10) || 10)}
                    style={{ fontSize: '12px' }}
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                    Verification Strictness
                  </label>
                  <select
                    value={verificationReq}
                    onChange={e => setVerificationReq(e.target.value)}
                    style={{ fontSize: '12px' }}
                  >
                    <option value="STRICT">Strict (Isolated sandbox + Scope diff)</option>
                    <option value="STANDARD">Standard (Unit tests pass)</option>
                  </select>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', gridColumn: '1 / -1' }}>
                  <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                    Prohibited Sensitive Files
                  </label>
                  <input
                    type="text"
                    value={prohibitedFiles}
                    onChange={e => setProhibitedFiles(e.target.value)}
                    style={{ fontSize: '12px' }}
                  />
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    Watchdog intercepts any agent attempting to modify these paths.
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Modal Footer Actions */}
        <div className="modal-footer" style={{ padding: '14px 20px', borderTop: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg)' }}>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={isStarting || isUnderstanding}>
            Cancel
          </button>

          {!draft ? (
            <button 
              type="button" 
              className="btn btn-primary" 
              onClick={() => handleInterpretGoal()}
              disabled={isUnderstanding || !goalInput.trim()}
            >
              <Sparkles size={13} />
              <span>{isUnderstanding ? 'Reasoning...' : 'Generate Plan'}</span>
            </button>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDraft(null)}
                disabled={isStarting}
              >
                Edit Request
              </button>

              <button 
                type="button" 
                className="btn btn-primary" 
                onClick={handleStartMission}
                disabled={isStarting}
              >
                <Target size={13} />
                <span>{isStarting ? 'Starting Supervision...' : 'Start Mission →'}</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
