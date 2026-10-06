import React, { useState, useEffect, useCallback } from 'react';
import { 
  ShieldAlert, 
  AlertTriangle, 
  Play, 
  Pause, 
  ExternalLink, 
  Bot
} from 'lucide-react';
import type { Mission, AgentRecord, ApprovalRequest, InterventionDetail } from '../types';
import { fetchMissions, fetchAgents, fetchApprovals, pauseMission, resumeMission } from '../api';
import { useWebSocket } from '../useWebSocket';

export const FloatingHud: React.FC = () => {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [intervention, setIntervention] = useState<InterventionDetail | null>(null);
  const [isActing, setIsActing] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [m, a, apprv] = await Promise.all([
        fetchMissions().catch(() => []),
        fetchAgents().catch(() => []),
        fetchApprovals().catch(() => [])
      ]);
      setMissions(Array.isArray(m) ? m : []);
      setAgents(Array.isArray(a) ? a : []);
      setApprovals(Array.isArray(apprv) ? apprv : []);
    } catch {
      // quiet fallback
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 4000);
    return () => clearInterval(interval);
  }, [loadData]);

  const { isConnected } = useWebSocket({
    onIntervention: (intv) => setIntervention(intv),
    onEvent: () => loadData()
  });

  const activeMission = missions.find(m => 
    ['RUNNING', 'INVESTIGATING', 'RECOVERING', 'VERIFYING', 'WAITING_APPROVAL'].includes(m.status)
  ) || missions[0];

  const workingAgent = agents.find(a => 
    a.status === 'RUNNING' || a.status === 'BUSY'
  ) || agents[0];

  const pendingApprovalsCount = approvals.filter(a => a.status === 'PENDING').length;

  const handleTogglePause = async () => {
    if (!activeMission) return;
    setIsActing(true);
    try {
      if (activeMission.status === 'PAUSED') {
        await resumeMission(activeMission.id);
      } else {
        await pauseMission(activeMission.id);
      }
      await loadData();
    } finally {
      setIsActing(false);
    }
  };

  const handleOpenFullRoom = () => {
    if (window.supervisorDesktop?.openControlRoom) {
      window.supervisorDesktop.openControlRoom();
    } else {
      window.location.hash = '';
      window.location.reload();
    }
  };

  return (
    <div style={{
      width: '100%',
      height: '100vh',
      backgroundColor: '#090b0f',
      color: '#f1f4f8',
      display: 'flex',
      flexDirection: 'column',
      padding: '14px',
      boxSizing: 'border-box',
      fontFamily: 'var(--font-sans)',
      userSelect: 'none',
      border: '1px solid #1f2737',
      borderRadius: '8px'
    }}>
      {/* Top Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className={`status-dot ${isConnected ? (activeMission?.status === 'RUNNING' ? 'running' : 'active') : 'offline'}`} />
          <span style={{ fontSize: '12px', fontWeight: 600, color: '#f1f4f8', letterSpacing: '-0.01em' }}>
            Supervisor
          </span>
          <span style={{ fontSize: '11px', color: '#64748b' }}>
            {activeMission ? activeMission.status.toLowerCase() : 'idle'}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <button
            onClick={handleOpenFullRoom}
            className="btn btn-ghost btn-sm"
            style={{ padding: '3px 6px', fontSize: '11px' }}
            title="Open Control Room"
          >
            <ExternalLink size={12} />
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto' }}>
        {/* Intervention State Alert if active */}
        {intervention && (
          <div style={{
            padding: '8px 10px',
            borderRadius: '6px',
            backgroundColor: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.3)',
            color: '#f59e0b',
            fontSize: '11px',
            display: 'flex',
            flexDirection: 'column',
            gap: '2px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
              <AlertTriangle size={12} />
              <span>Supervisor Intervened: {intervention.anomaly}</span>
            </div>
            <div style={{ color: '#94a3b8', fontSize: '10px' }}>
              Action: {intervention.action}
            </div>
          </div>
        )}

        {/* Pending Approval Gate Alert if any */}
        {pendingApprovalsCount > 0 && (
          <div style={{
            padding: '8px 10px',
            borderRadius: '6px',
            backgroundColor: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#ef4444',
            fontSize: '11px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ShieldAlert size={13} />
              <span>{pendingApprovalsCount} Approval Required</span>
            </div>
            <button
              onClick={handleOpenFullRoom}
              className="btn btn-sm"
              style={{ backgroundColor: '#ef4444', color: '#fff', fontSize: '10px', padding: '2px 6px' }}
            >
              Review
            </button>
          </div>
        )}

        {/* Mission Status */}
        {activeMission ? (
          <div style={{
            backgroundColor: '#0f131a',
            border: '1px solid #1f2737',
            borderRadius: '6px',
            padding: '10px'
          }}>
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#f1f4f8', lineHeight: 1.3 }}>
              {activeMission.title}
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Bot size={12} color="var(--primary)" />
              <span>{workingAgent ? `${workingAgent.agent_id} (${workingAgent.status.toLowerCase()})` : 'Waiting for agent'}</span>
            </div>
          </div>
        ) : (
          <div style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#64748b',
            fontSize: '12px',
            textAlign: 'center',
            padding: '12px'
          }}>
            No active missions. Supervisor is standing by.
          </div>
        )}
      </div>

      {/* Bottom Footer Action */}
      {activeMission && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '8px', borderTop: '1px solid #171d29' }}>
          <span style={{ fontSize: '11px', color: '#64748b', fontFamily: 'var(--font-mono)' }}>
            {activeMission.id.slice(0, 10)}...
          </span>

          <button
            onClick={handleTogglePause}
            disabled={isActing}
            className="btn btn-secondary btn-sm"
            style={{ fontSize: '11px', padding: '3px 8px' }}
          >
            {activeMission.status === 'PAUSED' ? <Play size={11} /> : <Pause size={11} />}
            <span>{activeMission.status === 'PAUSED' ? 'Resume' : 'Pause'}</span>
          </button>
        </div>
      )}
    </div>
  );
};
