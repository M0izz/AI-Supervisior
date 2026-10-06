import React, { useState } from 'react';
import { 
  Bot, 
  Play, 
  Pause 
} from 'lucide-react';
import type { AgentRecord, AdapterInfo } from '../types';
import { pauseAgent, resumeAgent } from '../api';

interface AgentsProps {
  agents: AgentRecord[];
  adapters: AdapterInfo[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string | null) => void;
  onRefresh: () => void;
}

export const Agents: React.FC<AgentsProps> = ({
  agents,
  adapters,
  selectedAgentId,
  onSelectAgent,
  onRefresh
}) => {
  const [isActing, setIsActing] = useState(false);

  const safeAgents = Array.isArray(agents) ? agents : [];
  const safeAdapters = Array.isArray(adapters) ? adapters : [];

  // Group adapters with live agent state if available
  const fleetList = safeAdapters.map(adapter => {
    const liveInstance = safeAgents.find(a => 
      a.agent_id.toLowerCase().includes((adapter.adapter_id || '').toLowerCase()) ||
      a.model.toLowerCase().includes((adapter.adapter_id || '').toLowerCase())
    );
    const isAvail = adapter.availability?.available ?? true;
    return {
      adapter,
      liveInstance,
      id: adapter.adapter_id,
      name: adapter.display_name,
      isWorking: liveInstance?.status === 'RUNNING' || liveInstance?.status === 'BUSY',
      isPaused: liveInstance?.status === 'PAUSED',
      isAvailable: isAvail,
      status: liveInstance ? liveInstance.status : (isAvail ? 'AVAILABLE' : 'OFFLINE')
    };
  });

  const selectedItem = fleetList.find(f => f.id === selectedAgentId) || fleetList[0];

  const handleToggleAgentPause = async () => {
    if (!selectedItem?.liveInstance) return;
    setIsActing(true);
    try {
      if (selectedItem.isPaused) {
        await resumeAgent(selectedItem.liveInstance.agent_id);
      } else {
        await pauseAgent(selectedItem.liveInstance.agent_id);
      }
      onRefresh();
    } finally {
      setIsActing(false);
    }
  };

  const workingCount = fleetList.filter(f => f.isWorking).length;
  const availableCount = fleetList.filter(f => f.isAvailable && !f.isWorking).length;
  const offlineCount = fleetList.filter(f => !f.isAvailable).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1080px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-title">
          <h1>Agents Workspace</h1>
          <p>
            {fleetList.length} connected provider adapters · {workingCount} working · {availableCount} idle · {offlineCount} unavailable
          </p>
        </div>
      </div>

      {/* Main Grid: Fleet List & Selected Agent Details */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '20px' }}>
        {/* Left: Agent List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Provider Fleet
          </div>

          {fleetList.map(item => {
            const isSelected = selectedItem?.id === item.id;
            return (
              <div
                key={item.id}
                className="surface-card surface-card-interactive"
                style={{
                  borderColor: isSelected ? 'var(--primary)' : 'var(--border)',
                  backgroundColor: isSelected ? 'var(--surface-elevated)' : 'var(--surface)',
                  padding: '14px'
                }}
                onClick={() => onSelectAgent(item.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Bot size={16} color={isSelected ? 'var(--primary)' : 'var(--text-secondary)'} />
                    <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>
                      {item.name}
                    </span>
                  </div>

                  <span className="status-pill">
                    <span className={`status-dot ${item.isWorking ? 'running' : item.isAvailable ? 'active' : 'idle'}`} />
                    <span style={{ fontSize: '11px' }}>
                      {item.isWorking ? 'working' : item.isPaused ? 'paused' : item.isAvailable ? 'idle' : 'unavailable'}
                    </span>
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '10px', flexWrap: 'wrap' }}>
                  {item.adapter.capabilities.map(c => (
                    <span key={c} className="badge badge-neutral" style={{ fontSize: '10px' }}>
                      {c.toLowerCase()}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: Selected Agent Workspace Inspector */}
        <div>
          {selectedItem ? (
            <div className="surface-card" style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '24px' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Bot size={20} color="var(--primary)" />
                    <h2 style={{ fontSize: '18px' }}>{selectedItem.name}</h2>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    adapter_id: {selectedItem.id} · provider: {selectedItem.adapter.provider || 'EXECUTION_PROVIDER'}
                  </div>
                </div>

                {selectedItem.liveInstance && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleToggleAgentPause}
                    disabled={isActing}
                  >
                    {selectedItem.isPaused ? <Play size={12} /> : <Pause size={12} />}
                    <span>{selectedItem.isPaused ? 'Resume' : 'Pause Agent'}</span>
                  </button>
                )}
              </div>

              {/* Status Section */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '14px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Status & Availability</div>
                <div style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                  {selectedItem.isWorking
                    ? 'Currently executing tasks on active mission.'
                    : selectedItem.isAvailable
                      ? 'CLI and runtime detected. Ready for assignment by dynamic router.'
                      : 'CLI adapter not detected in system path. Configure in settings or install provider tool.'}
                </div>
              </div>

              {/* Capabilities */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Capabilities & Tooling</div>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {selectedItem.adapter.capabilities.map(c => (
                    <span key={c} className="badge badge-blue">
                      {c.toLowerCase()}
                    </span>
                  ))}
                </div>
              </div>

              {/* Reliability & Metrics */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Supervisory Governance</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div style={{ padding: '10px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Task Verification Rate</div>
                    <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px', color: 'var(--success)' }}>
                      100% verified
                    </div>
                  </div>

                  <div style={{ padding: '10px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Watchdog Interventions</div>
                    <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px', color: 'var(--text-primary)' }}>
                      {selectedItem.liveInstance?.interventions || 0} recorded
                    </div>
                  </div>
                </div>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                Agents act as execution providers. The Supervisor owns planning, routing, failure detection, memory, and independent verification.
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <Bot size={20} />
              <div className="empty-state-title">Select an agent</div>
              <div className="empty-state-desc">Select an agent from the fleet list to inspect its capabilities and live tasks.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
