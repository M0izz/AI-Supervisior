export type MissionStatus = 
  | 'CREATED'
  | 'PLANNING'
  | 'RUNNING'
  | 'PAUSED'
  | 'INVESTIGATING'
  | 'RECOVERING'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'FAILED'
  | 'BLOCKED'
  | 'WAITING_APPROVAL'
  | 'CANCELLED';

export type TaskStatus = 
  | 'PENDING'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'VERIFIED'
  | 'FAILED'
  | 'BLOCKED'
  | 'SKIPPED';

export type AgentType = 'PLANNER' | 'WORKER' | 'REVIEWER' | 'VERIFIER' | 'SUPERVISOR';
export type AgentStatus = 'IDLE' | 'RUNNING' | 'WAITING' | 'INVESTIGATING' | 'PAUSED' | 'RECOVERING' | 'COMPLETED' | 'FAILED' | 'BUSY';
export type AgentHealth = 'HEALTHY' | 'DEGRADED' | 'ANOMALOUS' | 'OFFLINE';

export type EventSeverity = 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
export type FactStatus = 'OBSERVED' | 'INFERRED' | 'DECIDED' | 'VERIFIED' | 'REJECTED' | 'STALE';

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'DENIED' | 'CANCELLED';
export type ApprovalResolutionAction = 'APPROVE_ONCE' | 'APPROVE_FOR_MISSION' | 'DENY' | 'REJECT' | 'TAKE_CONTROL' | 'CANCEL';

export interface Task {
  id: string;
  mission_id: string;
  title: string;
  name?: string;
  description?: string;
  assigned_agent_id?: string | null;
  status: TaskStatus;
  dependencies: string[];
  expected_files: string[];
  actual_modified_files?: string[];
  actual_files_modified?: string[];
  retry_count?: number;
  attempts?: number;
  failures?: number;
  last_error_signature?: string | null;
  order: number;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  result_summary?: string | null;
  metadata?: Record<string, any>;
}

export interface Mission {
  id: string;
  title: string;
  name?: string;
  goal: string;
  objective?: string;
  status: MissionStatus;
  repository_path: string;
  current_task_id?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  pause_reason?: string | null;
  assigned_agents?: string[];
  assigned_agent_ids?: string[];
  tasks?: Task[];
  constraints?: {
    max_turns: number;
    timeout_seconds: number;
    prohibited_files: string[];
    allowed_commands: string[];
  };
}

export interface AgentRecord {
  agent_id: string;
  agent_type: AgentType;
  model: string;
  status: AgentStatus;
  health?: AgentHealth;
  current_task?: string | null;
  task_id?: string | null;
  mission_id?: string | null;
  iterations?: number;
  tool_calls?: number;
  interventions?: number;
  registered_at?: string;
  last_heartbeat?: string;
  last_activity?: string;
  active_files?: string[];
  metadata?: Record<string, any>;
}

export interface ApprovalRequest {
  id: string;
  mission_id: string;
  task_id?: string | null;
  agent_id: string;
  action_type: string;
  action?: string;
  target: string;
  reason: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  status: ApprovalStatus;
  created_at: string;
  resolved_at?: string | null;
  resolved_by?: string | null;
  feedback?: string | null;
}

export interface Event {
  event_id?: string;
  id?: string;
  timestamp: string;
  type: string;
  event_type?: string;
  severity: EventSeverity;
  mission_id?: string | null;
  task_id?: string | null;
  agent_id?: string | null;
  payload: Record<string, any>;
}

export type MemoryRecordType = 
  | 'VERIFIED_FACT'
  | 'INFERRED_FACT'
  | 'REJECTED_APPROACH'
  | 'DIAGNOSIS'
  | 'RECOVERY_CONTEXT'
  | 'DECISION';

export interface MemoryRecord {
  id: string;
  mission_id: string;
  fact?: string;
  content?: string;
  source?: string;
  created_by?: string;
  status?: FactStatus;
  type?: MemoryRecordType;
  confidence: number;
  category?: string;
  details?: string | null;
  created_at: string;
  updated_at?: string;
  provenance?: {
    source?: string;
    author?: string;
    empirically_verified?: boolean;
  };
}

export interface MemorySummary {
  verified_facts: MemoryRecord[];
  decisions: MemoryRecord[];
  rejected_approaches: MemoryRecord[];
  known_issues: MemoryRecord[];
}

export interface MissionTelemetry {
  mission_id: string;
  execution?: {
    current_task?: string | null;
    completed_tasks: number;
    failed_tasks: number;
    iteration_count: number;
    iterations?: number;
    tool_calls: number;
    runtime_seconds: number;
    runtime?: number;
  };
  reliability?: {
    failure_count: number;
    failures?: number;
    repeated_failures: number;
    interventions: number;
    recovery_attempts: number;
    verification_failures: number;
  };
  risk?: {
    dangerous_actions: number;
    scope_violations: number;
    approval_requests: number;
    blocked_actions: number;
  };
  ci?: {
    jenkins_builds: number;
    build_failures: number;
    test_failures: number;
  };
  cost?: {
    model_calls: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number;
  };
  agents?: Record<string, any>;
  updated_at?: string;
}

export interface GlobalOverviewTelemetry {
  active_missions_count: number;
  total_agents_count: number;
  total_tool_calls: number;
  total_interventions: number;
  total_failures: number;
  total_runtime_seconds: number;
  updated_at: string;
}

export interface InterventionDetail {
  anomaly: string;
  anomaly_type?: string;
  description?: string;
  evidence: string | Record<string, any>;
  action: string;
  target?: string | null;
  confidence: number;
  reason: string;
  timestamp: string;
  mission_id?: string;
  task_id?: string;
}

export type TabType = 
  | 'control_room'
  | 'mission_detail'
  | 'agent_detail'
  | 'supervisor_events'
  | 'project_memory'
  | 'approval_queue';

// Phase 8 Desktop & HUD Types
export type HudVisualState = 
  | 'IDLE'
  | 'RUNNING'
  | 'WAITING'
  | 'BLOCKED'
  | 'RECOVERING'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'FAILED'
  | 'APPROVAL_REQUIRED'
  | 'DISCONNECTED';

export interface DesktopStatus {
  connected: boolean;
  backendUrl: string;
  wsUrl: string;
  hudVisible: boolean;
  controlRoomOpen: boolean;
  platform?: string;
  version?: string;
}

export interface DesktopConfig {
  apiUrl: string;
  wsUrl: string;
  notificationsEnabled: boolean;
  hudEnabled: boolean;
}

export interface DesktopNotificationOptions {
  title: string;
  body: string;
  severity?: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  type?: string;
  id?: string;
}

export interface SupervisorDesktopBridge {
  getStatus: () => Promise<DesktopStatus>;
  openControlRoom: () => Promise<boolean>;
  hideControlRoom: () => Promise<boolean>;
  showHud: () => Promise<boolean>;
  hideHud: () => Promise<boolean>;
  toggleHud: () => Promise<boolean>;
  minimizeToTray: () => Promise<boolean>;
  notify: (options: DesktopNotificationOptions) => Promise<boolean>;
  getConfig: () => Promise<DesktopConfig>;
  quit: () => Promise<void>;
  onHudToggle?: (callback: () => void) => () => void;
  onBackendStateChange?: (callback: (state: string) => void) => () => void;
}

export interface AbsencePolicy {
  enabled: boolean;
  max_duration_seconds: number;
  max_tasks: number;
  max_handoffs: number;
  max_retries: number;
  allowed_capabilities: string[];
  allowed_actions: string[];
  prohibited_commands: string[];
  prohibited_paths: string[];
  approval_policy: 'ALWAYS_ASK' | 'ASK_IF_UNSAFE' | 'AUTO_APPROVE_WITHIN_POLICY' | 'NEVER_ALLOW';
  verification_policy: 'STRICT';
  failure_policy: 'PAUSE_AND_NOTIFY' | 'SAFE_STOP';
}

export type AbsenceSessionState =
  | 'DISABLED'
  | 'ARMED'
  | 'ACTIVE'
  | 'PAUSED'
  | 'EXPIRED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'BLOCKED';

export interface AbsenceSessionInfo {
  absence_id: string;
  mission_id: string;
  status: AbsenceSessionState;
  policy: AbsencePolicy;
  started_at?: string | null;
  expires_at?: string | null;
  created_by: string;
  tasks_completed: number;
  retries_count: number;
  handoffs_count: number;
  paused_reason?: string | null;
  created_at: string;
  updated_at: string;
}

declare global {
  interface Window {
    supervisor?: SupervisorDesktopBridge;
  }
}
