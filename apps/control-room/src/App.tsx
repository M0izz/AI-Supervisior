import React, { useState, useEffect, useCallback } from 'react';
import type { TabType, Mission, AgentRecord, ApprovalRequest, Event, MemoryRecord, InterventionDetail } from './types';
import { 
  fetchMissions, 
  fetchAgents, 
  fetchApprovals, 
  fetchMemory, 
  fetchTelemetry, 
  seedDemoMission 
} from './api';
import { useWebSocket } from './useWebSocket';
import { Navigation } from './components/Navigation';
import { InterventionPanel } from './components/InterventionModal';
import { ControlRoom } from './pages/ControlRoom';
import { MissionDetail } from './pages/MissionDetail';
import { AgentDetail } from './pages/AgentDetail';
import { SupervisorEvents } from './pages/SupervisorEvents';
import { ProjectMemory } from './pages/ProjectMemory';
import { ApprovalQueue } from './pages/ApprovalQueue';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('control_room');
  const [missions, setMissions] = useState<Mission[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [memoryRecords, setMemoryRecords] = useState<MemoryRecord[]>([]);
  const [telemetry, setTelemetry] = useState<any>(null);
  
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const [activeIntervention, setActiveIntervention] = useState<InterventionDetail | null>(null);
  const [dismissedIntervention, setDismissedIntervention] = useState(false);

  // Load all initial state
  const loadData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [m, a, apprv, mem, tel] = await Promise.all([
        fetchMissions().catch(() => []),
        fetchAgents().catch(() => []),
        fetchApprovals().catch(() => []),
        fetchMemory().catch(() => []),
        fetchTelemetry().catch(() => null)
      ]);

      const safeMissions = Array.isArray(m) ? m : [];
      const safeAgents = Array.isArray(a) ? a : [];
      const safeApprovals = Array.isArray(apprv) ? apprv : [];
      const safeMemory = Array.isArray(mem) ? mem : [];

      setMissions(safeMissions);
      if (safeMissions.length > 0 && !selectedMissionId) {
        setSelectedMissionId(safeMissions[0].id);
      }

      setAgents(safeAgents);
      if (safeAgents.length > 0 && !selectedAgentId) {
        setSelectedAgentId(safeAgents[0].agent_id);
      }

      setApprovals(safeApprovals);
      setMemoryRecords(safeMemory);
      setTelemetry(tel);
    } catch (err) {
      console.error('Failed to sync control room data', err);
    } finally {
      setIsRefreshing(false);
    }
  }, [selectedMissionId, selectedAgentId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle incoming live WebSocket events
  const handleLiveEvent = useCallback((event: Event) => {
    // If the event indicates mission or agent or approval mutation, refresh state
    const eType = event.event_type || event.type || '';
    if (
      eType.includes('MISSION') || 
      eType.includes('TASK') || 
      eType.includes('AGENT') || 
      eType.includes('APPROVAL') ||
      eType.includes('RECOVERY')
    ) {
      loadData();
    }
  }, [loadData]);

  // Handle incoming interventions detected via WebSocket
  const handleIntervention = useCallback((intervention: InterventionDetail) => {
    setActiveIntervention(intervention);
    setDismissedIntervention(false);
  }, []);

  const { isConnected: wsConnected, latency: wsLatency, events } = useWebSocket({
    onEvent: handleLiveEvent,
    onIntervention: handleIntervention
  });

  // Seed Demo Mission Handler
  const handleSeedDemo = async () => {
    setIsSeeding(true);
    try {
      const res = await seedDemoMission();
      if (res && res.mission_id) {
        setSelectedMissionId(res.mission_id);
      }
      await loadData();

      // Show seed demo intervention scenario for illustration if available
      setActiveIntervention({
        anomaly: 'LOOP DETECTED',
        evidence: '3 consecutive identical failures on test_csv_parser.py (regex unescaped comma error)',
        action: 'DELEGATE → REVIEWER',
        target: 'reviewer_01',
        confidence: 0.94,
        reason: 'Worker repeatedly failed with identical stack trace. Escalating to Reviewer for causal root diagnosis.',
        timestamp: new Date().toISOString()
      });
      setDismissedIntervention(false);
    } catch (e) {
      console.error('Failed to seed demo mission', e);
    } finally {
      setIsSeeding(false);
    }
  };

  const pendingApprovalsCount = Array.isArray(approvals) ? approvals.filter(a => a.status === 'PENDING').length : 0;

  return (
    <div className="app-container">
      {/* Navigation & Status Header */}
      <Navigation 
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        wsConnected={wsConnected}
        wsLatency={wsLatency}
        pendingApprovalsCount={pendingApprovalsCount}
        onSeedDemo={handleSeedDemo}
        isSeeding={isSeeding}
        onRefresh={loadData}
        isRefreshing={isRefreshing}
      />

      {/* Main Control Room Canvas */}
      <main className="app-main">
        {/* Persistent Intervention Alert if Active */}
        <InterventionPanel 
          intervention={activeIntervention}
          isOpen={!dismissedIntervention}
          onDismiss={() => setDismissedIntervention(true)}
        />

        {/* Tab 1: Control Room Overview */}
        {activeTab === 'control_room' && (
          <ControlRoom 
            missions={missions}
            agents={agents}
            activeInterventions={activeIntervention ? [activeIntervention] : []}
            telemetry={telemetry}
            onSelectMission={(id) => {
              setSelectedMissionId(id);
              setActiveTab('mission_detail');
            }}
            onSelectAgent={(id) => {
              setSelectedAgentId(id);
              setActiveTab('agent_detail');
            }}
            onNavigateToTab={setActiveTab}
          />
        )}

        {/* Tab 2: Mission Detail */}
        {activeTab === 'mission_detail' && (
          <MissionDetail 
            missions={missions}
            selectedMissionId={selectedMissionId}
            onSelectMission={setSelectedMissionId}
            agents={agents}
            onRefresh={loadData}
          />
        )}

        {/* Tab 3: Agent Detail */}
        {activeTab === 'agent_detail' && (
          <AgentDetail 
            agents={agents}
            selectedAgentId={selectedAgentId}
            onSelectAgent={setSelectedAgentId}
            onRefresh={loadData}
          />
        )}

        {/* Tab 4: Supervisor Events */}
        {activeTab === 'supervisor_events' && (
          <SupervisorEvents 
            events={events}
            wsConnected={wsConnected}
          />
        )}

        {/* Tab 5: Project Memory */}
        {activeTab === 'project_memory' && (
          <ProjectMemory 
            memoryRecords={memoryRecords}
            missions={missions}
            onRefresh={loadData}
          />
        )}

        {/* Tab 6: Approval Queue */}
        {activeTab === 'approval_queue' && (
          <ApprovalQueue 
            approvals={approvals}
            onRefresh={loadData}
          />
        )}
      </main>
    </div>
  );
};

export default App;
