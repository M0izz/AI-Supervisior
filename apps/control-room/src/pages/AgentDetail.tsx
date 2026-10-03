import React, { useState } from 'react';
import { 
  Users, 
  Cpu, 
  Lock, 
  Play, 
  Pause, 
  Wrench, 
  FileCode
} from 'lucide-react';
import type { AgentRecord, AgentStatus } from '../types';
import { pauseAgent, resumeAgent } from '../api';

interface AgentDetailProps {
  agents: AgentRecord[];
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string) => void;
  onRefresh: () => void;
}

export const AgentDetail: React.FC<AgentDetailProps> = ({
  agents,
  selectedAgentId,
  onSelectAgent,
  onRefresh
}) => {
  const [isActing, setIsActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const currentAgent = agents.find(a => a.agent_id === selectedAgentId) || agents[0];

  const handlePause = async () => {
    if (!currentAgent) return;
    setIsActing(true);
    setActionError(null);
    try {
      await pauseAgent(currentAgent.agent_id);
      onRefresh();
    } catch (e: any) {
      setActionError(e.message || 'Failed to pause agent');
    } finally {
      setIsActing(false);
    }
  };

  const handleResume = async () => {
    if (!currentAgent) return;
    setIsActing(true);
    setActionError(null);
    try {
      await resumeAgent(currentAgent.agent_id);
      onRefresh();
    } catch (e: any) {
      setActionError(e.message || 'Failed to resume agent');
    } finally {
      setIsActing(false);
    }
  };

  if (!currentAgent) {
    return (
      <div className="cr-panel" style={{ textAlign: 'center', padding: '48px' }}>
        <div style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          NO REGISTERED AGENTS IN FLEET. SEED A DEMO MISSION TO REGISTER AGENTS.
        </div>
      </div>
    );
  }

  const getAgentStatusBadge = (status: AgentStatus) => {
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Top Header & Agent Selector */}
      <div className="cr-panel" style={{ marginBottom: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
              AGENT SELECTOR:
            </span>
            <select 
              value={currentAgent.agent_id} 
              onChange={(e) => onSelectAgent(e.target.value)}
              style={{ width: 'auto', minWidth: '220px', fontWeight: 600 }}
            >
              {agents.map(a => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.agent_id} ({a.agent_type}) - {a.status}
                </option>
              ))}
            </select>
            {getAgentStatusBadge(currentAgent.status)}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {currentAgent.status === 'PAUSED' ? (
              <button 
                className="btn btn-success" 
                onClick={handleResume} 
                disabled={isActing}
              >
                <Play size={12} />
                <span>RESUME AGENT</span>
              </button>
            ) : (
              <button 
                className="btn btn-warning" 
                onClick={handlePause} 
                disabled={isActing}
              >
                <Pause size={12} />
                <span>PAUSE AGENT</span>
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

      {/* Main Agent Details */}
      <div className="grid-12">
        {/* Left Column: Metadata, Tool Call Timeline, File Locks (8 cols) */}
        <div style={{ gridColumn: 'span 8', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Metadata Card */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Cpu size={15} color="var(--status-cyan)" />
                <span>Agent Execution Profile</span>
              </div>
              <span className="badge badge-neutral" style={{ fontSize: '10px' }}>
                {currentAgent.agent_type}
              </span>
            </div>

            <div className="grid-3" style={{ gap: '12px', marginBottom: '16px' }}>
              <div style={{ backgroundColor: 'var(--bg-core)', padding: '10px', borderRadius: '3px' }}>
                <div className="telemetry-label">Assigned Model</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: 'var(--status-cyan)', marginTop: '4px' }}>
                  {currentAgent.model}
                </div>
              </div>
              <div style={{ backgroundColor: 'var(--bg-core)', padding: '10px', borderRadius: '3px' }}>
                <div className="telemetry-label">Mission Context</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '4px' }}>
                  {currentAgent.mission_id || 'STANDBY'}
                </div>
              </div>
              <div style={{ backgroundColor: 'var(--bg-core)', padding: '10px', borderRadius: '3px' }}>
                <div className="telemetry-label">Current Task</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '4px' }}>
                  {currentAgent.task_id || currentAgent.current_task || 'IDLE'}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)', paddingTop: '10px' }}>
              <span>Registered: {currentAgent.registered_at ? new Date(currentAgent.registered_at).toLocaleString() : 'Active session'}</span>
              <span>Last Heartbeat: {currentAgent.last_heartbeat ? new Date(currentAgent.last_heartbeat).toLocaleTimeString() : 'Just now'}</span>
            </div>
          </div>

          {/* Tool Calls Execution Stream */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Wrench size={15} color="var(--status-cyan)" />
                <span>Tool Execution Trace</span>
              </div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                BUDGET: {currentAgent.tool_calls || 3} / 20 USED
              </span>
            </div>

            <table className="cr-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Tool</th>
                  <th>Target / Arguments</th>
                  <th>Exit Code / Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="font-mono">13:30:12</td>
                  <td className="font-mono" style={{ color: 'var(--status-cyan)' }}>run_tests</td>
                  <td className="font-mono">pytest tests/test_csv_parser.py</td>
                  <td><span className="badge badge-emerald">EXIT 0</span></td>
                </tr>
                <tr>
                  <td className="font-mono">13:28:45</td>
                  <td className="font-mono" style={{ color: 'var(--status-cyan)' }}>edit_file</td>
                  <td className="font-mono">src/csv_parser.py (regex fix)</td>
                  <td><span className="badge badge-emerald">MODIFIED</span></td>
                </tr>
                <tr>
                  <td className="font-mono">13:25:10</td>
                  <td className="font-mono" style={{ color: 'var(--status-cyan)' }}>read_file</td>
                  <td className="font-mono">src/csv_parser.py (1-100)</td>
                  <td><span className="badge badge-emerald">SUCCESS</span></td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Active File Locks & Scope Isolation */}
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Lock size={15} color="var(--status-emerald)" />
                <span>File Locks & Conflict Avoidance</span>
              </div>
              <span className="badge badge-emerald">NO CONTENTION</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{
                backgroundColor: 'var(--bg-core)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '3px',
                padding: '10px',
                fontSize: '11px',
                fontFamily: 'var(--font-mono)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileCode size={14} color="var(--status-cyan)" />
                  <span>src/csv_parser.py</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Exclusive Write Lock</span>
                  <span className="badge badge-emerald">ACQUIRED</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Fleet List (4 cols) */}
        <div style={{ gridColumn: 'span 4' }}>
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <Users size={15} color="var(--text-secondary)" />
                <span>Full Agent Fleet</span>
              </div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                {agents.length} TOTAL
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {agents.map(a => {
                const isSelected = a.agent_id === currentAgent.agent_id;
                return (
                  <div 
                    key={a.agent_id}
                    onClick={() => onSelectAgent(a.agent_id)}
                    style={{
                      backgroundColor: isSelected ? 'var(--bg-surface-elevated)' : 'var(--bg-core)',
                      border: isSelected ? '1px solid var(--status-cyan)' : '1px solid var(--border-subtle)',
                      borderRadius: '3px',
                      padding: '10px 12px',
                      cursor: 'pointer'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-primary)' }}>
                        {a.agent_id}
                      </strong>
                      <span className="badge badge-neutral" style={{ fontSize: '9px' }}>
                        {a.agent_type}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '6px', fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                      <span>Model: {a.model}</span>
                      <span style={{ color: a.status === 'RUNNING' || a.status === 'BUSY' ? 'var(--status-cyan)' : 'inherit' }}>
                        {a.status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
