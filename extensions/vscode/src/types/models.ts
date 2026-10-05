export type BackendConnectionState = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'ERROR';

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

export type AgentStatus =
  | 'IDLE'
  | 'RUNNING'
  | 'WAITING'
  | 'INVESTIGATING'
  | 'PAUSED'
  | 'RECOVERING'
  | 'COMPLETED'
  | 'FAILED'
  | 'BUSY';

export type AgentHealth = 'HEALTHY' | 'DEGRADED' | 'ANOMALOUS' | 'OFFLINE';

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'DENIED' | 'CANCELLED';

export type ApprovalResolutionAction =
  | 'APPROVE_ONCE'
  | 'APPROVE_FOR_MISSION'
  | 'DENY'
  | 'REJECT'
  | 'TAKE_CONTROL'
  | 'CANCEL';

export interface Task {
  id: string;
  mission_id: string;
  title: string;
  status: TaskStatus;
  dependencies: string[];
  expected_files: string[];
  assigned_agent_id?: string | null;
  order: number;
  result_summary?: string | null;
  error_signature?: string | null;
  metadata?: Record<string, any>;
}

export interface Mission {
  id: string;
  title: string;
  goal: string;
  status: MissionStatus;
  repository_path: string;
  current_task_id?: string | null;
  active_agent_id?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  pause_reason?: string | null;
  assigned_agents?: string[];
  tasks?: Task[];
}

export interface AgentRecord {
  agent_id: string;
  agent_type: string;
  model: string;
  status: AgentStatus;
  health?: AgentHealth;
  current_task?: string | null;
  task_id?: string | null;
  mission_id?: string | null;
  interventions?: number;
  tool_calls?: number;
  metadata?: Record<string, any>;
}

export interface AdapterAvailability {
  status: string;
  available: boolean;
  message?: string;
  executable_path?: string | null;
}

export interface AdapterInfo {
  adapter_id: string;
  provider: string;
  display_name: string;
  version: string;
  capabilities: string[];
  availability: AdapterAvailability;
}

export interface ApprovalRequest {
  id: string;
  mission_id: string;
  task_id?: string | null;
  agent_id: string;
  action_type: string;
  target: string;
  reason: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  status: ApprovalStatus;
  created_at: string;
  resolved_at?: string | null;
  resolved_by?: string | null;
  feedback?: string | null;
}

export interface AbsenceSession {
  absence_id: string;
  mission_id: string;
  status: 'ARMED' | 'ACTIVE' | 'PAUSED' | 'EXPIRED' | 'COMPLETED' | 'CANCELLED';
  expires_at?: string;
  remaining_seconds?: number;
  policy: {
    max_duration_seconds: number;
    budget_ceiling_usd: number;
    max_retries: number;
    max_handoffs: number;
    allowed_actions: string[];
    protected_files: string[];
  };
}

export interface Event {
  event_id?: string;
  id?: string;
  timestamp: string;
  type: string;
  severity: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  mission_id?: string | null;
  task_id?: string | null;
  agent_id?: string | null;
  payload: Record<string, any>;
}

export interface SelectionContext {
  filePath: string;
  relativeFilePath: string;
  languageId: string;
  startLine: number;
  endLine: number;
  code: string;
}

export interface DiagnosticItem {
  message: string;
  severity: string;
  source?: string;
  line: number;
  character: number;
}

export interface DiagnosticsContext {
  filePath: string;
  relativeFilePath: string;
  diagnostics: DiagnosticItem[];
}
