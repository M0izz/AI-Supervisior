import React, { useState } from 'react';
import { 
  Database, 
  Plus, 
  Search,
  AlertTriangle,
  FileCode,
  ShieldCheck
} from 'lucide-react';
import type { MemoryRecord, Mission } from '../types';
import { addMemoryRecord } from '../api';

interface ProjectMemoryProps {
  memoryRecords: MemoryRecord[];
  missions: Mission[];
  onRefresh: () => void;
}

export const ProjectMemory: React.FC<ProjectMemoryProps> = ({
  memoryRecords,
  missions,
  onRefresh
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newCategory, setNewCategory] = useState<'VERIFIED_FACT' | 'REJECTED_APPROACH' | 'DECISION' | 'FAILURE' | 'DISCOVERY'>('VERIFIED_FACT');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const safeRecords = Array.isArray(memoryRecords) ? memoryRecords : [];
  const safeMissions = Array.isArray(missions) ? missions : [];

  const filterTabs = [
    { id: 'ALL', label: 'All' },
    { id: 'VERIFIED', label: 'Verified' },
    { id: 'DECISION', label: 'Decisions' },
    { id: 'REJECTED', label: 'Rejected' },
    { id: 'FAILURE', label: 'Failures' },
    { id: 'DISCOVERY', label: 'Discoveries' }
  ];

  const filteredRecords = safeRecords.filter(rec => {
    const cat = (rec.category || rec.type || rec.status || '').toUpperCase();
    if (selectedCategory !== 'ALL') {
      if (selectedCategory === 'VERIFIED' && !cat.includes('VERIF')) return false;
      if (selectedCategory === 'DECISION' && !cat.includes('DECIS')) return false;
      if (selectedCategory === 'REJECTED' && !cat.includes('REJECT')) return false;
      if (selectedCategory === 'FAILURE' && !cat.includes('FAIL')) return false;
      if (selectedCategory === 'DISCOVERY' && !cat.includes('DISCOV')) return false;
    }
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const content = (rec.fact || rec.content || '').toLowerCase();
      const missionId = (rec.mission_id || '').toLowerCase();
      return content.includes(q) || missionId.includes(q);
    }
    return true;
  });

  const handleCreateMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    setIsSubmitting(true);
    try {
      const primaryMissionId = safeMissions[0]?.id || 'global';
      await addMemoryRecord(primaryMissionId, {
        fact: newContent.trim(),
        source: 'supervisor_verification',
        created_by: 'human_operator',
        category: newCategory.toLowerCase(),
        status: newCategory === 'VERIFIED_FACT' ? 'VERIFIED' : 'OBSERVED',
        confidence: 1.0,
        details: 'Verified architectural knowledge'
      });
      setNewContent('');
      setIsAdding(false);
      onRefresh();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1080px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-title">
          <h1>Project Memory</h1>
          <p>
            What Supervisor has learned about this project. Facts, decisions, and failure patterns that persist across agents.
          </p>
        </div>

        <div className="page-header-actions">
          <button className="btn btn-primary" onClick={() => setIsAdding(!isAdding)}>
            <Plus size={14} />
            <span>Add Memory Record</span>
          </button>
        </div>
      </div>

      {/* New Memory Inline Form */}
      {isAdding && (
        <form onSubmit={handleCreateMemory} className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '14px', borderColor: 'var(--primary-border)' }}>
          <div style={{ fontWeight: 600, fontSize: '13px' }}>Record Knowledge for Agent Fleet</div>

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '220px' }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Category</label>
              <select
                value={newCategory}
                onChange={e => setNewCategory(e.target.value as any)}
              >
                <option value="VERIFIED_FACT">Verified Fact</option>
                <option value="DECISION">Architecture Decision</option>
                <option value="REJECTED_APPROACH">Rejected Approach</option>
                <option value="FAILURE">Known Failure Mode</option>
                <option value="DISCOVERY">Codebase Discovery</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1, minWidth: '240px' }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Statement</label>
              <input
                type="text"
                placeholder="e.g. CSV parser must support UTF-8 BOM encoding without corruption"
                value={newContent}
                onChange={e => setNewContent(e.target.value)}
                autoFocus
                required
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setIsAdding(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : 'Save Knowledge'}
            </button>
          </div>
        </form>
      )}

      {/* Filter and Search Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {filterTabs.map(f => (
            <button
              key={f.id}
              className={`btn btn-sm ${selectedCategory === f.id ? 'btn-secondary' : 'btn-ghost'}`}
              style={{ fontWeight: selectedCategory === f.id ? 600 : 400 }}
              onClick={() => setSelectedCategory(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div style={{ position: 'relative', width: '260px' }}>
          <input
            type="text"
            placeholder="Search memory..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            style={{ width: '100%', paddingLeft: '32px' }}
          />
          <Search size={14} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
        </div>
      </div>

      {/* Records Cards */}
      {filteredRecords.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <Database size={18} />
          </div>
          <div className="empty-state-title">Nothing learned yet</div>
          <div className="empty-state-desc">
            {searchTerm 
              ? `No memory records match "${searchTerm}".` 
              : 'Verified facts, architectural decisions, and rejected approaches will appear here as Supervisor works.'}
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '14px' }}>
          {filteredRecords.map(rec => {
            const cat = (rec.category || rec.type || rec.status || '').toUpperCase();
            const isRejected = cat.includes('REJECT');
            const isFailure = cat.includes('FAIL');
            const isDecision = cat.includes('DECIS');

            let typeLabel = 'VERIFIED FACT';
            let badgeClass = 'badge-green';
            let borderColor = 'var(--success)';
            let Icon = ShieldCheck;

            if (isRejected) {
              typeLabel = 'REJECTED APPROACH';
              badgeClass = 'badge-amber';
              borderColor = 'var(--warning)';
              Icon = AlertTriangle;
            } else if (isFailure) {
              typeLabel = 'FAILURE MODE';
              badgeClass = 'badge-red';
              borderColor = 'var(--danger)';
              Icon = AlertTriangle;
            } else if (isDecision) {
              typeLabel = 'ARCHITECTURE DECISION';
              badgeClass = 'badge-blue';
              borderColor = 'var(--primary)';
              Icon = FileCode;
            }

            // Find related mission title
            const relatedMission = safeMissions.find(m => m.id === rec.mission_id);
            const missionDisplay = relatedMission?.title || (rec.mission_id ? `Mission #${rec.mission_id.slice(0, 8)}` : 'Global Project');

            return (
              <div 
                key={rec.id} 
                className="surface-card"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '14px',
                  borderLeft: `3px solid ${borderColor}`,
                  padding: '16px 18px'
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span className={`badge ${badgeClass}`} style={{ fontSize: '10px', letterSpacing: '0.04em' }}>
                      <Icon size={11} />
                      <span>{typeLabel}</span>
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {new Date(rec.created_at).toLocaleDateString()}
                    </span>
                  </div>

                  <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', lineHeight: 1.5 }}>
                    {rec.fact || rec.content}
                  </div>
                </div>

                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: '8px',
                  paddingTop: '10px',
                  borderTop: '1px solid var(--border-subtle)',
                  fontSize: '11px'
                }}>
                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>Confidence</div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                      {Math.round((rec.confidence || 1) * 100)}%
                    </div>
                  </div>

                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>Verified By</div>
                    <div style={{ color: 'var(--text-secondary)', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {rec.source === 'supervisor_verification' ? 'Test suite' : rec.source || 'Supervisor'}
                    </div>
                  </div>

                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>Related Mission</div>
                    <div style={{ color: 'var(--text-secondary)', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {missionDisplay}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
