import React, { useState } from 'react';
import { 
  Database, 
  CheckCircle2, 
  AlertTriangle, 
  HelpCircle, 
  XCircle, 
  Search, 
  Plus, 
  ShieldCheck, 
  Layers, 
  User 
} from 'lucide-react';
import type { MemoryRecord, MemoryRecordType, Mission } from '../types';
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
  const [selectedType, setSelectedType] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [isAdding, setIsAdding] = useState<boolean>(false);
  const [newContent, setNewContent] = useState<string>('');
  const [newType, setNewType] = useState<MemoryRecordType>('VERIFIED_FACT');
  const [newMissionId, setNewMissionId] = useState<string>(missions[0]?.id || 'global');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const filteredRecords = memoryRecords.filter(rec => {
    const category = (rec.category || rec.type || '').toUpperCase();
    if (selectedType !== 'ALL' && category !== selectedType && rec.status !== selectedType) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const content = (rec.fact || rec.content || '').toLowerCase();
      const source = (rec.source || rec.provenance?.source || '').toLowerCase();
      const author = (rec.created_by || rec.provenance?.author || '').toLowerCase();
      if (!content.includes(term) && !source.includes(term) && !author.includes(term)) return false;
    }
    return true;
  });

  const handleCreateMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    setIsSubmitting(true);
    try {
      await addMemoryRecord(newMissionId, {
        fact: newContent,
        source: 'control_room_operator',
        created_by: 'human_supervisor',
        category: newType.toLowerCase(),
        status: newType === 'VERIFIED_FACT' ? 'VERIFIED' : 'OBSERVED',
        confidence: newType === 'VERIFIED_FACT' ? 1.0 : 0.85,
        details: 'Recorded via Control Room Project Memory interface'
      });
      setNewContent('');
      setIsAdding(false);
      onRefresh();
    } catch (err) {
      console.error('Failed to create memory record', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getTypeBadge = (rec: MemoryRecord) => {
    const cat = (rec.category || rec.type || rec.status || '').toUpperCase();
    if (cat.includes('VERIF')) {
      return <span className="badge badge-emerald"><CheckCircle2 size={11} /> VERIFIED FACT</span>;
    }
    if (cat.includes('INFER')) {
      return <span className="badge badge-cyan"><HelpCircle size={11} /> INFERRED FACT</span>;
    }
    if (cat.includes('REJECT')) {
      return <span className="badge badge-crimson"><XCircle size={11} /> REJECTED APPROACH</span>;
    }
    if (cat.includes('DIAGNOSIS')) {
      return <span className="badge badge-amber"><AlertTriangle size={11} /> DIAGNOSIS</span>;
    }
    if (cat.includes('RECOVERY')) {
      return <span className="badge badge-amber"><Layers size={11} /> RECOVERY CONTEXT</span>;
    }
    return <span className="badge badge-neutral"><ShieldCheck size={11} /> {cat || 'DECISION'}</span>;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Top Filter & Control Panel */}
      <div className="cr-panel" style={{ marginBottom: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Database size={16} color="var(--status-cyan)" />
            <h2 style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', textTransform: 'uppercase' }}>
              Project Knowledge & Empirical Memory Base
            </h2>
            <span className="badge badge-neutral">
              {filteredRecords.length} RECORDS
            </span>
          </div>

          <button 
            className="btn btn-primary" 
            onClick={() => setIsAdding(!isAdding)}
          >
            <Plus size={12} />
            <span>{isAdding ? 'CANCEL' : 'RECORD MEMORY FACT'}</span>
          </button>
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '12px', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '220px', position: 'relative' }}>
            <input 
              type="text" 
              placeholder="Search facts, diagnoses, rejected hypotheses, provenance..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ paddingLeft: '28px' }}
            />
            <Search size={14} style={{ position: 'absolute', left: '8px', top: '9px', color: 'var(--text-muted)' }} />
          </div>

          <div style={{ width: '220px' }}>
            <select 
              value={selectedType} 
              onChange={(e) => setSelectedType(e.target.value)}
            >
              <option value="ALL">All Categories</option>
              <option value="VERIFIED_FACT">Verified Facts</option>
              <option value="INFERRED_FACT">Inferred Facts</option>
              <option value="REJECTED_APPROACH">Rejected Approaches</option>
              <option value="DIAGNOSIS">Diagnoses</option>
              <option value="RECOVERY_CONTEXT">Recovery Context</option>
              <option value="DECISION">Decisions</option>
            </select>
          </div>
        </div>
      </div>

      {/* Add Memory Modal / Box */}
      {isAdding && (
        <form onSubmit={handleCreateMemory} className="cr-panel" style={{ backgroundColor: 'var(--bg-surface-elevated)', border: '1px solid var(--status-cyan-border)' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600, color: 'var(--status-cyan)', marginBottom: '10px' }}>
            RECORD NEW COGNITIVE MEMORY FACT / REJECTED HYPOTHESIS
          </div>

          <div className="grid-2" style={{ gap: '12px', marginBottom: '10px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: '4px' }}>
                RECORD TYPE
              </label>
              <select 
                value={newType} 
                onChange={(e) => setNewType(e.target.value as MemoryRecordType)}
              >
                <option value="VERIFIED_FACT">VERIFIED_FACT (Empirically Proven)</option>
                <option value="INFERRED_FACT">INFERRED_FACT (Hypothesized)</option>
                <option value="REJECTED_APPROACH">REJECTED_APPROACH (Failed Attempt)</option>
                <option value="DIAGNOSIS">DIAGNOSIS (Root Cause Finding)</option>
                <option value="RECOVERY_CONTEXT">RECOVERY_CONTEXT</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: '4px' }}>
                MISSION SCOPE
              </label>
              <select 
                value={newMissionId} 
                onChange={(e) => setNewMissionId(e.target.value)}
              >
                {missions.map(m => (
                  <option key={m.id} value={m.id}>{m.title || m.name} ({m.id})</option>
                ))}
                <option value="global">Global Shared Knowledge</option>
              </select>
            </div>
          </div>

          <div style={{ marginBottom: '12px' }}>
            <label style={{ display: 'block', fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: '4px' }}>
              MEMORY CONTENT / INSIGHT
            </label>
            <textarea 
              rows={3} 
              value={newContent} 
              onChange={(e) => setNewContent(e.target.value)}
              placeholder="E.g., Verified that csv_parser requires delimiter='\\t' when handling tab-separated imports without header..."
              required
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <button type="button" className="btn" onClick={() => setIsAdding(false)}>
              CANCEL
            </button>
            <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'RECORDING...' : 'COMMIT FACT TO MEMORY'}
            </button>
          </div>
        </form>
      )}

      {/* Memory Records List */}
      <div className="cr-panel">
        {filteredRecords.length === 0 ? (
          <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            NO MEMORY RECORDS FOUND MATCHING QUERY
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {filteredRecords.map((rec) => {
              const isEmpirical = rec.status === 'VERIFIED' || rec.category === 'verified_fact';
              const factText = rec.fact || rec.content || '';
              const sourceText = rec.source || rec.provenance?.source || 'system_audit';
              const authorText = rec.created_by || rec.provenance?.author || 'supervisor';

              return (
                <div 
                  key={rec.id}
                  style={{
                    backgroundColor: 'var(--bg-core)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '4px',
                    padding: '14px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {getTypeBadge(rec)}
                      {isEmpirical && (
                        <span className="badge badge-emerald" style={{ fontSize: '9px' }}>
                          EMPIRICALLY VERIFIED
                        </span>
                      )}
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                        CONFIDENCE: {Math.round(rec.confidence * 100)}%
                      </span>
                    </div>

                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                      ID: {rec.id} &bull; {new Date(rec.created_at).toLocaleTimeString()}
                    </span>
                  </div>

                  {/* Fact Content */}
                  <div style={{ fontSize: '13px', color: 'var(--text-primary)', lineHeight: 1.5, fontFamily: 'var(--font-sans)' }}>
                    {factText}
                  </div>

                  {/* Provenance Box */}
                  <div style={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '2px',
                    padding: '8px 10px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: '11px',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-secondary)'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <strong style={{ color: 'var(--text-muted)' }}>PROVENANCE:</strong>
                        <span style={{ color: 'var(--text-primary)' }}>{sourceText}</span>
                      </span>

                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <User size={11} color="var(--text-muted)" />
                        <span style={{ color: 'var(--text-primary)' }}>{authorText}</span>
                      </span>
                    </div>

                    <span style={{ color: 'var(--text-muted)' }}>
                      SCOPE: {rec.mission_id || 'global'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
