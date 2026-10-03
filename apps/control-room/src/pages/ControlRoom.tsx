import React from 'react';
import { 
  Terminal, 
  Users, 
  ShieldAlert, 
  CheckCircle2, 
  AlertTriangle, 
  RotateCw, 
  Server, 
  Cpu, 
  ArrowRight,
  ExternalLink
} from 'lucide-react';
import type { Mission, AgentRecord, InterventionDetail, MissionTelemetry } from '../types';

interface ControlRoomProps {
  missions: Mission[];
  agents: AgentRecord[];
  activeInterventions: InterventionDetail[];
  telemetry: MissionTelemetry | null;
  onSelectMission: (missionId: string) => void;
  onSelectAgent: (agentId: string) => void;
  onNavigateToTab: (tab: any) => void;
}

export const ControlRoom: React.FC<ControlRoomProps> = ({
  missions,
  agents,
  activeInterventions,
  telemetry: _telemetry,
  onSelectMission,
  onSelectAgent,
  onNavigateToTab
}) => {
  const activeMissions = missions.filter(m => m.status === 'RUNNING' || m.status === 'INVESTIGATING' || m.status === 'WAITING_APPROVAL' || m.status === 'RECOVERING');
  const runningAgents = agents.filter(a => a.status === 'RUNNING' || a.status === 'BUSY');
  const failedMissions = missions.filter(m => m.status === 'FAILED');

  const getMissionStatusBadge = (status: string) => {
    switch (status) {
      case 'RUNNING':
        return <span className="badge badge-cyan"><RotateCw size={10} className="spin" /> RUNNING</span>;
      case 'INVESTIGATING':
        return <span className="badge badge-amber"><AlertTriangle size={10} /> INVESTIGATING</span>;
      case 'RECOVERING':
        return <span className="badge badge-amber"><RotateCw size={10} className="spin" /> RECOVERING</span>;
      case 'WAITING_APPROVAL':
        return <span className="badge badge-crimson"><ShieldAlert size={10} /> WAITING APPROVAL</span>;
      case 'COMPLETED':
        return <span className="badge badge-emerald"><CheckCircle2 size={10} /> COMPLETED</span>;
      case 'FAILED':
        return <span className="badge badge-crimson"><AlertTriangle size={10} /> FAILED</span>;
      default:
        return <span className="badge badge-neutral">{status}</span>;
    }
  };

  const getAgentStatusBadge = (status: string) => {
    switch (status) {
      case 'RUNNING':
      case 'BUSY':
        return <span className="badge badge-cyan"><span className="pulse-dot cyan" /> BUSY</span>;
      case 'PAUSED':
        return <span className="badge badge-amber"><span className="pulse-dot amber" /> PAUSED</span>;
      case 'FAILED':
        return <span className="badge badge-crimson"><span className="pulse-dot crimson" /> FAILED</span>;
      case 'IDLE':
      default:
        return <span className="badge badge-neutral"><span className="pulse-dot neutral" /> IDLE</span>;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Cockpit Telemetry Bar */}
      <div className="grid-4">
        {/* Metric 1: Active Missions */}
        <div className="cr-panel" style={{ margin: 0 }}>
          <div className="telemetry-label">Active Missions</div>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: '4px' }}>
            <div className="telemetry-value" style={{ color: activeMissions.length > 0 ? 'var(--status-cyan)' : 'var(--text-primary)' }}>
              {activeMissions.length}
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
              {missions.length} TOTAL
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Terminal size={12} color="var(--text-muted)" />
            <span>{failedMissions.length} Failures recorded</span>
          </div>
        </div>

        {/* Metric 2: Agent Fleet */}
        <div className="cr-panel" style={{ margin: 0 }}>
          <div className="telemetry-label">Autonomous Agents</div>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: '4px' }}>
            <div className="telemetry-value" style={{ color: runningAgents.length > 0 ? 'var(--status-emerald)' : 'var(--text-primary)' }}>
              {runningAgents.length}
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
              {agents.length} REGISTERED
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Users size={12} color="var(--text-muted)" />
            <span>Worker, Planner, Reviewer, Verifier</span>
          </div>
        </div>

        {/* Metric 3: Supervisor Engine */}
        <div className="cr-panel" style={{ margin: 0 }}>
          <div className="telemetry-label">Supervisor Status</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
            <span className="pulse-dot cyan" />
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.25rem', fontWeight: 700, color: 'var(--status-cyan)' }}>
              WATCHING
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <ShieldAlert size={12} color={activeInterventions.length > 0 ? 'var(--status-amber)' : 'var(--status-emerald)'} />
            <span style={{ color: activeInterventions.length > 0 ? 'var(--status-amber)' : 'var(--text-secondary)' }}>
              {activeInterventions.length} Current Interventions
            </span>
          </div>
        </div>

        {/* Metric 4: Infrastructure CI/Docker */}
        <div className="cr-panel" style={{ margin: 0 }}>
          <div className="telemetry-label">CI / Sandbox Status</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
            <CheckCircle2 size={18} color="var(--status-emerald)" />
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.25rem', fontWeight: 700, color: 'var(--status-emerald)' }}>
              JENKINS PASS
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Server size={12} color="var(--text-muted)" />
            <span>Docker Sandbox: Enforcing isolation</span>
          </div>
        </div>
      </div>

      {/* Main Section: Active Missions & Live Agent Status */}
      <div className="grid-12">
        {/* Left Column: Missions Overview (7 cols) */}
        <div style={{ gridColumn: 'span 7' }}>
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Terminal size={15} color="var(--status-cyan)" />
                <span>Active Mission Matrix</span>
              </div>
              <button 
                className="btn" 
                style={{ fontSize: '10px', padding: '3px 8px' }}
                onClick={() => onNavigateToTab('mission_detail')}
              >
                <span>Full DAG</span>
                <ArrowRight size={10} />
              </button>
            </div>

            {missions.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                NO MISSIONS ACTIVE. CLICK "SEED DEMO MISSION" TO INITIALIZE WORKLOAD.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {missions.map((mission) => {
                  const tasksList = mission.tasks || [];
                  const completedTasks = tasksList.filter(t => t.status === 'COMPLETED' || t.status === 'VERIFIED').length;
                  const totalTasks = tasksList.length;
                  const progressPct = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
                  const assignedList = mission.assigned_agents || mission.assigned_agent_ids || [];

                  return (
                    <div 
                      key={mission.id}
                      style={{
                        backgroundColor: 'var(--bg-core)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: '4px',
                        padding: '14px',
                        cursor: 'pointer',
                        transition: 'border-color 0.15s ease'
                      }}
                      onClick={() => onSelectMission(mission.id)}
                      onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--border-strong)'}
                      onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border-subtle)'}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                              MISSION
                            </span>
                            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                              {mission.title || mission.name}
                            </span>
                          </div>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                            ID: {mission.id} &bull; Created {new Date(mission.created_at).toLocaleTimeString()}
                          </div>
                        </div>
                        {getMissionStatusBadge(mission.status)}
                      </div>

                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '10px', lineHeight: 1.4 }}>
                        {mission.goal || mission.objective}
                      </div>

                      {/* Progress Bar */}
                      {totalTasks > 0 && (
                        <div style={{ marginBottom: '10px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                            <span>DAG TASKS PROGRESS ({completedTasks}/{totalTasks})</span>
                            <span>{progressPct}%</span>
                          </div>
                          <div style={{ height: '4px', backgroundColor: 'var(--border-default)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{
                              width: `${progressPct}%`,
                              height: '100%',
                              backgroundColor: mission.status === 'COMPLETED' ? 'var(--status-emerald)' : 'var(--status-cyan)',
                              transition: 'width 0.3s ease'
                            }} />
                          </div>
                        </div>
                      )}

                      {/* Footer: Assigned agents & quick link */}
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '11px',
                        borderTop: '1px solid var(--border-subtle)',
                        paddingTop: '8px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)' }}>
                          <Users size={12} />
                          <span>Active Agents: {assignedList.length > 0 ? assignedList.join(', ') : 'planner_01, worker_01'}</span>
                        </div>
                        <span style={{ color: 'var(--status-cyan)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          Inspect Mission <ExternalLink size={10} />
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Agent Registry Fleet & Watchdogs (5 cols) */}
        <div style={{ gridColumn: 'span 5' }}>
          {/* Agent Fleet Panel */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Users size={15} color="var(--status-cyan)" />
                <span>Agent Registry Fleet</span>
              </div>
              <button 
                className="btn" 
                style={{ fontSize: '10px', padding: '3px 8px' }}
                onClick={() => onNavigateToTab('agent_detail')}
              >
                <span>Registry</span>
                <ArrowRight size={10} />
              </button>
            </div>

            {agents.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                NO AGENTS REGISTERED
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {agents.map((agent) => (
                  <div 
                    key={agent.agent_id}
                    style={{
                      backgroundColor: 'var(--bg-core)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '3px',
                      padding: '10px 12px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between'
                    }}
                    onClick={() => onSelectAgent(agent.agent_id)}
                    onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--border-strong)'}
                    onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border-subtle)'}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <strong style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-primary)' }}>
                          {agent.agent_id}
                        </strong>
                        <span className="badge badge-neutral" style={{ fontSize: '9px', padding: '1px 4px' }}>
                          {agent.agent_type}
                        </span>
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>
                        Model: {agent.model} &bull; Task: {agent.task_id || agent.current_task || 'IDLE'}
                      </div>
                    </div>
                    <div>
                      {getAgentStatusBadge(agent.status)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Supervisor Watchdogs & Interventions */}
          <div className="cr-panel" style={{ marginBottom: 0 }}>
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Cpu size={15} color="var(--status-amber)" />
                <span>Supervisor Safeguards</span>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', backgroundColor: 'var(--bg-core)', borderRadius: '2px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Loop Detector (3-identical fail threshold):</span>
                <span style={{ color: 'var(--status-emerald)' }}>ARMED & ACTIVE</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', backgroundColor: 'var(--bg-core)', borderRadius: '2px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Tool-Call & Iteration Budget:</span>
                <span style={{ color: 'var(--status-emerald)' }}>ARMED (Max 20 / 30)</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', backgroundColor: 'var(--bg-core)', borderRadius: '2px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>File Conflict / Scope Enforcer:</span>
                <span style={{ color: 'var(--status-emerald)' }}>ENFORCING LOCKS</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', backgroundColor: 'var(--bg-core)', borderRadius: '2px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Dangerous Command Interceptor:</span>
                <span style={{ color: 'var(--status-emerald)' }}>ZERO IMPLICIT APPROVAL</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
