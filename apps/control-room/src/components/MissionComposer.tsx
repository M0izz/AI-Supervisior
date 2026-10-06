import React, { useState, useEffect } from 'react';
import { 
  X, 
  Sparkles, 
  Target, 
  Sliders, 
  ChevronDown, 
  ChevronUp, 
  AlertCircle,
  CheckCircle2
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
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showPlanTasks, setShowPlanTasks] = useState(false);

  // Advanced overrides (progressive disclosure)
  const [agentPreference, setAgentPreference] = useState('claude-code');
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
    "Add dark mode without changing the existing navigation",
    "Find why the API is returning 500 errors and fix the root cause",
    "Review this project for obvious security issues and fix anything safe to fix",
    "Improve the loading performance of the dashboard",
    "Add CSV import support and validate malformed files"
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
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Tell Supervisor what you want to accomplish.</div>
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
                Press Enter to interpret · Shift+Enter for newline
              </span>
            </div>

            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '2px' }}>
              Describe the outcome in your own words. Supervisor will break it down, choose the right agents, and verify the result.
            </div>

            <textarea
              rows={3}
              placeholder="Fix the authentication bug in my app and make sure the existing tests still pass..."
              value={goalInput}
              onChange={e => {
                setGoalInput(e.target.value);
                if (draft) setDraft(null); // Reset draft if user modifies prompt
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
                  <span>Monitor execution</span>
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
                <span>Supervisor is understanding your mission</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)', paddingLeft: '14px' }}>
                <div>● Identifying primary goal and edge cases</div>
                <div>● Detecting repository context: {repositoryPath}</div>
                <div>○ Building execution task graph</div>
                <div>○ Selecting primary and fallback agent workers</div>
              </div>
            </div>
          )}

          {/* Smart Preview Before Execution (Section 6) */}
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

              {/* Proposed Plan Tree */}
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                  Plan ({draft.proposed_tasks.length} tasks)
                </div>
                <div style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  backgroundColor: 'var(--bg)',
                  padding: '10px 12px',
                  borderRadius: '6px',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-secondary)',
                  lineHeight: 1.6
                }}>
                  {draft.proposed_tasks.map((t, i) => {
                    const isLast = i === draft.proposed_tasks.length - 1;
                    return (
                      <div key={t.id || i}>
                        <span style={{ color: 'var(--text-muted)' }}>{isLast ? '└── ' : '├── '}</span>
                        <span style={{ color: 'var(--text-primary)' }}>{t.title}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

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
                    Tests + Scope + Regression
                  </div>
                </div>
              </div>

              {/* Toggle to inspect decomposed tasks */}
              <div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ padding: '2px 0', fontSize: '11px', color: 'var(--text-muted)' }}
                  onClick={() => setShowPlanTasks(!showPlanTasks)}
                >
                  {showPlanTasks ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  <span>{showPlanTasks ? 'Hide task details' : 'Review task graph breakdown'}</span>
                </button>

                {showPlanTasks && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px' }}>
                    {draft.proposed_tasks.map((t, i) => (
                      <div key={t.id || i} style={{ padding: '8px 10px', borderRadius: '4px', backgroundColor: 'var(--bg)', border: '1px solid var(--border-subtle)', fontSize: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <span style={{ fontWeight: 500 }}>{t.title}</span>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{t.description}</div>
                        </div>
                        <span className="badge badge-neutral" style={{ fontSize: '10px' }}>{t.suggested_agent}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Progressive Disclosure: Advanced Controls */}
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
                    Preferred Agent
                  </label>
                  <select
                    value={agentPreference}
                    onChange={e => setAgentPreference(e.target.value)}
                    style={{ fontSize: '12px' }}
                  >
                    <option value="claude-code">Claude Code (Anthropic)</option>
                    <option value="codex">OpenAI Codex</option>
                    <option value="gemini">Gemini CLI</option>
                    <option value="qwen">Qwen Local</option>
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
                    <option value="STRICT">Strict (Isolated sandbox tests + AST)</option>
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
                    Watchdog immediately intercepts any agent modifying these paths.
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
              <span>{isUnderstanding ? 'Interpreting...' : 'Generate Plan'}</span>
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
