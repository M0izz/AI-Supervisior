import React, { useState, useEffect } from 'react';
import { 
  Terminal, 
  Play, 
  Pause, 
  Layers, 
  Server, 
  Cpu, 
  Users,
  RotateCcw
} from 'lucide-react';
import type { Mission, Task, AgentRecord } from '../types';
import { TaskDAGView } from '../components/TaskDAGView';
import { pauseMission, resumeMission, getMissionTasks } from '../api';

interface MissionDetailProps {
  missions: Mission[];
  selectedMissionId: string | null;
  onSelectMission: (missionId: string) => void;
  agents: AgentRecord[];
  onRefresh: () => void;
}

export const MissionDetail: React.FC<MissionDetailProps> = ({
  missions,
  selectedMissionId,
  onSelectMission,
  agents,
  onRefresh
}) => {
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isActing, setIsActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Find selected mission or fallback to first
  const currentMission = missions.find(m => m.id === selectedMissionId) || missions[0];

  useEffect(() => {
    if (!currentMission) return;
    if (currentMission.tasks && currentMission.tasks.length > 0) {
      setTasks(currentMission.tasks);
    } else {
      getMissionTasks(currentMission.id)
        .then(res => {
          if (res && res.tasks) setTasks(res.tasks);
        })
        .catch(() => {
          setTasks([]);
        });
    }
  }, [currentMission]);

  const handlePause = async () => {
    if (!currentMission) return;
    setIsActing(true);
    setActionError(null);
    try {
      await pauseMission(currentMission.id);
      onRefresh();
    } catch (e: any) {
      setActionError(e.message || 'Failed to pause mission');
    } finally {
      setIsActing(false);
    }
  };

  const handleResume = async () => {
    if (!currentMission) return;
    setIsActing(true);
    setActionError(null);
    try {
      await resumeMission(currentMission.id);
      onRefresh();
    } catch (e: any) {
      setActionError(e.message || 'Failed to resume mission');
    } finally {
      setIsActing(false);
    }
  };

  if (!currentMission) {
    return (
      <div className="cr-panel" style={{ textAlign: 'center', padding: '48px' }}>
        <div style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          NO ACTIVE MISSIONS AVAILABLE. PLEASE SEED A DEMO MISSION TO VIEW DETAILS.
        </div>
      </div>
    );
  }

  const assignedList = currentMission.assigned_agents || currentMission.assigned_agent_ids || [];
  const assignedAgents = agents.filter(a => 
    assignedList.includes(a.agent_id) || 
    tasks.some(t => t.assigned_agent_id === a.agent_id)
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Top Header & Mission Switcher */}
      <div className="cr-panel" style={{ marginBottom: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
              MISSION SELECTOR:
            </span>
            <select 
              value={currentMission.id} 
              onChange={(e) => onSelectMission(e.target.value)}
              style={{ width: 'auto', minWidth: '240px', fontWeight: 600 }}
            >
              {missions.map(m => (
                <option key={m.id} value={m.id}>
                  {m.title || m.name} ({m.status})
                </option>
              ))}
            </select>
            <span className="badge badge-cyan">
              {currentMission.status}
            </span>
          </div>

          {/* Action buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {currentMission.status === 'RUNNING' ? (
              <button 
                className="btn btn-warning" 
                onClick={handlePause} 
                disabled={isActing}
              >
                <Pause size={12} />
                <span>PAUSE MISSION</span>
              </button>
            ) : (
              <button 
                className="btn btn-success" 
                onClick={handleResume} 
                disabled={isActing}
              >
                <Play size={12} />
                <span>RESUME MISSION</span>
              </button>
            )}
          </div>
        </div>

        {actionError && (
          <div style={{ marginTop: '10px', color: 'var(--status-crimson)', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
            Error: {actionError}
          </div>
        )}
      </div>

      {/* Main Content Grid */}
      <div className="grid-12">
        {/* Left Column: Objective, DAG, Executions (8 cols) */}
        <div style={{ gridColumn: 'span 8', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Mission Objective */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Terminal size={15} color="var(--status-cyan)" />
                <span>Mission Objective</span>
              </div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                CREATED {new Date(currentMission.created_at).toLocaleString()}
              </span>
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-primary)', lineHeight: 1.5 }}>
              {currentMission.goal || currentMission.objective}
            </div>
          </div>

          {/* Task DAG */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Layers size={15} color="var(--status-cyan)" />
                <span>Task DAG (Directed Acyclic Graph)</span>
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                {tasks.filter(t => t.status === 'COMPLETED' || t.status === 'VERIFIED').length} / {tasks.length} COMPLETED
              </div>
            </div>

            <TaskDAGView 
              tasks={tasks}
              selectedTaskId={selectedTask?.id}
              onSelectTask={(task) => setSelectedTask(task)}
            />
          </div>

          {/* Jenkins Builds & CI Verification History */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Server size={15} color="var(--status-emerald)" />
                <span>Jenkins CI & Unit Test Verifications</span>
              </div>
              <span className="badge badge-emerald">CI PASS</span>
            </div>

            <table className="cr-table">
              <thead>
                <tr>
                  <th>Build #</th>
                  <th>Job Name</th>
                  <th>Tests Passed</th>
                  <th>Tests Failed</th>
                  <th>Exit Code</th>
                  <th>Timestamp</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="font-mono">#102</td>
                  <td>csv-import-regression</td>
                  <td className="font-mono" style={{ color: 'var(--status-emerald)' }}>47 passed</td>
                  <td className="font-mono" style={{ color: 'var(--text-muted)' }}>0 failed</td>
                  <td className="font-mono">0</td>
                  <td>2 mins ago</td>
                  <td><span className="badge badge-emerald">PASSED</span></td>
                </tr>
                <tr>
                  <td className="font-mono">#101</td>
                  <td>csv-import-regression</td>
                  <td className="font-mono" style={{ color: 'var(--status-emerald)' }}>45 passed</td>
                  <td className="font-mono" style={{ color: 'var(--status-crimson)' }}>2 failed</td>
                  <td className="font-mono">1</td>
                  <td>6 mins ago</td>
                  <td><span className="badge badge-crimson">FAILED</span></td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Docker Execution Sandbox Audit */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Server size={15} color="var(--status-cyan)" />
                <span>Docker Sandbox Executions</span>
              </div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                ISOLATED WORKSPACE: /app/workspace
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{
                backgroundColor: 'var(--bg-core)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '3px',
                padding: '10px',
                fontSize: '11px',
                fontFamily: 'var(--font-mono)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--status-cyan)' }}>CONTAINER: agy-worker-sandbox-01</span>
                  <span style={{ color: 'var(--status-emerald)' }}>EXIT CODE: 0 (SUCCESS)</span>
                </div>
                <div style={{ color: 'var(--text-muted)' }}>
                  COMMAND: pytest tests/test_csv_parser.py -v --tb=short
                </div>
                <div style={{ color: 'var(--text-secondary)', marginTop: '4px' }}>
                  RESOURCE ENFORCEMENT: Memory Limit: 512MB &bull; CPU: 1.0 &bull; Network: Restricted
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Supervisor State, Agents, Recovery History (4 cols) */}
        <div style={{ gridColumn: 'span 4', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Supervisor State for this Mission */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Cpu size={15} color="var(--status-cyan)" />
                <span>Supervisor State</span>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                  CURRENT PHASE
                </span>
                <span className="badge badge-cyan">{currentMission.status}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                  ACTIVE WATCHDOG
                </span>
                <span className="badge badge-emerald">LOOP DETECTOR ARMED</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                  RETRY BUDGET
                </span>
                <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-primary)' }}>
                  2 / 5 used
                </span>
              </div>
            </div>
          </div>

          {/* Recovery History */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <RotateCcw size={15} color="var(--status-amber)" />
                <span>Recovery History</span>
              </div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                1 INTERVENTION
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{
                backgroundColor: 'var(--bg-core)',
                border: '1px solid var(--status-amber-border)',
                borderRadius: '3px',
                padding: '10px',
                fontSize: '11px',
                fontFamily: 'var(--font-mono)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--status-amber)', fontWeight: 600 }}>
                  <span>STRATEGY: DELEGATE_REVIEWER</span>
                  <span>CONFIDENCE 94%</span>
                </div>
                <div style={{ color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Target: reviewer_01 &bull; Status: SUCCESS
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '10px', marginTop: '4px' }}>
                  Diagnosed regex unescaped comma flaw in csv_parser.py
                </div>
              </div>
            </div>
          </div>

          {/* Assigned Agents */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Users size={15} color="var(--status-cyan)" />
                <span>Assigned Agent Crew</span>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {assignedAgents.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '11px', fontFamily: 'var(--font-mono)', textAlign: 'center', padding: '12px' }}>
                  NO AGENTS ASSIGNED TO THIS MISSION
                </div>
              ) : (
                assignedAgents.map(agent => (
                  <div 
                    key={agent.agent_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 10px',
                      backgroundColor: 'var(--bg-core)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '3px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '11px'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{agent.agent_id}</div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>{agent.agent_type} &bull; {agent.model}</div>
                    </div>
                    <span className="badge badge-neutral">{agent.status}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
