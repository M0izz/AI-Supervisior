import React, { useState } from 'react';
import { 
  Play, 
  Pause, 
  Plus,
  Cpu,
  Server,
  Terminal,
  Search,
  X
} from 'lucide-react';
import type { AgentRecord, AdapterInfo } from '../types';
import { pauseAgent, resumeAgent, registerCustomAgent } from '../api';
import { ProviderLogo } from '../components/ProviderLogo';

interface AgentsProps {
  agents: AgentRecord[];
  adapters: AdapterInfo[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string | null) => void;
  onRefresh: () => void;
}

interface FleetItem {
  id: string;
  name: string;
  provider: string;
  role: string;
  category: 'Coding' | 'Research' | 'Local' | 'Cloud' | 'Open Source';
  infrastructure: 'LOCAL' | 'DIGITALOCEAN' | 'NEBIUS';
  defaultCaps: string[];
  supportedModels?: string[];
  sessionSupport?: boolean;
}

const FLEET_REGISTRY: FleetItem[] = [
  { id: 'claude_code', name: 'Claude Code', provider: 'Anthropic', role: 'Autonomous Code Editing & Terminal', category: 'Coding', infrastructure: 'LOCAL', defaultCaps: ['code_execution', 'filesystem_write', 'terminal_execution', 'git'], supportedModels: ['Claude 3.7 Sonnet'] },
  { id: 'codex', name: 'OpenAI Codex', provider: 'OpenAI', role: 'Precision Code Repair & Fallback Handoff', category: 'Coding', infrastructure: 'LOCAL', defaultCaps: ['code_execution', 'test_execution', 'git'], supportedModels: ['Codex / GPT-4o'] },
  { id: 'hermes', name: 'Hermes Agent', provider: 'Nous Research', role: 'Long-running Autonomous Agent Sessions', category: 'Open Source', infrastructure: 'DIGITALOCEAN', defaultCaps: ['code_execution', 'long_running_session', 'remote_execution', 'governed_tools'], supportedModels: ['Hermes-4-70B', 'Gemma-4-31B'], sessionSupport: true },
  { id: 'digitalocean_managed', name: 'DigitalOcean Managed Agent', provider: 'DigitalOcean', role: 'MicroVM Cloud Sandbox & Action Gateway', category: 'Cloud', infrastructure: 'DIGITALOCEAN', defaultCaps: ['remote_execution', 'microvm_isolation', 'governed_tools', 'git'], supportedModels: ['Hermes 4', 'Gemma 4', 'Llama 3.3'], sessionSupport: true },
  { id: 'gemini', name: 'Gemini CLI', provider: 'Google', role: 'Multimodal Analysis & Architecture Planning', category: 'Research', infrastructure: 'LOCAL', defaultCaps: ['documentation', 'code_review', 'planning'], supportedModels: ['Gemini 2.5 Flash', 'Gemini 2.5 Pro'] },
  { id: 'goose', name: 'Goose', provider: 'Block', role: 'Open Extensible On-machine Agent', category: 'Open Source', infrastructure: 'LOCAL', defaultCaps: ['code_execution', 'terminal_execution', 'developer_tools'], supportedModels: ['Open Weights'] },
  { id: 'cline', name: 'Cline', provider: 'Cline', role: 'Autonomous Coding & File Patching', category: 'Coding', infrastructure: 'LOCAL', defaultCaps: ['code_execution', 'filesystem_write', 'terminal_execution'], supportedModels: ['Claude 3.7', 'DeepSeek'] },
  { id: 'opencode', name: 'OpenCode', provider: 'Open-Source', role: 'Open Weight Agentic Engine', category: 'Open Source', infrastructure: 'NEBIUS', defaultCaps: ['terminal_execution', 'git', 'filesystem_write'], supportedModels: ['Qwen 2.5 Coder', 'Kimi'] },
  { id: 'qwen', name: 'Qwen Local', provider: 'Alibaba Cloud', role: 'On-device Local LLM Offline Agent', category: 'Local', infrastructure: 'LOCAL', defaultCaps: ['local_model', 'code_execution', 'filesystem_read'], supportedModels: ['Qwen 2.5 Coder 32B'] },
  { id: 'kimi', name: 'Kimi Code', provider: 'Moonshot AI', role: 'Ultra Long-context Code Diagnostics', category: 'Research', infrastructure: 'NEBIUS', defaultCaps: ['large_context', 'code_review'], supportedModels: ['Kimi 1.5'] }
];

const INFERENCE_MODELS = [
  { id: 'gemma-4-31B-it', name: 'Google Gemma 4', developer: 'Google', infra: 'DIGITALOCEAN', size: '31B', focus: 'Supervisor reasoning & lightweight planning' },
  { id: 'hermes-4-70b-instruct', name: 'Nous Hermes 4', developer: 'Nous Research', infra: 'DIGITALOCEAN', size: '70B', focus: 'Long-session agentic coding & tool use' },
  { id: 'qwen-2.5-coder-32b', name: 'Qwen 2.5 Coder', developer: 'Alibaba Cloud', infra: 'NEBIUS', size: '32B', focus: 'Deep syntax repair & algorithm refactoring' },
  { id: 'nemotron-4-340b', name: 'NVIDIA Nemotron 4', developer: 'NVIDIA', infra: 'NEBIUS', size: '340B', focus: 'Supervisory situation reasoning & anomaly diagnosis' },
  { id: 'llama-3.3-70b', name: 'Meta Llama 3.3', developer: 'Meta', infra: 'DIGITALOCEAN', size: '70B', focus: 'General code generation and test crafting' },
  { id: 'deepseek-r1-distill', name: 'DeepSeek R1 Distill', developer: 'DeepSeek', infra: 'NEBIUS', size: '70B', focus: 'Chain-of-thought logic & math invariants' }
];

export const Agents: React.FC<AgentsProps> = ({
  agents,
  adapters,
  selectedAgentId,
  onSelectAgent,
  onRefresh
}) => {
  const [activeTab, setActiveTab] = useState<'agents' | 'models' | 'providers'>('agents');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [isActing, setIsActing] = useState(false);
  const [isCustomModalOpen, setIsCustomModalOpen] = useState(false);

  // Custom agent registration form
  const [customName, setCustomName] = useState('');
  const [customId, setCustomId] = useState('');
  const [customCommand, setCustomCommand] = useState('');
  const [customExecutionMode, setCustomExecutionMode] = useState<'local_process' | 'remote_managed'>('local_process');

  const safeAgents = Array.isArray(agents) ? agents : [];
  const safeAdapters = Array.isArray(adapters) ? adapters : [];

  // Build unified fleet view
  const fleetList = FLEET_REGISTRY.map(reg => {
    const matchedAdapter = safeAdapters.find(a => 
      a.adapter_id?.toLowerCase() === reg.id.toLowerCase() ||
      a.adapter_id?.toLowerCase().includes(reg.id.toLowerCase())
    );

    const liveInstance = safeAgents.find(a => 
      a.agent_id.toLowerCase().includes(reg.id.toLowerCase()) ||
      (matchedAdapter && a.agent_id.toLowerCase().includes(matchedAdapter.adapter_id.toLowerCase()))
    );

    const isInstalled = !!matchedAdapter;
    const isAvail = matchedAdapter ? (matchedAdapter.availability?.available ?? true) : false;
    const isWorking = liveInstance?.status === 'RUNNING' || liveInstance?.status === 'BUSY';
    const isPaused = liveInstance?.status === 'PAUSED';

    let statusDisplay = 'NOT CONFIGURED';
    if (isWorking) statusDisplay = 'RUNNING';
    else if (isPaused) statusDisplay = 'PAUSED';
    else if (isInstalled && isAvail) statusDisplay = 'READY';
    else if (isInstalled && !isAvail) statusDisplay = 'UNAVAILABLE';
    else statusDisplay = 'NOT CONFIGURED';

    const capabilities = matchedAdapter?.capabilities || reg.defaultCaps;

    return {
      ...reg,
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

  const filteredFleet = fleetList.filter(item => {
    if (selectedCategory !== 'All') {
      if (selectedCategory === 'Coding' && item.category !== 'Coding') return false;
      if (selectedCategory === 'Research' && item.category !== 'Research') return false;
      if (selectedCategory === 'Local' && item.infrastructure !== 'LOCAL') return false;
      if (selectedCategory === 'Cloud' && item.infrastructure !== 'DIGITALOCEAN' && item.infrastructure !== 'NEBIUS') return false;
      if (selectedCategory === 'Open Source' && item.category !== 'Open Source') return false;
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return item.name.toLowerCase().includes(q) || item.role.toLowerCase().includes(q) || item.provider.toLowerCase().includes(q);
    }
    return true;
  });

  const selectedItem = fleetList.find(f => f.id === selectedAgentId) || filteredFleet[0] || fleetList[0];

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

  const handleRegisterCustom = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customName || !customId || !customCommand) return;
    try {
      await registerCustomAgent({
        name: customName,
        adapter_id: customId.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
        command_or_endpoint: customCommand,
        execution_type: customExecutionMode,
        capabilities: ['code_execution', 'filesystem_write']
      });
      setIsCustomModalOpen(false);
      setCustomName('');
      setCustomId('');
      setCustomCommand('');
      onRefresh();
    } catch (err: any) {
      alert(`Registration failed: ${err.message}`);
    }
  };

  const readyCount = fleetList.filter(f => f.isAvailable).length;
  const runningCount = fleetList.filter(f => f.isWorking).length;
  const unavailCount = fleetList.filter(f => !f.isAvailable).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1100px' }}>
      {/* Top Header & Metrics */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '14px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            Agent Fleet Control Center
          </h1>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            {fleetList.length} runtimes integrated · <span style={{ color: 'var(--success)', fontWeight: 500 }}>{readyCount} ready</span> · {runningCount} active · <span style={{ color: 'var(--text-muted)' }}>{unavailCount} unconfigured</span>
          </div>
        </div>

        <button 
          className="btn btn-secondary btn-sm"
          onClick={() => setIsCustomModalOpen(true)}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Plus size={13} />
          <span>Register Custom Agent</span>
        </button>
      </div>

      {/* Sub-view Switcher Tabs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '10px' }}>
        <button
          className={`btn btn-sm ${activeTab === 'agents' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveTab('agents')}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Terminal size={14} />
          <span>Agent Runtimes ({fleetList.length})</span>
        </button>

        <button
          className={`btn btn-sm ${activeTab === 'models' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveTab('models')}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Cpu size={14} />
          <span>Inference Models ({INFERENCE_MODELS.length})</span>
        </button>

        <button
          className={`btn btn-sm ${activeTab === 'providers' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveTab('providers')}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Server size={14} />
          <span>Infrastructure Providers (3)</span>
        </button>
      </div>

      {/* VIEW 1: AGENT RUNTIMES */}
      {activeTab === 'agents' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Filter Pills & Search */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              {['All', 'Coding', 'Research', 'Local', 'Cloud', 'Open Source'].map(cat => (
                <button
                  key={cat}
                  className={`badge ${selectedCategory === cat ? 'badge-blue' : 'badge-neutral'}`}
                  style={{ cursor: 'pointer', padding: '5px 10px', fontSize: '11px' }}
                  onClick={() => setSelectedCategory(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', backgroundColor: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '6px', padding: '4px 10px', width: '240px' }}>
              <Search size={13} color="var(--text-muted)" />
              <input
                type="text"
                placeholder="Search runtimes..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                style={{ background: 'transparent', border: 'none', outline: 'none', color: 'var(--text-primary)', fontSize: '12px', width: '100%' }}
              />
            </div>
          </div>

          {/* Grid Layout: Left Cards & Right Inspector */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.25fr', gap: '18px' }}>
            {/* Cards List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {filteredFleet.map(item => {
                const isSelected = selectedItem?.id === item.id;
                return (
                  <div
                    key={item.id}
                    className="surface-card surface-card-interactive"
                    style={{
                      borderColor: isSelected ? 'var(--primary)' : 'var(--border)',
                      backgroundColor: isSelected ? 'var(--surface-elevated)' : 'var(--surface)',
                      padding: '12px 14px',
                      opacity: item.isAvailable ? 1 : 0.7
                    }}
                    onClick={() => onSelectAgent(item.id)}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <ProviderLogo providerId={item.id} name={item.name} size={20} />
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span>{item.name}</span>
                            <span className="badge badge-neutral" style={{ fontSize: '9px', padding: '1px 5px' }}>
                              {item.infrastructure}
                            </span>
                          </div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            {item.provider} · {item.role}
                          </div>
                        </div>
                      </div>

                      <span className="status-pill">
                        <span className={`status-dot ${item.isWorking ? 'running' : item.isAvailable ? 'active' : 'idle'}`} />
                        <span style={{ fontSize: '10px' }}>{item.statusDisplay}</span>
                      </span>
                    </div>

                    <div style={{ display: 'flex', gap: '5px', marginTop: '8px', flexWrap: 'wrap' }}>
                      {item.capabilities.slice(0, 4).map(c => (
                        <span key={c} className="badge badge-neutral" style={{ fontSize: '10px' }}>
                          {c.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Selected Agent Inspector */}
            <div>
              {selectedItem ? (
                <div className="surface-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <ProviderLogo providerId={selectedItem.id} name={selectedItem.name} size={28} />
                      <div>
                        <h2 style={{ fontSize: '17px', fontWeight: 600 }}>{selectedItem.name}</h2>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          {selectedItem.provider} · {selectedItem.role}
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
                        <span>{selectedItem.isPaused ? 'Resume' : 'Pause'}</span>
                      </button>
                    )}
                  </div>

                  {/* Status Banner */}
                  <div style={{
                    padding: '12px',
                    borderRadius: '6px',
                    backgroundColor: 'var(--surface-elevated)',
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        Supervisory Status
                      </span>
                      <span className="status-pill">
                        <span className={`status-dot ${selectedItem.isWorking ? 'running' : selectedItem.isAvailable ? 'active' : 'idle'}`} />
                        <span style={{ fontSize: '10px' }}>{selectedItem.statusDisplay}</span>
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                      {selectedItem.isWorking
                        ? 'Executing tasks on assigned mission under watchdog monitoring.'
                        : selectedItem.isAvailable
                          ? `Ready for assignment by Dynamic Router (${selectedItem.infrastructure} execution).`
                          : selectedItem.isInstalled
                            ? 'Adapter installed but CLI binary or endpoint not reachable in environment.'
                            : 'Runtime not configured on this machine.'}
                    </div>
                  </div>

                  {/* Backing Infrastructure & Capabilities */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Execution Substrate</span>
                      <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {selectedItem.infrastructure === 'LOCAL' ? 'Local Workstation (Host PATH)' : selectedItem.infrastructure === 'DIGITALOCEAN' ? 'DigitalOcean MicroVM / Action Gateway' : 'Nebius Token Factory'}
                      </span>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Session Support</span>
                      <span style={{ fontSize: '13px', fontWeight: 600, color: selectedItem.sessionSupport ? 'var(--success)' : 'var(--text-muted)' }}>
                        {selectedItem.sessionSupport ? 'Persistent Sessions (Attach / Resume)' : 'Single-task Isolation'}
                      </span>
                    </div>
                  </div>

                  {/* Supported Models */}
                  {selectedItem.supportedModels && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Supported Models</span>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {selectedItem.supportedModels.map(m => (
                          <span key={m} className="badge badge-blue" style={{ fontSize: '11px' }}>
                            {m}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Capabilities List */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Declared Capabilities</span>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {selectedItem.capabilities.map(c => (
                        <span key={c} className="badge badge-neutral" style={{ fontSize: '11px' }}>
                          {c.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* VIEW 2: INFERENCE MODELS */}
      {activeTab === 'models' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            Underlying language models accessed through infrastructure providers (DigitalOcean Inference, Nebius, and Local).
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px' }}>
            {INFERENCE_MODELS.map(m => (
              <div key={m.id} className="surface-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Cpu size={16} color="var(--primary)" />
                    <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>{m.name}</span>
                  </div>
                  <span className="badge badge-neutral" style={{ fontSize: '10px' }}>{m.infra}</span>
                </div>

                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  {m.focus}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', paddingTop: '6px', borderTop: '1px solid var(--border-subtle)' }}>
                  <span>Developer: {m.developer}</span>
                  <span>Size: {m.size}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* VIEW 3: INFRASTRUCTURE PROVIDERS */}
      {activeTab === 'providers' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            Execution substrates and inference gateways connected to AI Supervisor.
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '14px' }}>
            {/* DigitalOcean Card */}
            <div className="surface-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <ProviderLogo providerId="digitalocean" size={24} />
                <div>
                  <h3 style={{ fontSize: '15px', fontWeight: 600 }}>DigitalOcean</h3>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Cloud Infrastructure & Inference</div>
                </div>
              </div>

              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Provides Managed Agents in isolated microVMs, Action Gateway governed MCP tool access, and Serverless Inference with Google Gemma 4.
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: 'var(--text-muted)' }}>
                <div>✓ Managed Agents & Droplets</div>
                <div>✓ Action Gateway governed tools</div>
                <div>✓ Serverless Gemma 4 Inference</div>
              </div>

              <div style={{ paddingTop: '8px', borderTop: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span className="badge badge-neutral" style={{ fontSize: '10px' }}>OPTIONAL INTEGRATION</span>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Configure via Settings</span>
              </div>
            </div>

            {/* Nebius Card */}
            <div className="surface-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <ProviderLogo providerId="nebius" size={24} />
                <div>
                  <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Nebius Token Factory</h3>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Open Model Inference Gateway</div>
                </div>
              </div>

              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                OpenAI-compatible inference gateway powering NVIDIA Nemotron 4, Nous Hermes, Qwen 2.5 Coder, and Kimi Code models.
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: 'var(--text-muted)' }}>
                <div>✓ Dynamic model catalog queries</div>
                <div>✓ Supervisory reasoning backend</div>
                <div>✓ Token Factory high throughput</div>
              </div>

              <div style={{ paddingTop: '8px', borderTop: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span className="badge badge-neutral" style={{ fontSize: '10px' }}>OPTIONAL INTEGRATION</span>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Configure via Settings</span>
              </div>
            </div>

            {/* Local Card */}
            <div className="surface-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <ProviderLogo providerId="local" size={24} />
                <div>
                  <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Local Workstation</h3>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Developer Machine Host</div>
                </div>
              </div>

              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Executes agents on your local workstation with isolated Git worktrees and real-time subprocess telemetry.
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: 'var(--text-muted)' }}>
                <div>✓ Git worktree isolation</div>
                <div>✓ Local CLI execution (Claude, Codex)</div>
                <div>✓ Offline-first persistence (SQLite WAL)</div>
              </div>

              <div style={{ paddingTop: '8px', borderTop: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span className="badge badge-blue" style={{ fontSize: '10px' }}>ALWAYS ACTIVE</span>
                <span style={{ fontSize: '11px', color: 'var(--success)' }}>Connected</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Register Custom Agent */}
      {isCustomModalOpen && (
        <div className="modal-overlay" onClick={() => setIsCustomModalOpen(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '480px' }}>
            <div className="modal-header">
              <h2 style={{ fontSize: '15px', fontWeight: 600 }}>Register Custom Agent</h2>
              <button className="btn btn-ghost btn-sm" onClick={() => setIsCustomModalOpen(false)}>
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleRegisterCustom}>
              <div className="modal-body" style={{ gap: '12px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 500 }}>Agent Display Name</label>
                  <input
                    type="text"
                    placeholder="e.g. In-House Python Fixer"
                    value={customName}
                    onChange={e => setCustomName(e.target.value)}
                    required
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 500 }}>Unique Identifier Slug</label>
                  <input
                    type="text"
                    placeholder="e.g. custom_python_agent"
                    value={customId}
                    onChange={e => setCustomId(e.target.value)}
                    required
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 500 }}>Command or HTTP Endpoint</label>
                  <input
                    type="text"
                    placeholder="e.g. python -m custom_agent or https://agent.internal/api"
                    value={customCommand}
                    onChange={e => setCustomCommand(e.target.value)}
                    required
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 500 }}>Execution Mode</label>
                  <select
                    value={customExecutionMode}
                    onChange={e => setCustomExecutionMode(e.target.value as any)}
                  >
                    <option value="local_process">Local Process (Subprocess in Worktree)</option>
                    <option value="remote_managed">Remote Managed (HTTP / MicroVM)</option>
                  </select>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setIsCustomModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Register Agent
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
