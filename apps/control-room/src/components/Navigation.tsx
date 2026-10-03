import React from 'react';
import { 
  Activity, 
  Terminal, 
  Users, 
  Cpu, 
  Database, 
  ShieldAlert, 
  Radio, 
  Play, 
  RefreshCw 
} from 'lucide-react';
import type { TabType } from '../types';

interface NavigationProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  wsConnected: boolean;
  wsLatency: number | null;
  pendingApprovalsCount: number;
  onSeedDemo: () => void;
  isSeeding: boolean;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  setActiveTab,
  wsConnected,
  wsLatency,
  pendingApprovalsCount,
  onSeedDemo,
  isSeeding,
  onRefresh,
  isRefreshing
}) => {
  const tabs = [
    { id: 'control_room', label: '1. Control Room', icon: Activity },
    { id: 'mission_detail', label: '2. Mission Detail', icon: Terminal },
    { id: 'agent_detail', label: '3. Agent Detail', icon: Users },
    { id: 'supervisor_events', label: '4. Supervisor Events', icon: Cpu },
    { id: 'project_memory', label: '5. Project Memory', icon: Database },
    { 
      id: 'approval_queue', 
      label: '6. Approval Queue', 
      icon: ShieldAlert, 
      count: pendingApprovalsCount 
    },
  ] as const;

  return (
    <header style={{
      backgroundColor: 'var(--bg-surface)',
      borderBottom: '1px solid var(--border-default)',
      position: 'sticky',
      top: 0,
      zIndex: 40,
    }}>
      {/* Top Banner / System Bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 24px',
        borderBottom: '1px solid var(--border-subtle)',
        fontSize: '11px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontFamily: 'var(--font-mono)',
            fontWeight: 700,
            fontSize: '13px',
            letterSpacing: '0.08em',
            color: 'var(--text-primary)'
          }}>
            <span style={{
              display: 'inline-block',
              width: '10px',
              height: '10px',
              backgroundColor: '#38bdf8',
              borderRadius: '2px',
            }} />
            AI WORK SUPERVISOR <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>// CONTROL PLANE</span>
          </div>
          <span className="badge badge-cyan" style={{ fontSize: '10px', padding: '1px 6px' }}>
            SUPERVISOR WATCHING
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* WebSocket Pulse */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
          }}>
            <Radio size={13} color={wsConnected ? 'var(--status-emerald)' : 'var(--status-amber)'} />
            <span style={{ color: wsConnected ? 'var(--status-emerald)' : 'var(--status-amber)' }}>
              {wsConnected ? 'WS LIVE' : 'WS RECONNECTING'}
            </span>
            {wsLatency !== null && wsConnected && (
              <span style={{ color: 'var(--text-muted)' }}>({wsLatency}ms)</span>
            )}
          </div>

          {/* Quick Actions */}
          <button 
            className="btn" 
            onClick={onRefresh} 
            disabled={isRefreshing}
            title="Refresh All States"
          >
            <RefreshCw size={12} className={isRefreshing ? 'spin' : ''} />
            <span>SYNC</span>
          </button>

          <button 
            className="btn btn-primary" 
            onClick={onSeedDemo} 
            disabled={isSeeding}
            title="Load Seed Demo Mission (CSV Import Refactor)"
          >
            <Play size={12} />
            <span>{isSeeding ? 'SEEDING...' : 'SEED DEMO MISSION'}</span>
          </button>
        </div>
      </div>

      {/* Tabs Navigation Bar */}
      <nav style={{
        display: 'flex',
        alignItems: 'stretch',
        padding: '0 24px',
        overflowX: 'auto',
      }}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          const hasBadge = 'count' in tab && tab.count !== undefined && tab.count > 0;

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as TabType)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '11px 16px',
                background: 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid var(--status-cyan)' : '2px solid transparent',
                color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                fontWeight: isActive ? 600 : 500,
                fontSize: '12px',
                fontFamily: 'var(--font-mono)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                whiteSpace: 'nowrap',
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.color = 'var(--text-primary)';
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.color = 'var(--text-secondary)';
              }}
            >
              <Icon size={14} color={isActive ? 'var(--status-cyan)' : 'var(--text-muted)'} />
              <span>{tab.label}</span>
              {hasBadge && (
                <span className="badge badge-crimson" style={{ fontSize: '10px', padding: '0 5px' }}>
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </header>
  );
};
