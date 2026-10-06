import React, { useState } from 'react';
import { X, Target, AlertCircle } from 'lucide-react';
import { createMission } from '../api';
import type { Mission } from '../types';

interface CreateMissionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onMissionCreated: (mission: Mission) => void;
}

export const CreateMissionModal: React.FC<CreateMissionModalProps> = ({
  isOpen,
  onClose,
  onMissionCreated
}) => {
  const [title, setTitle] = useState('');
  const [goal, setGoal] = useState('');
  const [repositoryPath, setRepositoryPath] = useState('./demo/sample-project');
  const [maxTurns, setMaxTurns] = useState(10);
  const [prohibitedFiles, setProhibitedFiles] = useState('.env, secrets.json');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !goal.trim()) {
      setError('Please provide both a mission title and an objective.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const prohibitedList = prohibitedFiles
        .split(',')
        .map(f => f.trim())
        .filter(Boolean);

      const created = await createMission({
        title: title.trim(),
        goal: goal.trim(),
        repository_path: repositoryPath.trim() || './demo/sample-project',
        constraints: {
          max_turns: maxTurns,
          timeout_seconds: 3600,
          prohibited_files: prohibitedList,
          allowed_commands: ['pytest', 'git status', 'git diff', 'npm test']
        }
      });

      onMissionCreated(created);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to initialize mission on backend');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Target size={16} color="var(--primary)" />
            <h2>Start Supervised Mission</h2>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
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

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                Mission Title
              </label>
              <input
                type="text"
                placeholder="e.g. Fix authentication timeout bug"
                value={title}
                onChange={e => setTitle(e.target.value)}
                autoFocus
                required
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                Goal & Objective
              </label>
              <textarea
                rows={3}
                placeholder="Describe what the agent must accomplish. The Supervisor will plan tasks and verify results."
                value={goal}
                onChange={e => setGoal(e.target.value)}
                required
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                  Workspace Repository
                </label>
                <input
                  type="text"
                  placeholder="./demo/sample-project"
                  value={repositoryPath}
                  onChange={e => setRepositoryPath(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                  Max Turn Budget
                </label>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={maxTurns}
                  onChange={e => setMaxTurns(parseInt(e.target.value, 10) || 10)}
                />
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                Prohibited Sensitive Files (Watchdog Guard)
              </label>
              <input
                type="text"
                placeholder=".env, secrets.json, id_rsa"
                value={prohibitedFiles}
                onChange={e => setProhibitedFiles(e.target.value)}
              />
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                The Supervisor will block any agent modification attempt touching these paths.
              </span>
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Starting...' : 'Create Mission'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
