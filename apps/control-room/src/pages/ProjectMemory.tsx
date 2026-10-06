import React, { useState } from 'react';
import { 
  Database, 
  Plus, 
  Search 
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
  const [newCategory, setNewCategory] = useState<'VERIFIED_FACT' | 'REJECTED_APPROACH' | 'DECISION'>('VERIFIED_FACT');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const safeRecords = Array.isArray(memoryRecords) ? memoryRecords : [];
  const safeMissions = Array.isArray(missions) ? missions : [];

  const filteredRecords = safeRecords.filter(rec => {
    const cat = (rec.category || rec.type || rec.status || '').toUpperCase();
    if (selectedCategory !== 'ALL' && !cat.includes(selectedCategory)) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const content = (rec.fact || rec.content || '').toLowerCase();
      return content.includes(q);
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
        source: 'supervisor_operator',
        created_by: 'human_operator',
        category: newCategory.toLowerCase(),
        status: newCategory === 'VERIFIED_FACT' ? 'VERIFIED' : 'OBSERVED',
        confidence: 1.0,
        details: 'Manually verified architectural constraint'
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
            Facts, architectural decisions, and rejected approaches that persist across agents and missions.
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

          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '200px' }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Category</label>
              <select
                value={newCategory}
                onChange={e => setNewCategory(e.target.value as any)}
              >
                <option value="VERIFIED_FACT">Verified Fact</option>
                <option value="REJECTED_APPROACH">Rejected Approach</option>
                <option value="DECISION">Architecture Decision</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Description</label>
              <input
                type="text"
                placeholder="e.g. CSV parser requires UTF-8 without BOM due to header parsing bug"
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

      {/* Filter and Search */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          {[
            { id: 'ALL', label: 'All Knowledge' },
            { id: 'VERIF', label: 'Verified Facts' },
            { id: 'REJECT', label: 'Rejected Approaches' },
            { id: 'DECISION', label: 'Decisions' }
          ].map(f => (
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
            placeholder="Search memory records..."
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
          <div className="empty-state-title">No memory records found</div>
          <div className="empty-state-desc">
            Project memory is automatically accumulated as agents execute tasks and verification discovers facts, or you can record custom facts manually.
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '14px' }}>
          {filteredRecords.map(rec => {
            const cat = (rec.category || rec.type || rec.status || '').toUpperCase();
            const isVerified = cat.includes('VERIF');
            const isRejected = cat.includes('REJECT');

            return (
              <div 
                key={rec.id} 
                className="surface-card"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '12px',
                  borderLeft: isVerified ? '3px solid var(--success)' : isRejected ? '3px solid var(--danger)' : '3px solid var(--primary)'
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span className={`badge ${isVerified ? 'badge-green' : isRejected ? 'badge-red' : 'badge-blue'}`}>
                      {isVerified ? 'Verified Fact' : isRejected ? 'Rejected Approach' : 'Architecture Decision'}
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      {new Date(rec.created_at).toLocaleDateString()}
                    </span>
                  </div>

                  <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', lineHeight: 1.5 }}>
                    {rec.fact || rec.content}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
                  <span>Source: {rec.source || 'supervisor_verification'}</span>
                  <span>Confidence: {Math.round((rec.confidence || 1) * 100)}%</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
