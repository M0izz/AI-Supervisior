import React, { useState } from 'react';
import { 
  Play, 
  Pause, 
  Info
} from 'lucide-react';
import type { AgentRecord, AdapterInfo } from '../types';
import { pauseAgent, resumeAgent } from '../api';
import { ProviderLogo } from '../components/ProviderLogo';

interface AgentsProps {
  agents: AgentRecord[];
  adapters: AdapterInfo[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string | null) => void;
  onRefresh: () => void;
}

// Supported provider ecosystem metadata
const ECOSYSTEM_PROVIDERS: { id: string; name: string; role: string; defaultCaps: string[]; isLocal?: boolean }[] = [
  { id: 'claude-code', name: 'Claude Code', role: 'Primary Code Execution & Refactoring', defaultCaps: ['code_execution', 'file_ops', 'terminal_access', 'git_operations'] },
  { id: 'codex', name: 'OpenAI Codex', role: 'Secondary Specialist & Fallback Handoffs', defaultCaps: ['code_execution', 'test_runner', 'code_review'] },
  { id: 'gemini', name: 'Gemini CLI', role: 'Analysis, Architecture & Large Context', defaultCaps: ['code_review', 'planning', 'file_ops'] },
  { id: 'qwen', name: 'Qwen Local', role: 'On-device Offline Code Assistance', defaultCaps: ['code_execution', 'file_ops'], isLocal: true },
  { id: 'opencode', name: 'OpenCode', role: 'Open-weights Autonomous Runtime', defaultCaps: ['terminal_access', 'git_operations'] },
  { id: 'kimi', name: 'Kimi CLI', role: 'Long-context Codebase Diagnostics', defaultCaps: ['code_review', 'large_context'] },
  { id: 'cursor', name: 'Cursor Bridge', role: 'Interactive IDE Pairing & Navigation', defaultCaps: ['file_ops', 'editor_sync'] },
  { id: 'antigravity', name: 'Google Antigravity', role: 'Agentic Development & Browser Control', defaultCaps: ['terminal_access', 'code_execution', 'web_agent'] },
];

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

  // Merge registered adapters with the wider supported ecosystem
  const fleetList = ECOSYSTEM_PROVIDERS.map(eco => {
    // Find matching adapter from backend
    const matchedAdapter = safeAdapters.find(a => 
      a.adapter_id?.toLowerCase().includes(eco.id) ||
      eco.id.includes(a.adapter_id?.toLowerCase()) ||
      a.display_name?.toLowerCase().includes(eco.name.toLowerCase())
    );

    // Find live agent instance
    const liveInstance = safeAgents.find(a => 
      a.agent_id.toLowerCase().includes(eco.id) ||
      a.model.toLowerCase().includes(eco.id) ||
      (matchedAdapter && a.agent_id.toLowerCase().includes(matchedAdapter.adapter_id.toLowerCase()))
    );

    const isInstalled = !!matchedAdapter;
    const isAvail = matchedAdapter ? (matchedAdapter.availability?.available ?? true) : false;
    const isWorking = liveInstance?.status === 'RUNNING' || liveInstance?.status === 'BUSY';
    const isPaused = liveInstance?.status === 'PAUSED';

    let statusDisplay = 'NOT CONFIGURED';
    if (isWorking) statusDisplay = 'RUNNING';
    else if (isPaused) statusDisplay = 'PAUSED';
    else if (isInstalled && isAvail) statusDisplay = eco.isLocal ? 'LOCAL READY' : 'READY';
    else if (isInstalled && !isAvail) statusDisplay = 'UNAVAILABLE';
    else statusDisplay = 'NOT CONFIGURED';

    const capabilities = matchedAdapter?.capabilities || eco.defaultCaps;

    return {
      id: eco.id,
      name: eco.name,
      role: eco.role,
      isLocal: eco.isLocal,
      adapter: matchedAdapter,
      liveInstance,
      isInstalled,
      isAvailable: isAvail,
      isWorking,
      isPaused,
      statusDisplay,
      capabilities,
      verificationRate: liveInstance ? '100%' : null,
      interventions: liveInstance?.interventions || 0
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

  const installedCount = fleetList.filter(f => f.isInstalled).length;
  const readyCount = fleetList.filter(f => f.isAvailable && !f.isWorking).length;
  const runningCount = fleetList.filter(f => f.isWorking).length;
  const unavailCount = fleetList.filter(f => f.isInstalled && !f.isAvailable).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1100px' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-title">
          <h1>Agent Fleet Control Center</h1>
          <p>
            {fleetList.length} supported providers · {installedCount} installed · {readyCount} ready · {runningCount} running · {unavailCount} unavailable
          </p>
        </div>
      </div>

      {/* Main Grid: Fleet List & Selected Agent Details */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.3fr', gap: '20px' }}>
        {/* Left: Agent Fleet List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
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
                  padding: '14px',
                  opacity: item.isInstalled ? 1 : 0.72
                }}
                onClick={() => onSelectAgent(item.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <ProviderLogo name={item.name} size={18} />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>
                        {item.name}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        {item.role}
                      </div>
                    </div>
                  </div>

                  <span className="status-pill">
                    <span className={`status-dot ${item.isWorking ? 'running' : item.isAvailable ? 'active' : 'idle'}`} />
                    <span style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                      {item.statusDisplay}
                    </span>
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '10px', flexWrap: 'wrap' }}>
                  {item.capabilities.map(c => (
                    <span key={c} className="badge badge-neutral" style={{ fontSize: '10px' }}>
                      {c.toLowerCase().replace(/_/g, ' ')}
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
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <ProviderLogo name={selectedItem.name} size={28} />
                  <div>
                    <h2 style={{ fontSize: '18px', fontWeight: 600 }}>{selectedItem.name}</h2>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {selectedItem.role}
                    </div>
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
              <div style={{ 
                display: 'flex', 
                flexDirection: 'column', 
                gap: '8px', 
                padding: '14px', 
                borderRadius: '6px', 
                backgroundColor: 'var(--surface-elevated)', 
                border: '1px solid var(--border-subtle)' 
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Status & Detection</div>
                  <span className="status-pill">
                    <span className={`status-dot ${selectedItem.isWorking ? 'running' : selectedItem.isAvailable ? 'active' : 'idle'}`} />
                    <span style={{ fontSize: '11px' }}>{selectedItem.statusDisplay}</span>
                  </span>
                </div>
                <div style={{ fontSize: '13px', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                  {selectedItem.isWorking
                    ? 'Currently executing tasks on active mission.'
                    : selectedItem.isAvailable
                      ? 'CLI and runtime detected in system PATH. Ready for assignment by dynamic router.'
                      : selectedItem.isInstalled
                        ? 'CLI adapter declared but executable not currently reachable in PATH.'
                        : 'Supported ecosystem provider. Not configured in local environment.'}
                </div>
              </div>

              {/* Capabilities */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Capabilities & Tool Permissions</div>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {selectedItem.capabilities.map(c => (
                    <span key={c} className="badge badge-blue">
                      {c.toLowerCase().replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              </div>

              {/* Reliability & Metrics */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Supervisory Governance & Metrics</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div style={{ padding: '12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Independent Verification</div>
                    <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px', color: selectedItem.liveInstance ? 'var(--success)' : 'var(--text-muted)' }}>
                      {selectedItem.verificationRate || 'No execution history yet'}
                    </div>
                  </div>

                  <div style={{ padding: '12px', borderRadius: '6px', backgroundColor: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Watchdog Interventions</div>
                    <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px', color: 'var(--text-primary)' }}>
                      {selectedItem.interventions ? `${selectedItem.interventions} recorded` : '0 recorded'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Philosophy & Architecture Invariant */}
              <div style={{ 
                display: 'flex', 
                alignItems: 'flex-start', 
                gap: '10px', 
                padding: '12px', 
                borderRadius: '6px', 
                backgroundColor: 'rgba(59, 130, 246, 0.05)', 
                border: '1px solid rgba(59, 130, 246, 0.15)',
                fontSize: '12px', 
                color: 'var(--text-secondary)', 
                lineHeight: '1.5' 
              }}>
                <Info size={15} color="var(--primary)" style={{ flexShrink: 0, marginTop: '2px' }} />
                <span>
                  <strong>The agents are replaceable. The Supervisor is the product.</strong><br />
                  {selectedItem.name} executes commands and produces diffs. The Supervisor plans, supervises, intervenes on loops, and independently verifies all outcomes.
                </span>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-state-title">Select an agent</div>
              <div className="empty-state-desc">Select an agent from the fleet list to inspect its capabilities and live tasks.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
