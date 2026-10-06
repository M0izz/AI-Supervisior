import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, 
  Activity, 
  Target, 
  Bot, 
  Database, 
  Compass, 
  ShieldCheck, 
  Settings, 
  Plus, 
  FlaskConical, 
  Cloud, 
  Sparkles
} from 'lucide-react';
import type { TabType, Mission, AgentRecord } from '../types';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (tab: TabType) => void;
  onOpenCreateMission: () => void;
  onSeedDemo: () => void;
  onOpenSync: () => void;
  missions: Mission[];
  agents: AgentRecord[];
  onSelectMission?: (missionId: string) => void;
  onSelectAgent?: (agentId: string) => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onNavigate,
  onOpenCreateMission,
  onSeedDemo,
  onOpenSync,
  missions,
  agents,
  onSelectMission,
  onSelectAgent
}) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  interface CommandItem {
    id: string;
    label: string;
    sublabel?: string;
    icon: any;
    group: string;
    action: () => void;
  }

  const items: CommandItem[] = [
    // Navigation
    { id: 'nav-overview', label: 'Go to Overview', icon: Activity, group: 'Navigation', action: () => { onNavigate('overview'); onClose(); } },
    { id: 'nav-missions', label: 'Go to Missions', icon: Target, group: 'Navigation', action: () => { onNavigate('missions'); onClose(); } },
    { id: 'nav-agents', label: 'Go to Agents', icon: Bot, group: 'Navigation', action: () => { onNavigate('agents'); onClose(); } },
    { id: 'nav-memory', label: 'Go to Project Memory', icon: Database, group: 'Navigation', action: () => { onNavigate('memory'); onClose(); } },
    { id: 'nav-activity', label: 'Go to Activity & Events', icon: Compass, group: 'Navigation', action: () => { onNavigate('activity'); onClose(); } },
    { id: 'nav-approvals', label: 'Go to Approvals Queue', icon: ShieldCheck, group: 'Navigation', action: () => { onNavigate('approvals'); onClose(); } },
    { id: 'nav-settings', label: 'Go to Settings', icon: Settings, group: 'Navigation', action: () => { onNavigate('settings'); onClose(); } },
    { id: 'nav-tour', label: 'Open Product Tour & Architecture', icon: Sparkles, group: 'Navigation', action: () => { onNavigate('landing'); onClose(); } },
    // Actions
    { id: 'act-new', label: 'Create New Supervised Mission', icon: Plus, group: 'Actions', action: () => { onOpenCreateMission(); onClose(); } },
    { id: 'act-demo', label: 'Run Demo Scenario (Loop & Handoff)', icon: FlaskConical, group: 'Actions', action: () => { onSeedDemo(); onClose(); } },
    { id: 'act-sync', label: 'Open Cloud Sync & Devices', icon: Cloud, group: 'Actions', action: () => { onOpenSync(); onClose(); } },
    // Active Missions
    ...missions.slice(0, 5).map(m => ({
      id: `mission-${m.id}`,
      label: `Mission: ${m.title}`,
      sublabel: `${m.status} · ${m.id}`,
      icon: Target,
      group: 'Missions',
      action: () => {
        if (onSelectMission) onSelectMission(m.id);
        onNavigate('missions');
        onClose();
      }
    })),
    // Connected Agents
    ...agents.slice(0, 5).map(a => ({
      id: `agent-${a.agent_id}`,
      label: `Agent: ${a.agent_id}`,
      sublabel: `${a.agent_type} · ${a.status}`,
      icon: Bot,
      group: 'Agents',
      action: () => {
        if (onSelectAgent) onSelectAgent(a.agent_id);
        onNavigate('agents');
        onClose();
      }
    }))
  ];

  const filtered = items.filter(item => {
    if (!query) return true;
    const q = query.toLowerCase();
    return item.label.toLowerCase().includes(q) || (item.sublabel && item.sublabel.toLowerCase().includes(q));
  });

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => (prev + 1) % (filtered.length || 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => (prev - 1 + (filtered.length || 1)) % (filtered.length || 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered[selectedIndex]) {
        filtered[selectedIndex].action();
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="command-palette" onClick={e => e.stopPropagation()}>
        <div className="command-input-wrapper">
          <Search size={16} color="var(--text-muted)" />
          <input
            ref={inputRef}
            className="command-input"
            placeholder="Type a command or search..."
            value={query}
            onChange={e => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
          />
          <span className="kbd-shortcut">ESC</span>
        </div>

        <div className="command-list">
          {filtered.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              No commands matching "{query}"
            </div>
          ) : (
            filtered.map((item, idx) => {
              const Icon = item.icon;
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={item.id}
                  className={`command-item ${isSelected ? 'selected' : ''}`}
                  onClick={item.action}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <Icon size={14} color={isSelected ? 'var(--primary)' : 'var(--text-muted)'} />
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    <div style={{ fontSize: '13px', fontWeight: isSelected ? 500 : 400 }}>{item.label}</div>
                    {item.sublabel && (
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {item.sublabel}
                      </div>
                    )}
                  </div>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{item.group}</span>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
