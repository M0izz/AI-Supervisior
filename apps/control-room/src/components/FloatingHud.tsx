import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  Pause,
  ExternalLink,
  Minus,
  Pin,
  RefreshCw,
  Cpu,
  Layers,
  Activity
} from 'lucide-react';
import type {
  Mission,
  AgentRecord,
  ApprovalRequest,
  Event,
  InterventionDetail,
  HudVisualState
} from '../types';
import {
  fetchMissions,
  fetchAgents,
  fetchApprovals,
  resolveApproval,
  pauseMission,
  resumeMission
} from '../api';
import { useWebSocket } from '../useWebSocket';

export const FloatingHud: React.FC = () => {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [activeIntervention, setActiveIntervention] = useState<InterventionDetail | null>(null);
  const [verificationState, setVerificationState] = useState<{
    status: 'idle' | 'verifying' | 'verified' | 'rejected';
    details?: string;
  }>({ status: 'idle' });
  const [handoffState, setHandoffState] = useState<{
    fromAgent?: string;
    toAgent?: string;
    reason?: string;
  } | null>(null);

  const [isAlwaysOnTop, setIsAlwaysOnTop] = useState(true);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());

  // Load authoritative backend state
  const refreshState = useCallback(async () => {
    try {
      const [mList, aList, apprvList] = await Promise.all([
        fetchMissions().catch(() => []),
        fetchAgents().catch(() => []),
        fetchApprovals().catch(() => [])
      ]);
      setMissions(Array.isArray(mList) ? mList : []);
      setAgents(Array.isArray(aList) ? aList : []);
      setApprovals(Array.isArray(apprvList) ? apprvList : []);
      setLastRefreshed(new Date());
    } catch {
      // Backend unavailable; state remains clean
    }
  }, []);

  useEffect(() => {
    refreshState();
    const interval = setInterval(refreshState, 10000);
    return () => clearInterval(interval);
  }, [refreshState]);

  // Handle incoming live events & trigger zero-nag notifications
  const handleLiveEvent = useCallback((event: Event) => {
    const eType = event.event_type || event.type || '';
    const payload = event.payload || {};

    // 1. Refresh state on structural mutations
    if (
      eType.includes('MISSION') ||
      eType.includes('TASK') ||
      eType.includes('AGENT') ||
      eType.includes('APPROVAL') ||
      eType.includes('HANDOFF') ||
      eType.includes('VERIFICATION')
    ) {
      refreshState();
    }

    // 2. Watchdog Interventions
    if (
      eType === 'INTERVENTION_TRIGGERED' ||
      eType === 'ANOMALY_DETECTED' ||
      eType.includes('LOOP_DETECTED') ||
      payload.intervention_type
    ) {
      const intervention: InterventionDetail = {
        anomaly: payload.anomaly || payload.intervention_type || 'WATCHDOG_INTERVENTION',
        description: payload.description || payload.reason || 'Watchdog rule triggered',
        evidence: payload.evidence || '',
        action: payload.action || 'INTERVENE',
        confidence: payload.confidence ?? 1.0,
        reason: payload.reason || 'Safety / Progress policy intervention',
        timestamp: event.timestamp || new Date().toISOString(),
        mission_id: event.mission_id || undefined,
        task_id: event.task_id || undefined
      };
      setActiveIntervention(intervention);

      // Notify desktop if supported
      window.supervisor?.notify({
        title: 'AI Supervisor Intervention',
        body: `${intervention.reason} (${intervention.action})`,
        severity: 'WARNING',
        type: 'CRITICAL_INTERVENTION',
        id: event.id
      });
    }

    // 3. Verification Events
    if (eType === 'VERIFICATION_STARTED') {
      setVerificationState({ status: 'verifying', details: 'Running independent test suite & diff audit...' });
    } else if (eType === 'VERIFICATION_ACCEPTED' || eType === 'TASK_VERIFIED') {
      const summary = payload.summary || 'Tests passed and diff validated';
      setVerificationState({ status: 'verified', details: summary });
      window.supervisor?.notify({
        title: 'Task Verified ✓',
        body: summary,
        severity: 'INFO',
        type: 'TASK_VERIFIED',
        id: event.id
      });
    } else if (eType === 'VERIFICATION_REJECTED') {
      const summary = payload.summary || payload.error || 'Verification rejected by ground truth';
      setVerificationState({ status: 'rejected', details: summary });
      window.supervisor?.notify({
        title: 'Verification Rejected ✕',
        body: summary,
        severity: 'ERROR',
        type: 'VERIFICATION_FAILED',
        id: event.id
      });
    }

    // 4. Handoff Events
    if (eType === 'HANDOFF_INITIATED' || eType === 'AGENT_HANDOFF') {
      setHandoffState({
        fromAgent: payload.source_agent || payload.from_agent || 'Original Agent',
        toAgent: payload.target_agent || payload.to_agent || 'Next Agent',
        reason: payload.reason || 'Automated handoff'
      });
    } else if (eType === 'HANDOFF_COMPLETED') {
      setHandoffState(null);
    }

    // 5. Approvals
    if (eType === 'APPROVAL_REQUIRED' || eType === 'APPROVAL_REQUESTED') {
      window.supervisor?.notify({
        title: 'Action Approval Required',
        body: payload.action_summary || 'Agent requires human authorization',
        severity: 'WARNING',
        type: 'APPROVAL_REQUIRED',
        id: event.id
      });
    }
  }, [refreshState]);

  const { isConnected, latency } = useWebSocket({
    onEvent: handleLiveEvent,
    reconnectInterval: 2500,
    maxReconnectInterval: 12000
  });

  // Identify primary active mission
  const activeMission = useMemo(() => {
    if (missions.length === 0) return null;
    const prioritized = missions.find(m =>
      ['RUNNING', 'RECOVERING', 'INVESTIGATING', 'VERIFYING', 'WAITING_APPROVAL'].includes(m.status)
    );
    return prioritized || missions[0];
  }, [missions]);

  // Identify assigned agent
  const currentAgent = useMemo(() => {
    if (!activeMission || agents.length === 0) return null;
    const assignedId = activeMission.assigned_agents?.[0] || activeMission.assigned_agent_ids?.[0];
    if (assignedId) {
      const found = agents.find(a => a.agent_id === assignedId);
      if (found) return found;
    }
    return agents.find(a => a.mission_id === activeMission.id) || agents[0];
  }, [activeMission, agents]);

  // Derive top pending approval
  const topApproval = useMemo(() => {
    return approvals.find(a => a.status === 'PENDING') || null;
  }, [approvals]);

  // Determine overall HUD visual state
  const hudState: HudVisualState = useMemo(() => {
    if (!isConnected) return 'DISCONNECTED';
    if (topApproval) return 'APPROVAL_REQUIRED';
    if (!activeMission) return 'IDLE';

    switch (activeMission.status) {
      case 'RUNNING':
        if (verificationState.status === 'verifying') return 'VERIFYING';
        return 'RUNNING';
      case 'RECOVERING':
      case 'INVESTIGATING':
        return 'RECOVERING';
      case 'PAUSED':
      case 'WAITING_APPROVAL':
        return 'WAITING';
      case 'BLOCKED':
        return 'BLOCKED';
      case 'COMPLETED':
        return 'COMPLETED';
      case 'FAILED':
      case 'CANCELLED':
        return 'FAILED';
      default:
        return 'IDLE';
    }
  }, [isConnected, topApproval, activeMission, verificationState]);

  // State Badge styling
  const stateBadgeInfo = useMemo(() => {
    switch (hudState) {
      case 'RUNNING':
        return { label: 'WORKING', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', border: '#059669' };
      case 'VERIFYING':
        return { label: 'VERIFYING', color: '#0ea5e9', bg: 'rgba(14, 165, 233, 0.15)', border: '#0284c7' };
      case 'APPROVAL_REQUIRED':
        return { label: 'APPROVAL REQ', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.18)', border: '#d97706' };
      case 'RECOVERING':
        return { label: 'RECOVERING', color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.15)', border: '#7c3aed' };
      case 'WAITING':
        return { label: 'WAITING', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)', border: '#b45309' };
      case 'BLOCKED':
      case 'FAILED':
        return { label: hudState, color: '#ef4444', bg: 'rgba(239, 68, 68, 0.15)', border: '#dc2626' };
      case 'COMPLETED':
        return { label: 'COMPLETED', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', border: '#059669' };
      case 'DISCONNECTED':
        return { label: 'OFFLINE', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.15)', border: '#dc2626' };
      default:
        return { label: 'IDLE', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.12)', border: '#475569' };
    }
  }, [hudState]);

  // Actions
  const handleOpenControlRoom = async () => {
    if (window.supervisor?.openControlRoom) {
      await window.supervisor.openControlRoom();
    } else {
      window.location.hash = '';
    }
  };

  const handleMinimize = async () => {
    if (window.supervisor?.minimizeToTray) {
      await window.supervisor.minimizeToTray();
    } else if (window.supervisor?.hideHud) {
      await window.supervisor.hideHud();
    }
  };

  const handleResolveApproval = async (id: string, action: 'APPROVE_ONCE' | 'DENY') => {
    setIsActionLoading(true);
    try {
      await resolveApproval(id, action);
      await refreshState();
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleToggleMissionPause = async () => {
    if (!activeMission) return;
    setIsActionLoading(true);
    try {
      if (activeMission.status === 'PAUSED') {
        await resumeMission(activeMission.id);
      } else {
        await pauseMission(activeMission.id, 'Paused via Floating HUD');
      }
      await refreshState();
    } finally {
      setIsActionLoading(false);
    }
  };

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        backgroundColor: '#090d16',
        color: '#f0f4f8',
        display: 'flex',
        flexDirection: 'column',
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
        fontSize: '12px',
        userSelect: 'none',
        overflow: 'hidden',
        boxSizing: 'border-box',
        border: '1px solid #1e293b'
      }}
    >
      {/* 1. Drag Header & Status Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 10px',
          backgroundColor: '#0e1422',
          borderBottom: '1px solid #1e293b',
          // @ts-ignore
          WebkitAppRegion: 'drag',
          cursor: 'grab'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: isConnected ? '#10b981' : '#ef4444',
              boxShadow: isConnected ? '0 0 8px rgba(16,185,129,0.6)' : 'none'
            }}
          />
          <span style={{ fontWeight: 700, letterSpacing: '0.04em', fontSize: '11px', color: '#e2e8f0' }}>
            SUPERVISOR
          </span>
          <span
            style={{
              fontSize: '9px',
              fontWeight: 600,
              padding: '1px 5px',
              borderRadius: '3px',
              backgroundColor: stateBadgeInfo.bg,
              color: stateBadgeInfo.color,
              border: `1px solid ${stateBadgeInfo.border}`,
              letterSpacing: '0.05em'
            }}
          >
            {stateBadgeInfo.label}
          </span>
        </div>

        {/* Window controls (non-draggable) */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            // @ts-ignore
            WebkitAppRegion: 'no-drag'
          }}
        >
          {latency !== null && (
            <span style={{ fontSize: '10px', color: '#64748b', marginRight: '4px', fontFamily: 'monospace' }}>
              {latency}ms
            </span>
          )}
          <button
            onClick={() => setIsAlwaysOnTop(!isAlwaysOnTop)}
            title={isAlwaysOnTop ? 'Always on Top (Active)' : 'Pin to Top'}
            style={{
              background: 'transparent',
              border: 'none',
              color: isAlwaysOnTop ? '#38bdf8' : '#64748b',
              cursor: 'pointer',
              padding: '2px',
              display: 'flex'
            }}
          >
            <Pin size={12} />
          </button>
          <button
            onClick={handleMinimize}
            title="Minimize to Tray"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#64748b',
              cursor: 'pointer',
              padding: '2px',
              display: 'flex'
            }}
          >
            <Minus size={12} />
          </button>
          <button
            onClick={handleOpenControlRoom}
            title="Open Control Room"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#38bdf8',
              cursor: 'pointer',
              padding: '2px',
              display: 'flex'
            }}
          >
            <ExternalLink size={12} />
          </button>
        </div>
      </div>

      {/* 2. Main Content Body */}
      <div style={{ flex: 1, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: '6px', overflow: 'hidden' }}>
        {/* Mission Title & Agent Row */}
        {activeMission ? (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '6px' }}>
              <div
                style={{
                  fontWeight: 600,
                  fontSize: '12px',
                  color: '#f8fafc',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: '240px'
                }}
                title={activeMission.title}
              >
                {activeMission.title}
              </div>
              <div
                style={{
                  fontSize: '10px',
                  fontFamily: 'monospace',
                  color: '#94a3b8',
                  backgroundColor: '#161f30',
                  padding: '1px 5px',
                  borderRadius: '3px',
                  border: '1px solid #233148'
                }}
              >
                {currentAgent?.model || currentAgent?.agent_id || 'Supervisor'}
              </div>
            </div>

            {/* Current Objective / Task */}
            <div
              style={{
                fontSize: '11px',
                color: '#94a3b8',
                marginTop: '2px',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}
            >
              {activeMission.goal || 'Executing task graph...'}
            </div>
          </div>
        ) : (
          <div style={{ padding: '8px 0', color: '#64748b', textAlign: 'center' }}>
            {isConnected ? 'No active mission. Standing by.' : 'Connecting to Supervisor backend...'}
          </div>
        )}

        {/* 3. Supervisory Context Rows */}
        <div
          style={{
            backgroundColor: '#0e1422',
            borderRadius: '4px',
            border: '1px solid #1c2638',
            padding: '6px 8px',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
            fontSize: '10.5px'
          }}
        >
          {/* Watchdogs Status */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            {activeIntervention ? (
              <>
                <AlertTriangle size={12} color="#f59e0b" />
                <span style={{ color: '#f59e0b', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  Watchdog: {activeIntervention.reason || activeIntervention.anomaly}
                </span>
              </>
            ) : (
              <>
                <CheckCircle2 size={12} color="#10b981" />
                <span style={{ color: '#94a3b8' }}>Watchdogs clear</span>
              </>
            )}
          </div>

          {/* Verification Status */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            {verificationState.status === 'verifying' ? (
              <>
                <Activity size={12} color="#0ea5e9" className="animate-spin" />
                <span style={{ color: '#0ea5e9', fontWeight: 500 }}>Independent verification in progress</span>
              </>
            ) : verificationState.status === 'verified' ? (
              <>
                <CheckCircle2 size={12} color="#10b981" />
                <span style={{ color: '#10b981' }}>Ground truth verified ✓</span>
              </>
            ) : verificationState.status === 'rejected' ? (
              <>
                <XCircle size={12} color="#ef4444" />
                <span style={{ color: '#ef4444' }}>Verification rejected (recovering)</span>
              </>
            ) : (
              <>
                <Layers size={12} color="#64748b" />
                <span style={{ color: '#64748b' }}>Verification gate armed</span>
              </>
            )}
          </div>

          {/* Handoff Status (if active) */}
          {handoffState && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', color: '#c084fc' }}>
              <Cpu size={12} color="#c084fc" />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                Handoff: {handoffState.fromAgent} ➔ {handoffState.toAgent}
              </span>
            </div>
          )}
        </div>

        {/* 4. Actionable Alert / Approval Banner */}
        {topApproval && (
          <div
            style={{
              backgroundColor: 'rgba(245, 158, 11, 0.12)',
              border: '1px solid rgba(245, 158, 11, 0.4)',
              borderRadius: '4px',
              padding: '5px 8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '6px'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', overflow: 'hidden' }}>
              <ShieldAlert size={13} color="#f59e0b" style={{ flexShrink: 0 }} />
              <div style={{ fontSize: '10px', color: '#fef08a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                Approval: {topApproval.action_type || topApproval.action || 'Privileged action'}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
              <button
                disabled={isActionLoading}
                onClick={() => handleResolveApproval(topApproval.id, 'APPROVE_ONCE')}
                style={{
                  backgroundColor: '#059669',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '3px',
                  padding: '2px 6px',
                  fontSize: '9.5px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Approve
              </button>
              <button
                disabled={isActionLoading}
                onClick={() => handleResolveApproval(topApproval.id, 'DENY')}
                style={{
                  backgroundColor: '#dc2626',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '3px',
                  padding: '2px 6px',
                  fontSize: '9.5px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Deny
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 5. Compact Bottom Action Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '4px 10px',
          backgroundColor: '#0b0f1a',
          borderTop: '1px solid #1e293b',
          fontSize: '10.5px'
        }}
      >
        <button
          onClick={handleOpenControlRoom}
          style={{
            background: 'none',
            border: 'none',
            color: '#38bdf8',
            cursor: 'pointer',
            padding: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '3px',
            fontWeight: 500
          }}
        >
          <span>Control Room</span>
          <ExternalLink size={10} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {activeMission && (
            <button
              onClick={handleToggleMissionPause}
              disabled={isActionLoading}
              style={{
                background: 'none',
                border: 'none',
                color: activeMission.status === 'PAUSED' ? '#10b981' : '#f59e0b',
                cursor: 'pointer',
                padding: 0,
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
                fontSize: '10px'
              }}
            >
              {activeMission.status === 'PAUSED' ? (
                <>
                  <Play size={10} />
                  <span>Resume</span>
                </>
              ) : (
                <>
                  <Pause size={10} />
                  <span>Pause</span>
                </>
              )}
            </button>
          )}

          <button
            onClick={refreshState}
            title={`Last sync: ${lastRefreshed.toLocaleTimeString()}`}
            style={{
              background: 'none',
              border: 'none',
              color: '#64748b',
              cursor: 'pointer',
              padding: 0,
              display: 'flex',
              alignItems: 'center'
            }}
          >
            <RefreshCw size={10} />
          </button>
        </div>
      </div>
    </div>
  );
};
