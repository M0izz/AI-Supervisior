import React, { useState, useEffect, useMemo } from 'react';
import { 
  Network, 
  RefreshCw, 
  Search, 
  Layers, 
  ShieldCheck, 
  AlertTriangle, 
  CheckCircle2, 
  Terminal, 
  GitBranch, 
  Cpu, 
  X, 
  Copy, 
  Check, 
  ZoomIn, 
  ZoomOut, 
  RotateCcw, 
  Sparkles
} from 'lucide-react';
import type { GraphNode, GraphEdge, MissionGraphData, GraphHealth } from '../types';
import { getMissionGraph, getGraphHealth } from '../api';

interface FalkorGraphInspectorProps {
  missionId: string;
  hideHeader?: boolean;
  onSeedDemo?: () => void;
  onSelectMission?: (missionId: string) => void;
  availableMissions?: Array<{ id: string; title: string; status?: string }>;
  missionLinks?: Record<string, number>;
}

const STAGE_ORDER = [
  { id: 'Mission', label: '1. Mission', icon: Sparkles, color: '#3478F6' },
  { id: 'Task', label: '2. Tasks', icon: Layers, color: '#06B6D4' },
  { id: 'Execution', label: '3. Exec', icon: Terminal, color: '#80B5FF' },
  { id: 'ExecutionEvent', label: '4. Failures', icon: AlertTriangle, color: '#EF4444' },
  { id: 'Decision', label: '5. Decisions', icon: Cpu, color: '#8B5CF6' },
  { id: 'Handoff', label: '6. Handoffs', icon: GitBranch, color: '#F59E0B' },
  { id: 'Verification', label: '7. Verify', icon: ShieldCheck, color: '#10B981' },
  { id: 'Evidence', label: '8. Evidence', icon: CheckCircle2, color: '#14B8A6' }
];

export const FalkorGraphInspector: React.FC<FalkorGraphInspectorProps> = ({ 
  missionId, 
  hideHeader = false, 
  onSeedDemo,
  onSelectMission,
  availableMissions = [],
  missionLinks = {}
}) => {
  const [graphData, setGraphData] = useState<MissionGraphData | null>(null);
  const [health, setHealth] = useState<GraphHealth | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [viewMode, setViewMode] = useState<'lineage' | 'topology'>('lineage');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [panOffset, setPanOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const fetchGraph = async () => {
    setLoading(true);
    setError(null);
    try {
      const [gData, hData] = await Promise.all([
        getMissionGraph(missionId),
        getGraphHealth().catch(() => null)
      ]);
      setGraphData(gData);
      setHealth(hData);
      if (gData.nodes.length > 0 && !selectedNode) {
        // default select the mission or first decision
        const initial = gData.nodes.find(n => n.label === 'Decision') || gData.nodes.find(n => n.label === 'Mission') || gData.nodes[0];
        setSelectedNode(initial);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch graph memory from FalkorDB');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (missionId) {
      fetchGraph();
    }
  }, [missionId]);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Group nodes by stage
  const nodesByStage = useMemo(() => {
    if (!graphData) return {};
    const groups: Record<string, GraphNode[]> = {};
    for (const n of graphData.nodes) {
      let stageKey = n.label;
      if (n.label === 'ExecutionEvent' || n.label === 'Failure') {
        stageKey = 'ExecutionEvent';
      }
      if (!groups[stageKey]) groups[stageKey] = [];
      groups[stageKey].push(n);
    }
    return groups;
  }, [graphData]);

  // Filtered nodes
  const filteredNodes = useMemo(() => {
    if (!graphData) return [];
    return graphData.nodes.filter(n => {
      const matchesStage = !selectedStage || n.label === selectedStage || (selectedStage === 'ExecutionEvent' && n.label === 'Failure');
      const q = searchQuery.toLowerCase().trim();
      if (!q) return matchesStage;
      const matchesSearch = 
        n.id.toLowerCase().includes(q) ||
        n.label.toLowerCase().includes(q) ||
        JSON.stringify(n.properties || {}).toLowerCase().includes(q);
      return matchesStage && matchesSearch;
    });
  }, [graphData, selectedStage, searchQuery]);

  // Edges linked to selected node
  const linkedEdges = useMemo(() => {
    if (!graphData || !selectedNode) return { incoming: [], outgoing: [] };
    const incoming = graphData.edges.filter(e => e.target === selectedNode.id);
    const outgoing = graphData.edges.filter(e => e.source === selectedNode.id);
    return { incoming, outgoing };
  }, [graphData, selectedNode]);

  // Associated Evidence for selected node (if verification or task)
  const linkedEvidence = useMemo(() => {
    if (!graphData || !selectedNode) return [];
    if (selectedNode.label === 'Evidence') return [selectedNode];
    if (selectedNode.label === 'Verification') {
      const evidenceIds = graphData.edges
        .filter(e => e.source === selectedNode.id && e.type === 'SUPPORTED_BY')
        .map(e => e.target);
      return graphData.nodes.filter(n => evidenceIds.includes(n.id));
    }
    if (selectedNode.label === 'Task') {
      const verifIds = graphData.edges
        .filter(e => e.target === selectedNode.id && e.type === 'EVALUATES')
        .map(e => e.source);
      const evIds = graphData.edges
        .filter(e => verifIds.includes(e.source) && e.type === 'SUPPORTED_BY')
        .map(e => e.target);
      return graphData.nodes.filter(n => evIds.includes(n.id));
    }
    return [];
  }, [graphData, selectedNode]);

  // Causal failure event for selected execution or decision
  const causalFailure = useMemo(() => {
    if (!graphData || !selectedNode) return null;
    if (selectedNode.label === 'Failure') return selectedNode;
    if (selectedNode.label === 'Execution') {
      const failEdge = graphData.edges.find(e => e.source === selectedNode.id && (e.type === 'FAILS_WITH' || e.type === 'FAILED_WITH'));
      if (failEdge) {
        return graphData.nodes.find(n => n.id === failEdge.target) || null;
      }
    }
    if (selectedNode.label === 'Decision') {
      const respEdge = graphData.edges.find(e => e.source === selectedNode.id && e.type === 'RESPONDS_TO');
      if (respEdge) {
        return graphData.nodes.find(n => n.id === respEdge.target) || null;
      }
    }
    return null;
  }, [graphData, selectedNode]);

  // Node position calculation for SVG Topology
  const topologyLayout = useMemo(() => {
    if (!graphData) return { nodes: [], edges: [] };
    const columnMap: Record<string, number> = {
      Mission: 0,
      Requirement: 0.5,
      Task: 1,
      Execution: 2,
      ExecutionEvent: 2.8,
      Failure: 2.8,
      Decision: 3.5,
      Handoff: 4.2,
      Verification: 5,
      Evidence: 5.8,
      Artifact: 5.8,
      Agent: 3.5
    };

    const colWidth = 240;
    const rowHeight = 110;
    const colCounters: Record<number, number> = {};

    const positionedNodes = graphData.nodes.map(node => {
      const col = columnMap[node.label] ?? 3;
      const count = colCounters[col] || 0;
      colCounters[col] = count + 1;

      return {
        ...node,
        x: 80 + col * colWidth,
        y: 80 + count * rowHeight
      };
    });

    const nodePosMap = new Map(positionedNodes.map(n => [n.id, n]));

    const positionedEdges = graphData.edges
      .map(e => {
        const src = nodePosMap.get(e.source);
        const tgt = nodePosMap.get(e.target);
        if (!src || !tgt) return null;
        return {
          ...e,
          x1: src.x + 95,
          y1: src.y + 25,
          x2: tgt.x - 95,
          y2: tgt.y + 25
        };
      })
      .filter(Boolean) as Array<GraphEdge & { x1: number; y1: number; x2: number; y2: number }>;

    return { nodes: positionedNodes, edges: positionedEdges };
  }, [graphData]);

  const getNodeColor = (label: string, props?: Record<string, any>) => {
    if (label === 'Failure') return '#EF4444';
    if (label === 'ExecutionEvent') {
      const isErr = props?.event_type?.includes('FAIL') || props?.severity === 'ERROR';
      return isErr ? '#EF4444' : '#60A5FA';
    }
    if (label === 'Execution') {
      return props?.status === 'FAILED' ? '#F59E0B' : props?.status === 'COMPLETED' ? '#10B981' : '#3478F6';
    }
    const found = STAGE_ORDER.find(s => s.id === label);
    return found ? found.color : '#8B5CF6';
  };

  const getNodeBadgeClass = (label: string, props?: Record<string, any>) => {
    if (label === 'Failure') return 'badge-danger';
    if (label === 'ExecutionEvent' && (props?.event_type?.includes('FAIL') || props?.severity === 'ERROR')) {
      return 'badge-danger';
    }
    if (label === 'Verification') {
      return props?.decision === 'ACCEPT' ? 'badge-green' : 'badge-danger';
    }
    if (label === 'Decision') return 'badge-purple';
    if (label === 'Task') return 'badge-blue';
    if (label === 'Evidence') return props?.passed ? 'badge-green' : 'badge-danger';
    return 'badge-neutral';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', position: 'relative' }}>
      {/* Top Banner: FalkorDB Authoritative Memory Status & Meta (Hidden when embedded in dedicated workspace) */}
      {!hideHeader && (
        <div 
          className="surface-card" 
          style={{ 
            padding: '16px 20px', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between', 
            gap: '16px', 
            flexWrap: 'wrap',
            borderLeft: '4px solid var(--primary)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div 
              style={{ 
                width: '36px', 
                height: '36px', 
                borderRadius: 'var(--radius-md)', 
                backgroundColor: 'var(--primary-subtle)', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                border: '1px solid var(--primary-border)'
              }}
            >
              <Network size={20} color="var(--primary)" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>
                  FalkorDB Authoritative Graph Memory
                </span>
                <span className="badge badge-blue" style={{ fontSize: '10px', textTransform: 'uppercase' }}>
                  Track 02: Memory & Coordination
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                <span>Graph: <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{health?.graph_name || 'ai_supervisor_memory'}</strong></span>
                <span>•</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span className={`status-dot ${health?.connected || health?.status === 'HEALTHY' ? 'active' : 'idle'}`} />
                  {health?.status === 'HEALTHY' ? 'Live & Connected' : 'Checking Connection'}
                </span>
                <span>•</span>
                <span>Latency: <strong style={{ color: 'var(--text-primary)' }}>{health?.latency_ms ? `${health.latency_ms.toFixed(1)}ms` : '< 1ms'}</strong></span>
                <span>•</span>
                <span>Nodes: <strong style={{ color: 'var(--primary-ice)' }}>{graphData?.nodes_count ?? 0}</strong></span>
                <span>•</span>
                <span>Edges: <strong style={{ color: 'var(--primary-ice)' }}>{graphData?.edges_count ?? 0}</strong></span>
              </div>
            </div>
          </div>

          {/* View Toggle & Actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ display: 'flex', backgroundColor: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)', padding: '2px', border: '1px solid var(--border-subtle)' }}>
              <button
                type="button"
                className={`btn btn-sm ${viewMode === 'lineage' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ padding: '4px 10px', fontSize: '12px' }}
                onClick={() => setViewMode('lineage')}
              >
                Lineage Flow
              </button>
              <button
                type="button"
                className={`btn btn-sm ${viewMode === 'topology' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ padding: '4px 10px', fontSize: '12px' }}
                onClick={() => setViewMode('topology')}
              >
                Graph Topology
              </button>
            </div>

            <button
              type="button"
              className="btn btn-outline btn-sm"
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              onClick={fetchGraph}
              disabled={loading}
            >
              <RefreshCw size={13} className={loading ? 'spin' : ''} />
              <span>Refresh Graph</span>
            </button>
          </div>
        </div>
      )}

      {/* 8-Stage Supervisory Lineage Stepper Strip */}
      <div 
        className="surface-card" 
        style={{ 
          padding: '8px 12px', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between',
          gap: '10px', 
          flexWrap: 'wrap',
          backgroundColor: 'var(--surface-elevated)',
          borderRadius: 'var(--radius-md)'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginRight: '4px', whiteSpace: 'nowrap' }}>
            Stages:
          </span>
          {STAGE_ORDER.map((stage) => {
            const Icon = stage.icon;
            const count = nodesByStage[stage.id]?.length || 0;
            const isSelected = selectedStage === stage.id;
            return (
              <button
                key={stage.id}
                type="button"
                onClick={() => setSelectedStage(isSelected ? null : stage.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '4px 8px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: isSelected ? 'var(--primary-subtle)' : count > 0 ? 'rgba(255, 255, 255, 0.03)' : 'transparent',
                  border: `1px solid ${isSelected ? 'var(--primary-border)' : count > 0 ? 'var(--border-subtle)' : 'transparent'}`,
                  color: isSelected ? 'var(--text-primary)' : count > 0 ? 'var(--text-secondary)' : 'var(--text-dim)',
                  cursor: 'pointer',
                  fontSize: '11px',
                  fontWeight: isSelected ? 600 : 500,
                  whiteSpace: 'nowrap',
                  transition: 'all 0.15s ease'
                }}
              >
                <Icon size={12} color={count > 0 ? stage.color : 'var(--text-dim)'} />
                <span>{stage.label}</span>
                <span 
                  style={{ 
                    fontSize: '10px', 
                    padding: '0 4px', 
                    borderRadius: '10px',
                    fontWeight: 600,
                    backgroundColor: count > 0 ? `${stage.color}20` : 'transparent',
                    color: count > 0 ? stage.color : 'var(--text-dim)'
                  }}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* View Mode Switcher + Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <div style={{ display: 'flex', backgroundColor: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)', padding: '2px', border: '1px solid var(--border-subtle)' }}>
            <button
              type="button"
              className={`btn btn-sm ${viewMode === 'lineage' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ padding: '3px 8px', fontSize: '11.5px' }}
              onClick={() => setViewMode('lineage')}
            >
              Lineage Flow
            </button>
            <button
              type="button"
              className={`btn btn-sm ${viewMode === 'topology' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ padding: '3px 8px', fontSize: '11.5px' }}
              onClick={() => setViewMode('topology')}
            >
              Graph Topology
            </button>
          </div>

          <button
            type="button"
            className="btn btn-outline btn-sm"
            style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '3px 8px', fontSize: '11.5px' }}
            onClick={fetchGraph}
            disabled={loading}
            title="Reload graph context for this mission"
          >
            <RefreshCw size={12} className={loading ? 'spin' : ''} />
            <span>Reload</span>
          </button>
        </div>
      </div>

      {/* Main Graph Content Area: Lineage Flow vs SVG Topology */}
      {error ? (
        <div className="surface-card" style={{ padding: '36px', textAlign: 'center', border: '1px solid var(--danger-border)' }}>
          <AlertTriangle size={36} color="var(--danger)" style={{ margin: '0 auto 12px auto' }} />
          <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>FalkorDB Connection Error</h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '480px', margin: '8px auto 16px auto' }}>
            {error}
          </p>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Verify that FalkorDB is running via <code style={{ color: 'var(--primary-ice)' }}>docker compose up -d</code>.
          </p>
        </div>
      ) : loading && !graphData ? (
        <div className="surface-card" style={{ padding: '60px', textAlign: 'center', color: 'var(--text-muted)' }}>
          <RefreshCw size={24} className="spin" style={{ margin: '0 auto 12px auto' }} />
          <div>Retrieving mission property graph from FalkorDB...</div>
        </div>
      ) : graphData && graphData.nodes.length === 0 ? (
        <div className="surface-card" style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-muted)', backgroundColor: 'var(--card-bg)', border: '1px solid var(--border)' }}>
          <div style={{
            width: '44px',
            height: '44px',
            borderRadius: '50%',
            backgroundColor: 'rgba(56, 189, 248, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 14px auto',
            color: '#38bdf8'
          }}>
            <Network size={22} />
          </div>
          <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
            No Active Graph Nodes for This Mission Yet
          </div>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '460px', margin: '0 auto 18px auto', lineHeight: '1.5' }}>
            This mission is currently in planning or awaiting approval. As soon as the mission runs, the supervisor continuously writes task DAGs, execution attempts, failure events, recovery decisions, and verification evidence into FalkorDB.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', flexWrap: 'wrap' }}>
            {onSeedDemo && (
              <button onClick={onSeedDemo} className="btn btn-primary btn-sm" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                <Sparkles size={13} />
                <span>Populate Graph via Demo Scenario</span>
              </button>
            )}
          </div>

          {availableMissions && availableMissions.length > 0 && availableMissions.some(m => (missionLinks[m.id] || 0) > 0) && (
            <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '10px' }}>
                Or inspect an existing mission with live graph memory:
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', flexWrap: 'wrap' }}>
                {availableMissions
                  .filter(m => (missionLinks[m.id] || 0) > 0)
                  .slice(0, 4)
                  .map(m => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => onSelectMission && onSelectMission(m.id)}
                      className="btn btn-secondary btn-sm"
                      style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                    >
                      <Network size={12} color="#38bdf8" />
                      <span>{m.title}</span>
                      <span style={{ fontSize: '11px', color: '#10b981', fontWeight: 600 }}>
                        {missionLinks[m.id]} nodes
                      </span>
                    </button>
                  ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: selectedNode ? '1fr 380px' : '1fr', gap: '16px', alignItems: 'start' }}>
          
          {/* Left Column: Visual Inspector (Lineage or Topology) */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            
            {/* Search and Filters toolbar */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
              <div style={{ position: 'relative', flex: 1, maxWidth: '340px' }}>
                <Search size={14} color="var(--text-dim)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
                <input
                  type="text"
                  placeholder="Filter nodes by ID, label, reason..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '7px 10px 7px 32px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'var(--bg-deep)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)',
                    fontSize: '12.5px'
                  }}
                />
              </div>

              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Showing <strong style={{ color: 'var(--text-primary)' }}>{filteredNodes.length}</strong> of {graphData?.nodes_count} nodes
              </div>
            </div>

            {/* VIEW MODE A: Mission Lineage Flow (Cards per stage) */}
            {viewMode === 'lineage' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {STAGE_ORDER.map(stage => {
                  const stageNodes = (nodesByStage[stage.id] || []).filter(n => {
                    if (!searchQuery) return true;
                    const q = searchQuery.toLowerCase();
                    return n.id.toLowerCase().includes(q) || JSON.stringify(n.properties || {}).toLowerCase().includes(q);
                  });

                  if (selectedStage && selectedStage !== stage.id) return null;
                  if (stageNodes.length === 0 && selectedStage === stage.id) {
                    return (
                      <div key={stage.id} className="surface-card" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                        No {stage.label} nodes recorded in FalkorDB yet.
                      </div>
                    );
                  }
                  if (stageNodes.length === 0) return null;

                  const Icon = stage.icon;

                  return (
                    <div 
                      key={stage.id} 
                      className="surface-card" 
                      style={{ 
                        padding: '16px 20px', 
                        display: 'flex', 
                        flexDirection: 'column', 
                        gap: '12px',
                        borderLeft: `3px solid ${stage.color}`
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Icon size={15} color={stage.color} />
                          <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>
                            {stage.label}
                          </span>
                          <span className="badge badge-neutral" style={{ fontSize: '10.5px' }}>
                            {stageNodes.length}
                          </span>
                        </div>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          (:{stage.id})
                        </span>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '10px' }}>
                        {stageNodes.map(node => {
                          const isSelected = selectedNode?.id === node.id;
                          const title = node.properties?.title || node.properties?.goal || node.properties?.action || node.properties?.event_type || node.properties?.summary || node.id;
                          const subtitle = node.properties?.reason || node.properties?.error_signature || node.properties?.status || node.properties?.decision || '';

                          return (
                            <div
                              key={node.id}
                              onClick={() => setSelectedNode(node)}
                              style={{
                                padding: '12px 14px',
                                borderRadius: 'var(--radius-sm)',
                                backgroundColor: isSelected ? 'var(--surface-hover)' : 'var(--bg-deep)',
                                border: `1px solid ${isSelected ? 'var(--primary)' : 'var(--border-subtle)'}`,
                                cursor: 'pointer',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '6px',
                                transition: 'all 0.15s ease',
                                boxShadow: isSelected ? '0 0 12px rgba(52, 120, 246, 0.25)' : 'none'
                              }}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                                <span className={`badge ${getNodeBadgeClass(node.label, node.properties)}`} style={{ fontSize: '10px' }}>
                                  {node.label}
                                </span>
                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                                  {node.id.length > 18 ? `${node.id.slice(0, 18)}...` : node.id}
                                </span>
                              </div>

                              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {title}
                              </div>

                              {subtitle && (
                                <div style={{ fontSize: '11.5px', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  {subtitle}
                                </div>
                              )}

                              {/* Node quick metrics / badges */}
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', fontSize: '11px', color: 'var(--text-dim)' }}>
                                {node.properties?.status && (
                                  <span>status: <strong style={{ color: 'var(--text-secondary)' }}>{node.properties.status}</strong></span>
                                )}
                                {node.properties?.agent_id && (
                                  <span>agent: <strong style={{ color: 'var(--text-secondary)' }}>{node.properties.agent_id}</strong></span>
                                )}
                                {node.properties?.passed !== undefined && (
                                  <span style={{ color: node.properties.passed ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                                    {node.properties.passed ? '✓ PASSED' : '✗ FAILED'}
                                  </span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* VIEW MODE B: Interactive SVG Graph Topology */}
            {viewMode === 'topology' && (
              <div 
                className="surface-card" 
                style={{ 
                  height: '620px', 
                  position: 'relative', 
                  overflow: 'hidden',
                  backgroundColor: 'var(--bg-deep)',
                  border: '1px solid var(--border)'
                }}
              >
                {/* Canvas Zoom & Pan Controls */}
                <div style={{ position: 'absolute', top: '12px', right: '12px', zIndex: 10, display: 'flex', gap: '6px', backgroundColor: 'var(--surface-glass)', padding: '4px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <button 
                    type="button" 
                    className="btn btn-ghost btn-sm" 
                    style={{ padding: '4px 6px' }} 
                    onClick={() => setZoomLevel(z => Math.min(z + 0.15, 2.0))}
                    title="Zoom In"
                  >
                    <ZoomIn size={14} />
                  </button>
                  <button 
                    type="button" 
                    className="btn btn-ghost btn-sm" 
                    style={{ padding: '4px 6px' }} 
                    onClick={() => setZoomLevel(z => Math.max(z - 0.15, 0.4))}
                    title="Zoom Out"
                  >
                    <ZoomOut size={14} />
                  </button>
                  <button 
                    type="button" 
                    className="btn btn-ghost btn-sm" 
                    style={{ padding: '4px 6px' }} 
                    onClick={() => { setZoomLevel(1); setPanOffset({ x: 0, y: 0 }); }}
                    title="Reset View"
                  >
                    <RotateCcw size={14} />
                  </button>
                </div>

                {/* SVG Graph Canvas */}
                <svg
                  width="100%"
                  height="100%"
                  style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
                  onMouseDown={e => {
                    setIsDragging(true);
                    setDragStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
                  }}
                  onMouseMove={e => {
                    if (isDragging) {
                      setPanOffset({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
                    }
                  }}
                  onMouseUp={() => setIsDragging(false)}
                  onMouseLeave={() => setIsDragging(false)}
                >
                  <defs>
                    <marker
                      id="arrowhead"
                      markerWidth="10"
                      markerHeight="7"
                      refX="10"
                      refY="3.5"
                      orient="auto"
                    >
                      <polygon points="0 0, 10 3.5, 0 7" fill="var(--border-light)" />
                    </marker>
                    <marker
                      id="arrowhead-highlight"
                      markerWidth="10"
                      markerHeight="7"
                      refX="10"
                      refY="3.5"
                      orient="auto"
                    >
                      <polygon points="0 0, 10 3.5, 0 7" fill="var(--primary)" />
                    </marker>
                  </defs>

                  <g transform={`translate(${panOffset.x}, ${panOffset.y}) scale(${zoomLevel})`}>
                    {/* Render Directed Edges */}
                    {topologyLayout.edges.map((edge, idx) => {
                      const isHighlighted = selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id);
                      const midX = (edge.x1 + edge.x2) / 2;
                      const midY = (edge.y1 + edge.y2) / 2;

                      return (
                        <g key={idx}>
                          <line
                            x1={edge.x1}
                            y1={edge.y1}
                            x2={edge.x2}
                            y2={edge.y2}
                            stroke={isHighlighted ? 'var(--primary)' : 'rgba(76, 141, 255, 0.25)'}
                            strokeWidth={isHighlighted ? 2.5 : 1.2}
                            strokeDasharray={edge.type.includes('FAILS') ? '4,4' : 'none'}
                            markerEnd={isHighlighted ? 'url(#arrowhead-highlight)' : 'url(#arrowhead)'}
                          />
                          <text
                            x={midX}
                            y={midY - 4}
                            fill={isHighlighted ? 'var(--primary-ice)' : 'var(--text-dim)'}
                            fontSize="9"
                            fontFamily="var(--font-mono)"
                            textAnchor="middle"
                            style={{ pointerEvents: 'none' }}
                          >
                            {edge.type}
                          </text>
                        </g>
                      );
                    })}

                    {/* Render Graph Nodes */}
                    {topologyLayout.nodes.map(node => {
                      const isSelected = selectedNode?.id === node.id;
                      const color = getNodeColor(node.label, node.properties);
                      const label = node.properties?.title || node.properties?.action || node.properties?.event_type || node.properties?.summary || node.id;
                      const shortLabel = label.length > 22 ? `${label.slice(0, 20)}...` : label;

                      return (
                        <g
                          key={node.id}
                          transform={`translate(${node.x - 90}, ${node.y - 25})`}
                          onClick={() => setSelectedNode(node)}
                          style={{ cursor: 'pointer' }}
                        >
                          <rect
                            width="180"
                            height="50"
                            rx="8"
                            fill={isSelected ? 'var(--surface-hover)' : 'var(--surface-elevated)'}
                            stroke={isSelected ? 'var(--primary)' : 'var(--border)'}
                            strokeWidth={isSelected ? 2 : 1}
                            style={{
                              filter: isSelected ? 'drop-shadow(0 0 10px rgba(52, 120, 246, 0.4))' : 'none'
                            }}
                          />
                          {/* Color bar on left edge */}
                          <rect width="4" height="50" rx="2" fill={color} />

                          {/* Node label pill */}
                          <text x="12" y="16" fill={color} fontSize="9" fontWeight="700" fontFamily="var(--font-sans)">
                            {node.label.toUpperCase()}
                          </text>

                          {/* Node title */}
                          <text x="12" y="32" fill="var(--text-primary)" fontSize="11" fontWeight="600" fontFamily="var(--font-sans)">
                            {shortLabel}
                          </text>

                          {/* Node ID */}
                          <text x="12" y="44" fill="var(--text-dim)" fontSize="8.5" fontFamily="var(--font-mono)">
                            {node.id.slice(0, 20)}
                          </text>
                        </g>
                      );
                    })}
                  </g>
                </svg>
              </div>
            )}
          </div>

          {/* Right Column: Interactive Node Inspector & Linked Evidence Drawer */}
          {selectedNode && (
            <div 
              className="surface-card" 
              style={{ 
                padding: '20px', 
                display: 'flex', 
                flexDirection: 'column', 
                gap: '16px',
                position: 'sticky',
                top: '20px',
                maxHeight: 'calc(100vh - 120px)',
                overflowY: 'auto',
                boxShadow: 'var(--shadow-lg)',
                border: '1px solid var(--border-light)'
              }}
            >
              {/* Header */}
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className={`badge ${getNodeBadgeClass(selectedNode.label, selectedNode.properties)}`} style={{ fontSize: '11px' }}>
                      {selectedNode.label}
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>FalkorDB Node</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                      {selectedNode.id}
                    </span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      style={{ padding: '2px 4px' }}
                      onClick={() => handleCopy(selectedNode.id)}
                      title="Copy Node ID"
                    >
                      {copiedId === selectedNode.id ? <Check size={12} color="var(--success)" /> : <Copy size={12} />}
                    </button>
                  </div>
                </div>

                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ padding: '4px' }}
                  onClick={() => setSelectedNode(null)}
                  title="Close Inspector"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Causality Trace Highlight: Inbound & Outbound Connections */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '10px 12px', backgroundColor: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Graph Traversal Lineage
                </span>
                
                {/* Incoming Edges */}
                {linkedEdges.incoming.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>Incoming:</span>
                    {linkedEdges.incoming.map((e, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                        <span style={{ color: 'var(--primary-pale)' }}>({e.source.slice(0, 10)}...)</span>
                        <span style={{ color: 'var(--text-dim)' }}>-[:{e.type}]-&gt;</span>
                        <span style={{ color: 'var(--text-primary)' }}>(this)</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Outgoing Edges */}
                {linkedEdges.outgoing.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '4px' }}>
                    <span style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>Outgoing:</span>
                    {linkedEdges.outgoing.map((e, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
                        <span style={{ color: 'var(--text-primary)' }}>(this)</span>
                        <span style={{ color: 'var(--primary-ice)' }}>-[:{e.type}]-&gt;</span>
                        <span style={{ color: 'var(--primary-pale)' }}>({e.target.slice(0, 10)}...)</span>
                      </div>
                    ))}
                  </div>
                )}

                {linkedEdges.incoming.length === 0 && linkedEdges.outgoing.length === 0 && (
                  <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>Root mission node (no explicit incoming edges).</span>
                )}
              </div>

              {/* Causal Failure Event Link (if applicable) */}
              {causalFailure && (
                <div style={{ padding: '10px 12px', backgroundColor: 'var(--danger-subtle)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--danger-border)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11.5px', fontWeight: 600, color: 'var(--danger)' }}>
                    <AlertTriangle size={13} />
                    <span>Causal Failure Event</span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                    {causalFailure.properties?.error_signature || causalFailure.properties?.event_type || causalFailure.id}
                  </div>
                  {causalFailure.properties?.reason && (
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      {causalFailure.properties.reason}
                    </div>
                  )}
                </div>
              )}

              {/* Linked Empirical Evidence Viewer (if Verification or Task node) */}
              {linkedEvidence.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '11.5px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Linked Empirical Evidence ({linkedEvidence.length})
                    </span>
                    <span className="badge badge-green" style={{ fontSize: '10px' }}>
                      VERIFIED
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {linkedEvidence.map((ev, i) => {
                      const passed = ev.properties?.passed;
                      const empData = typeof ev.properties?.empirical_data === 'string' 
                        ? JSON.parse(ev.properties.empirical_data || '{}') 
                        : ev.properties?.empirical_data;

                      return (
                        <div 
                          key={ev.id || i} 
                          style={{ 
                            padding: '10px 12px', 
                            borderRadius: 'var(--radius-sm)', 
                            backgroundColor: 'var(--bg-deep)', 
                            border: `1px solid ${passed ? 'var(--success-border)' : 'var(--danger-border)'}`,
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '6px'
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                              {ev.properties?.description || ev.properties?.evidence_type || 'Evidence Item'}
                            </span>
                            <span className={`badge ${passed ? 'badge-green' : 'badge-danger'}`} style={{ fontSize: '9.5px' }}>
                              {passed ? 'PASS' : 'FAIL'}
                            </span>
                          </div>

                          <div style={{ fontSize: '10.5px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                            id: {ev.id}
                          </div>

                          {empData && (
                            <pre style={{
                              margin: '4px 0 0 0',
                              padding: '6px 8px',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(0,0,0,0.4)',
                              fontSize: '10.5px',
                              color: 'var(--text-secondary)',
                              fontFamily: 'var(--font-mono)',
                              overflowX: 'auto',
                              whiteSpace: 'pre-wrap'
                            }}>
                              {JSON.stringify(empData, null, 2)}
                            </pre>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Full Properties Table */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: '11.5px', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Node Properties
                </span>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', backgroundColor: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)', padding: '10px 12px', border: '1px solid var(--border-subtle)' }}>
                  {Object.entries(selectedNode.properties || {}).map(([key, val]) => {
                    const displayVal = typeof val === 'object' ? JSON.stringify(val) : String(val);
                    return (
                      <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: '2px', borderBottom: '1px solid rgba(255,255,255,0.04)', paddingBottom: '4px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          {key}
                        </span>
                        <span style={{ fontSize: '12px', color: 'var(--text-primary)', wordBreak: 'break-word', fontFamily: key.includes('id') || key.includes('hash') || key.includes('time') ? 'var(--font-mono)' : 'var(--font-sans)' }}>
                          {displayVal}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
