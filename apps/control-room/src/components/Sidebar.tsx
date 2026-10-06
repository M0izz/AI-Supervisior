import React from 'react';
import { 
  Compass, 
  Target, 
  Bot, 
  Database, 
  Activity, 
  ShieldCheck, 
  Settings, 
  FolderGit2, 
  Cloud,
  Sparkles
} from 'lucide-react';
import type { TabType, SyncStatus } from '../types';

interface SidebarProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  activeMissionsCount: number;
  activeAgentsCount: number;
  pendingApprovalsCount: number;
  wsConnected: boolean;
  wsLatency: number | null;
  syncStatus: SyncStatus | null;
  onOpenSync: () => void;
  currentProject?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  activeMissionsCount,
  activeAgentsCount,
  pendingApprovalsCount,
  wsConnected,
  wsLatency,
  syncStatus,
  onOpenSync,
  currentProject = 'AI-Supervisior'
}) => {
  const isOverview = activeTab === 'overview' || activeTab === 'control_room';
  const isMissions = activeTab === 'missions' || activeTab === 'mission_detail';
  const isAgents = activeTab === 'agents' || activeTab === 'agent_detail';
  const isMemory = activeTab === 'memory' || activeTab === 'project_memory';
  const isActivity = activeTab === 'activity' || activeTab === 'supervisor_events';
  const isApprovals = activeTab === 'approvals' || activeTab === 'approval_queue';
  const isSettings = activeTab === 'settings';
  const isLanding = activeTab === 'landing';

  return (
    <aside className="app-sidebar" aria-label="Application Navigation">
      {/* Brand Header */}
      <div className="sidebar-brand">
        <div className="brand-mark" title="AI Supervisor Control Plane">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M3 12h3m12 0h3M12 3v3m0 12v3" />
            <path d="m5.6 5.6 2.2 2.2m8.4 8.4 2.2 2.2m0-12.8-2.2 2.2m-8.4 8.4-2.2 2.2" />
          </svg>
        </div>
        <div>
          <div className="brand-title">AI Supervisor</div>
        </div>
        <span className="brand-tag">v1.0</span>
      </div>

      {/* Navigation Sections */}
      <nav className="sidebar-nav">
        <div className="nav-section-title">Workspace</div>

        <button
          className={`nav-item ${isOverview ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <Activity size={16} />
          <span>Overview</span>
        </button>

        <button
          className={`nav-item ${isMissions ? 'active' : ''}`}
          onClick={() => setActiveTab('missions')}
        >
          <Target size={16} />
          <span>Missions</span>
          {activeMissionsCount > 0 && (
            <span className="nav-badge">{activeMissionsCount}</span>
          )}
        </button>

        <button
          className={`nav-item ${isAgents ? 'active' : ''}`}
          onClick={() => setActiveTab('agents')}
        >
          <Bot size={16} />
          <span>Agents</span>
          {activeAgentsCount > 0 && (
            <span className="nav-badge">{activeAgentsCount}</span>
          )}
        </button>

        <button
          className={`nav-item ${isMemory ? 'active' : ''}`}
          onClick={() => setActiveTab('memory')}
        >
          <Database size={16} />
          <span>Memory</span>
        </button>

        <button
          className={`nav-item ${isActivity ? 'active' : ''}`}
          onClick={() => setActiveTab('activity')}
        >
          <Compass size={16} />
          <span>Activity</span>
        </button>

        <div className="nav-section-title" style={{ marginTop: '12px' }}>Governance</div>

        <button
          className={`nav-item ${isApprovals ? 'active' : ''}`}
          onClick={() => setActiveTab('approvals')}
        >
          <ShieldCheck size={16} />
          <span>Approvals</span>
          {pendingApprovalsCount > 0 && (
            <span className="nav-badge urgent">{pendingApprovalsCount}</span>
          )}
        </button>

        <button
          className={`nav-item ${isSettings ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          <Settings size={16} />
          <span>Settings</span>
        </button>

        <div className="nav-section-title" style={{ marginTop: '12px' }}>Product</div>

        <button
          className={`nav-item ${isLanding ? 'active' : ''}`}
          onClick={() => setActiveTab('landing')}
        >
          <Sparkles size={16} color="var(--primary)" />
          <span style={{ color: isLanding ? 'var(--text-primary)' : 'var(--primary)' }}>Product Tour</span>
        </button>
      </nav>

      {/* Bottom Footer Info */}
      <div className="sidebar-footer">
        {/* Project Context */}
        <div className="project-pill" title="Authoritative Local Workspace">
          <FolderGit2 size={13} color="var(--text-muted)" />
          <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {currentProject}
          </span>
        </div>

        {/* Sync & Connection Status */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 4px', fontSize: '11px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }} title={wsConnected ? `WebSocket active (${wsLatency ?? 1}ms)` : 'Disconnected'}>
            <span className={`status-dot ${wsConnected ? 'active' : 'offline'}`} />
            <span style={{ color: 'var(--text-muted)' }}>
              {wsConnected ? 'Connected' : 'Offline'}
            </span>
          </div>

          <button
            onClick={onOpenSync}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '4px', 
              color: 'var(--text-muted)',
              padding: '2px 4px',
              borderRadius: '4px'
            }}
            title="Cloud Sync & Multi-Device Settings"
          >
            <Cloud size={12} />
            <span>{syncStatus?.state === 'SYNCED' ? 'Synced' : 'Sync'}</span>
          </button>
        </div>
      </div>
    </aside>
  );
};
