import React, { useState, useEffect } from 'react';
import { 
  Search, 
  Plus, 
  FlaskConical, 
  RefreshCw, 
  Layers,
  Radio,
  Network
} from 'lucide-react';
import type { GraphHealth } from '../types';
import { getGraphHealth } from '../api';

interface TopBarProps {
  onOpenCommandPalette: () => void;
  onOpenCreateMission: () => void;
  onSeedDemo: () => void;
  isSeeding: boolean;
  onRefresh: () => void;
  isRefreshing: boolean;
  onOpenHud?: () => void;
  onOpenGraphInspector?: () => void;
  wsConnected?: boolean;
  wsLatency?: number | null;
}

export const TopBar: React.FC<TopBarProps> = ({
  onOpenCommandPalette,
  onOpenCreateMission,
  onSeedDemo,
  isSeeding,
  onRefresh,
  isRefreshing,
  onOpenHud,
  onOpenGraphInspector,
  wsConnected = true,
  wsLatency = 12
}) => {
  const [graphHealth, setGraphHealth] = useState<GraphHealth | null>(null);

  useEffect(() => {
    let isMounted = true;
    const checkGraph = () => {
      getGraphHealth()
        .then(h => { if (isMounted) setGraphHealth(h); })
        .catch(() => { if (isMounted) setGraphHealth(null); });
    };
    checkGraph();
    const timer = setInterval(checkGraph, 10000);
    return () => { isMounted = false; clearInterval(timer); };
  }, []);
  return (
    <header className="app-topbar">
      <div className="topbar-left">
        {/* Command Search Trigger */}
        <button 
          className="search-trigger" 
          onClick={onOpenCommandPalette}
          title="Search missions, agents, or run commands (Ctrl+K / ⌘K)"
        >
          <Search size={14} />
          <span>Search or command...</span>
          <span className="kbd-shortcut">⌘K</span>
        </button>

        {/* Live Supervisory Vitals Pill */}
        <div 
          className="status-pill"
          style={{ 
            fontSize: '11.5px', 
            padding: '4px 10px',
            backgroundColor: 'rgba(56, 189, 248, 0.06)',
            borderColor: 'rgba(56, 189, 248, 0.2)'
          }}
          title="Supervisory Nervous System Event Pipeline & Real-Time Watchdogs"
        >
          <Radio size={12} color="var(--primary)" className={wsConnected ? 'spin' : ''} style={{ animationDuration: '4s' }} />
          <span style={{ color: 'var(--text-secondary)' }}>Supervisory Bus:</span>
          <span style={{ color: wsConnected ? 'var(--primary)' : 'var(--danger)', fontWeight: 600 }}>
            {wsConnected ? `Live (${wsLatency ?? 14}ms)` : 'Offline'}
          </span>
        </div>

        {/* Live FalkorDB Property Graph Memory Indicator */}
        <div
          className="status-pill"
          style={{
            fontSize: '11.5px',
            padding: '4px 10px',
            cursor: onOpenGraphInspector ? 'pointer' : 'default',
            backgroundColor: graphHealth?.connected ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
            borderColor: graphHealth?.connected ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)',
          }}
          onClick={onOpenGraphInspector}
          title={
            graphHealth?.connected
              ? `FalkorDB Authoritative Graph Memory: Connected to ${graphHealth.host}:${graphHealth.port} (${graphHealth.graph_name}). Storing ${graphHealth.nodes_count ?? 0} nodes & ${graphHealth.relationships_count ?? 0} relationships. Latency: ${Math.round(graphHealth.latency_ms)}ms. Click to inspect graph.`
              : `FalkorDB Graph Memory: Disconnected (${graphHealth?.error || 'Port 6379 unavailable'}). Graph-backed retrieval and lineage paused.`
          }
        >
          <Network size={12} color={graphHealth?.connected ? 'var(--success)' : 'var(--danger)'} />
          <span style={{ color: 'var(--text-secondary)' }}>FalkorDB:</span>
          <span style={{ color: graphHealth?.connected ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
            {graphHealth?.connected ? `Connected (${graphHealth.nodes_count ?? 0} nodes)` : 'Disconnected'}
          </span>
        </div>
      </div>

      <div className="topbar-right">
        {/* Refresh */}
        <button
          className="btn btn-ghost btn-sm"
          onClick={onRefresh}
          disabled={isRefreshing}
          title="Sync state with authoritative backend"
        >
          <RefreshCw size={13} className={isRefreshing ? 'spin' : ''} />
          <span>{isRefreshing ? 'Syncing...' : 'Sync'}</span>
        </button>

        {/* Demo Scenario Button */}
        <button
          className="btn btn-secondary btn-sm"
          onClick={onSeedDemo}
          disabled={isSeeding}
          title="Load deterministic demonstration scenario (Authentication test loop & handoff)"
        >
          <FlaskConical size={13} color="var(--warning)" />
          <span>{isSeeding ? 'Seeding...' : 'Demo Scenario'}</span>
        </button>

        {/* Start Mission Button */}
        <button
          className="btn btn-primary btn-sm"
          onClick={onOpenCreateMission}
          title="Start a new supervised autonomous mission"
        >
          <Plus size={14} />
          <span>Start a Mission</span>
        </button>

        {/* HUD Launcher */}
        {onOpenHud && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={onOpenHud}
            title="Open Floating HUD window"
          >
            <Layers size={13} />
            <span>HUD</span>
          </button>
        )}
      </div>
    </header>
  );
};
