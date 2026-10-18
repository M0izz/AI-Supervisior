import React, { useState, useEffect, useCallback } from 'react';
import type { 
  TabType, 
  Mission, 
  AgentRecord, 
  ApprovalRequest, 
  Event, 
  MemoryRecord, 
  InterventionDetail,
  AdapterInfo,
  SyncStatus
} from './types';
import { 
  fetchMissions, 
  fetchAgents, 
  fetchApprovals, 
  fetchMemory, 
  getAdapters,
  getSyncStatus,
  seedDemoMission,
  executeMission,
  getSupervisorEvents
} from './api';
import { useWebSocket } from './useWebSocket';

// Layout & Modals
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { CommandPalette } from './components/CommandPalette';
import { MissionComposer } from './components/MissionComposer';
import { SyncModal } from './components/SyncModal';

// Reconstructed Pages
import { Overview } from './pages/Overview';
import { Missions } from './pages/Missions';
import { Agents } from './pages/Agents';
import { Activity } from './pages/Activity';
import { ProjectMemory } from './pages/ProjectMemory';
import { Approvals } from './pages/Approvals';
import { Settings } from './pages/Settings';
import { LandingPage } from './pages/LandingPage';
import { FalkorDBWorkspace } from './pages/FalkorDBWorkspace';

const getInitialRoute = (): 'landing' | 'app' => {
  if (typeof window === 'undefined') return 'landing';
  const path = window.location.pathname.toLowerCase().replace(/\/+$/, '');
  const hash = window.location.hash.toLowerCase();
  const search = window.location.search.toLowerCase();
  
  // Explicit landing route or query param
  if (
    path.startsWith('/landing') ||
    hash.includes('landing') ||
    search.includes('view=landing')
  ) {
    return 'landing';
  }

  // Explicit control room routes
  const isControlRoomRoute =
    path.startsWith('/app') ||
    path.startsWith('/overview') ||
    path.startsWith('/missions') ||
    path.startsWith('/agents') ||
    path.startsWith('/falkordb') ||
    path.startsWith('/graph') ||
    path.startsWith('/memory') ||
    path.startsWith('/activity') ||
    path.startsWith('/approvals') ||
    path.startsWith('/settings') ||
    hash.includes('overview') ||
    hash.includes('missions') ||
    hash.includes('agents') ||
    hash.includes('falkordb') ||
    hash.includes('approvals');

  if (isControlRoomRoute) {
    return 'app';
  }

  // Root or unmapped paths default to the Landing Page
  return 'landing';
};

const getInitialTab = (): TabType => {
  if (typeof window === 'undefined') return 'overview';
  const path = window.location.pathname.toLowerCase();
  const hash = window.location.hash.toLowerCase();
  if (path.includes('falkordb') || hash.includes('falkordb') || path.includes('graph')) {
    return 'falkordb';
  }
  if (path.includes('missions') || hash.includes('missions')) return 'missions';
  if (path.includes('agents') || hash.includes('agents')) return 'agents';
  if (path.includes('memory') || hash.includes('memory')) return 'memory';
  if (path.includes('activity') || hash.includes('activity')) return 'activity';
  if (path.includes('approvals') || hash.includes('approvals')) return 'approvals';
  if (path.includes('settings') || hash.includes('settings')) return 'settings';
  return 'overview';
};

export const App: React.FC = () => {
  const [currentRoute, setCurrentRoute] = useState<'landing' | 'app'>(getInitialRoute);
  const [activeTab, setActiveTab] = useState<TabType>(getInitialTab);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [adapters, setAdapters] = useState<AdapterInfo[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [memoryRecords, setMemoryRecords] = useState<MemoryRecord[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [interventions, setInterventions] = useState<InterventionDetail[]>([]);

  // Route & Tab Navigation Handler (survives refresh and direct URL access)
  const handleTabChange = useCallback((tab: TabType) => {
    if (tab === 'landing') {
      setCurrentRoute('landing');
      setActiveTab('landing');
      try {
        if (window.location.pathname !== '/landing') {
          window.history.pushState(null, '', '/landing');
        }
      } catch {
        window.location.hash = '#landing';
      }
      return;
    }

    setActiveTab(tab);
    setCurrentRoute('app');
    const pathName = tab === 'falkordb' ? '/falkordb' : tab === 'overview' ? '/overview' : `/${tab}`;
    try {
      if (window.location.pathname !== pathName) {
        window.history.pushState(null, '', pathName);
      }
    } catch {
      window.location.hash = `#${tab}`;
    }
  }, []);

  // Route Synchronization on popstate / hashchange
  useEffect(() => {
    const handleRouteChange = () => {
      const route = getInitialRoute();
      setCurrentRoute(route);
      if (route === 'app') {
        setActiveTab(getInitialTab());
      } else {
        setActiveTab('landing');
      }
    };
    window.addEventListener('popstate', handleRouteChange);
    window.addEventListener('hashchange', handleRouteChange);
    return () => {
      window.removeEventListener('popstate', handleRouteChange);
      window.removeEventListener('hashchange', handleRouteChange);
    };
  }, []);

  const navigateToControlRoom = useCallback((tab: TabType = 'overview') => {
    handleTabChange(tab);
  }, [handleTabChange]);

  // Modals
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isCreateMissionOpen, setIsCreateMissionOpen] = useState(false);
  const [isSyncOpen, setIsSyncOpen] = useState(false);

  // Loading states
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);

  // Fallback safety timeout for initial loading
  useEffect(() => {
    const timer = setTimeout(() => setIsInitialLoading(false), 2500);
    return () => clearTimeout(timer);
  }, []);

  // Load authoritative backend data
  const loadData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [m, a, adapRes, apprv, mem, evts, sync] = await Promise.all([
        fetchMissions().catch(() => []),
        fetchAgents().catch(() => []),
        getAdapters().catch(() => ({ adapters: [], count: 0 })),
        fetchApprovals().catch(() => []),
        fetchMemory().catch(() => []),
        getSupervisorEvents({ limit: 40 }).catch(() => []),
        getSyncStatus().catch(() => null)
      ]);

      const safeMissions = Array.isArray(m) ? m : [];
      const safeAgents = Array.isArray(a) ? a : [];
      const safeApprovals = Array.isArray(apprv) ? apprv : [];
      const safeMemory = Array.isArray(mem) ? mem : [];
      const safeEvents = Array.isArray(evts) ? evts : [];

      setMissions(safeMissions);
      setAgents(safeAgents);
      setAdapters(adapRes?.adapters || []);
      setApprovals(safeApprovals);
      setMemoryRecords(safeMemory);
      setEvents(safeEvents);
      if (sync) setSyncStatus(sync);
    } catch (err) {
      console.error('Failed to sync authoritative backend data', err);
    } finally {
      setIsRefreshing(false);
      setIsInitialLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle incoming live WebSocket events
  const handleLiveEvent = useCallback((event: Event) => {
    setEvents(prev => [event, ...prev.slice(0, 99)]);
    const eType = event.event_type || event.type || '';
    if (
      eType.includes('MISSION') || 
      eType.includes('TASK') || 
      eType.includes('AGENT') || 
      eType.includes('APPROVAL') ||
      eType.includes('RECOVERY') ||
      eType.includes('VERIFICATION')
    ) {
      loadData();
    }
  }, [loadData]);

  const handleIntervention = useCallback((intv: InterventionDetail) => {
    setInterventions(prev => [intv, ...prev]);
  }, []);

  const { isConnected: wsConnected, latency: wsLatency } = useWebSocket({
    onEvent: handleLiveEvent,
    onIntervention: handleIntervention
  });

  // Global keyboard shortcuts (Ctrl+K / ⌘K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Real demo scenario trigger
  const handleSeedDemo = async () => {
    setIsSeeding(true);
    try {
      const res = await seedDemoMission();
      if (res?.mission_id) {
        setSelectedMissionId(res.mission_id);
        setActiveTab('missions');
        // Trigger real background mission execution via backend MissionRunner
        executeMission(res.mission_id).catch(e => {
          console.warn('Mission execution progress', e);
        });
      }
      await loadData();
    } catch (e) {
      console.error('Failed to run demo scenario', e);
    } finally {
      setIsSeeding(false);
    }
  };

  const pendingApprovalsCount = approvals.filter(a => a.status === 'PENDING').length;
  const activeMissionsCount = missions.filter(m => 
    ['RUNNING', 'INVESTIGATING', 'RECOVERING', 'VERIFYING', 'WAITING_APPROVAL'].includes(m.status)
  ).length;
  const activeAgentsCount = agents.filter(a => a.status === 'RUNNING' || a.status === 'BUSY').length;

  // If visitor is on the landing page route, render the signature Landing Page immediately
  if (currentRoute === 'landing') {
    return (
      <LandingPage
        onStartSupervising={() => navigateToControlRoom('overview')}
        onRunDemo={handleSeedDemo}
      />
    );
  }

  // Initial loading state for Control Room runtime connection
  if (isInitialLoading) {
    return (
      <div style={{
        height: '100vh',
        width: '100vw',
        backgroundColor: 'var(--bg)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '16px',
        color: 'var(--text-primary)'
      }}>
        <div style={{
          width: '36px',
          height: '36px',
          borderRadius: '8px',
          background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffffff',
          fontWeight: 700,
          fontSize: '18px'
        }}>
          ●
        </div>
        <div style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)' }}>
          Connecting to local AI Supervisor runtime...
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      {/* Restrained Modern Sidebar */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        activeMissionsCount={activeMissionsCount}
        activeAgentsCount={activeAgentsCount}
        pendingApprovalsCount={pendingApprovalsCount}
        wsConnected={wsConnected}
        wsLatency={wsLatency}
        syncStatus={syncStatus}
        onOpenSync={() => setIsSyncOpen(true)}
      />

      {/* Main Container */}
      <div className="app-content">
        {/* Topbar */}
        <TopBar
          onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
          onOpenCreateMission={() => setIsCreateMissionOpen(true)}
          onSeedDemo={handleSeedDemo}
          isSeeding={isSeeding}
          onRefresh={loadData}
          isRefreshing={isRefreshing}
          onOpenHud={window.supervisorDesktop?.showHud ? () => window.supervisorDesktop?.showHud() : undefined}
          onOpenLanding={() => handleTabChange('landing')}
          onOpenGraphInspector={() => handleTabChange('falkordb')}
          wsConnected={wsConnected}
          wsLatency={wsLatency}
        />

        {/* Scrollable View Area */}
        <main className="app-view">
          {/* Landing / Product Tour */}
          {activeTab === 'landing' && (
            <LandingPage
              onStartSupervising={() => handleTabChange('overview')}
              onRunDemo={handleSeedDemo}
            />
          )}

          {/* Overview */}
          {(activeTab === 'overview' || activeTab === 'control_room') && (
            <Overview
              missions={missions}
              agents={agents}
              adapters={adapters}
              approvals={approvals}
              interventions={interventions}
              events={events}
              memoryRecords={memoryRecords}
              onSelectMission={(id) => {
                setSelectedMissionId(id);
                handleTabChange('missions');
              }}
              onSelectAgent={(id) => {
                setSelectedAgentId(id);
                handleTabChange('agents');
              }}
              onNavigateToTab={handleTabChange}
              onOpenCreateMission={() => setIsCreateMissionOpen(true)}
              onRefresh={loadData}
            />
          )}

          {/* FalkorDB Graph Memory Workspace */}
          {(activeTab === 'falkordb' || activeTab === 'graph_memory' || activeTab === 'graph') && (
            <FalkorDBWorkspace
              missions={missions}
              selectedMissionId={selectedMissionId}
              onSelectMission={(id) => setSelectedMissionId(id)}
              onSeedDemo={handleSeedDemo}
              isSeeding={isSeeding}
            />
          )}

          {/* Missions (Integrated with Mission Detail) */}
          {(activeTab === 'missions' || activeTab === 'mission_detail') && (
            <Missions
              missions={missions}
              selectedMissionId={selectedMissionId}
              onSelectMission={setSelectedMissionId}
              onRefresh={loadData}
              onOpenCreateMission={() => setIsCreateMissionOpen(true)}
            />
          )}

          {/* Agents */}
          {(activeTab === 'agents' || activeTab === 'agent_detail') && (
            <Agents
              agents={agents}
              adapters={adapters}
              selectedAgentId={selectedAgentId}
              onSelectAgent={setSelectedAgentId}
              onRefresh={loadData}
            />
          )}

          {/* Activity */}
          {(activeTab === 'activity' || activeTab === 'supervisor_events') && (
            <Activity
              events={events}
              wsConnected={wsConnected}
              missions={missions}
              onSelectMission={(mid) => {
                setSelectedMissionId(mid);
                handleTabChange('missions');
              }}
              onRefresh={loadData}
            />
          )}

          {/* Project Memory */}
          {(activeTab === 'memory' || activeTab === 'project_memory') && (
            <ProjectMemory
              memoryRecords={memoryRecords}
              missions={missions}
              onRefresh={loadData}
            />
          )}

          {/* Approvals */}
          {(activeTab === 'approvals' || activeTab === 'approval_queue') && (
            <Approvals
              approvals={approvals}
              onRefresh={loadData}
            />
          )}

          {/* Settings */}
          {activeTab === 'settings' && (
            <Settings />
          )}
        </main>
      </div>

      {/* Global Modals */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onNavigate={handleTabChange}
        onOpenCreateMission={() => setIsCreateMissionOpen(true)}
        onSeedDemo={handleSeedDemo}
        onOpenSync={() => setIsSyncOpen(true)}
        missions={missions}
        agents={agents}
        onSelectMission={setSelectedMissionId}
        onSelectAgent={setSelectedAgentId}
      />

      <MissionComposer
        isOpen={isCreateMissionOpen}
        onClose={() => setIsCreateMissionOpen(false)}
        onMissionStarted={(newMission) => {
          setSelectedMissionId(newMission.id);
          setActiveTab('missions');
          loadData();
        }}
      />

      <SyncModal
        isOpen={isSyncOpen}
        onClose={() => setIsSyncOpen(false)}
        syncStatus={syncStatus}
        onRefreshSync={loadData}
      />
    </div>
  );
};

export default App;
