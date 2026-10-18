export type MissionStatus = 
  | 'DRAFT'
  | 'PLANNING'
  | 'AWAITING_APPROVAL'
  | 'APPROVED'
  | 'RUNNING'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'NEEDS_CLARIFICATION'
  | 'REJECTED'
  | 'CANCELLED'
  | 'FAILED'
  | 'NEEDS_REVIEW'
  | 'CREATED'
  | 'PENDING'
  | 'WAITING_APPROVAL'
  | 'PAUSED'
  | 'INVESTIGATING'
  | 'RECOVERING'
  | 'BLOCKED';

export interface PlanTaskItem {
  task_id: string;
  title: string;
  description?: string;
  dependencies: string[];
  proposed_agent: string;
  required_capabilities: string[];
  expected_files: string[];
  risk_classification: string;
  acceptance_criteria: string[];
  verification_strategy: string;
}

export interface StructuredInterpretation {
  original_request: string;
  interpreted_goal: string;
  expected_deliverables: string[];
  in_scope: string[];
  explicit_exclusions: string[];
  constraints: string[];
  assumptions: string[];
  blocking_questions: string[];
  non_blocking_assumptions: string[];
  risks: string[];
  definition_of_success: string;
  proposed_verification_methods: string[];
}

export interface PlanVersion {
  plan_id: string;
  mission_id: string;
  version: number;
  interpretation: StructuredInterpretation;
  tasks: PlanTaskItem[];
  validation_status: 'VALID' | 'INVALID' | 'NEEDS_CLARIFICATION';
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  approved_by?: string | null;
  approved_at?: string | null;
  rejection_reason?: string | null;
  execution_started_at?: string | null;
  created_at: string;
  updated_at: string;
}

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
  approved_plan_version?: number | null;
  plan_status?: string;
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
  | 'overview'
  | 'missions'
  | 'agents'
  | 'memory'
  | 'falkordb'
  | 'activity'
  | 'approvals'
  | 'settings'
  | 'landing'
  // Legacy aliases for backward compatibility
  | 'control_room'
  | 'mission_detail'
  | 'agent_detail'
  | 'supervisor_events'
  | 'project_memory'
  | 'approval_queue'
  | 'graph_memory'
  | 'graph';

export interface GraphStats {
  connected: boolean;
  graph_name: string;
  host: string;
  port: number;
  nodes_count: number;
  relationships_count: number;
  labels: Record<string, number>;
  relationship_types: Record<string, number>;
  error?: string | null;
}

export interface SafeQueryResult {
  query: string;
  columns: string[];
  rows: any[][];
  row_count: number;
  execution_time_ms: number;
}

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

declare global {
  interface Window {
    supervisorDesktop?: SupervisorDesktopBridge;
  }
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

export interface AdapterInfo {
  adapter_id: string;
  provider: string;
  display_name: string;
  version: string;
  capabilities: string[];
  runtime_type?: string;
  execution_mode?: string;
  infrastructure_provider?: string;
  supported_models?: string[];
  supported_tools?: string[];
  session_support?: boolean;
  remote_execution?: boolean;
  local_execution?: boolean;
  configuration_requirements?: string[];
  availability: {
    status: string;
    available: boolean;
    message: string;
    executable_path?: string | null;
  };
}

export interface ProviderInfo {
  provider_id: string;
  name: string;
  status: string;
  available: boolean;
  message: string;
  capabilities: string[];
  inference_endpoint?: string | null;
  managed_agents_support: boolean;
  action_gateway_support: boolean;
  supported_models: string[];
}

export interface ModelInfo {
  model_id: string;
  name: string;
  developer: string;
  infrastructure_provider: string;
  parameter_size?: string | null;
  specialties: string[];
  available: boolean;
  context_window?: number | null;
}

export interface CustomAgentRegistrationRequest {
  name: string;
  adapter_id: string;
  command_or_endpoint: string;
  provider?: string;
  execution_type?: 'local_process' | 'remote_managed';
  capabilities?: string[];
  env_vars?: Record<string, string>;
}

export type SyncState = 'ONLINE' | 'OFFLINE' | 'SYNCING' | 'SYNCED' | 'ERROR' | 'AUTH_REQUIRED';

export interface SyncStatus {
  state: SyncState;
  device_id: string;
  project_id: string;
  pending_outbox_count: number;
  outbox_pending_count?: number;
  last_synced_at?: string | null;
  last_pull_cursor?: number;
  connected_devices_count?: number;
  error_message?: string | null;
}

export interface SyncDevice {
  device_id: string;
  display_name: string;
  platform: string;
  app_version: string;
  status: 'ACTIVE' | 'REVOKED';
  created_at: string;
  last_seen_at: string;
}

export interface SupervisorDecision {
  id: string;
  timestamp: string;
  decision_type: 'ROUTE' | 'PAUSE' | 'WARN' | 'HANDOFF' | 'VERIFY' | 'REQUIRE_APPROVAL' | 'COMPLETE' | string;
  title: string;
  why: string;
  evidence: string[];
  action: string;
  target_agent?: string;
  result?: string;
  provenance_model?: string;
}

export interface GeminiAnalysisResponse {
  diagnosis: string;
  root_cause: string;
  recommended_recovery: string;
  confidence: number;
  affected_components: string[];
  model_provenance: string;
  is_live: boolean;
}

export interface GraphNode {
  id: string;
  label: 'Mission' | 'Requirement' | 'Task' | 'Execution' | 'ExecutionEvent' | 'Decision' | 'Handoff' | 'Verification' | 'Evidence' | 'Artifact' | 'Agent' | string;
  properties: Record<string, any>;
}

export interface GraphEdge {
  source: string;
  type: string;
  target: string;
}

export interface MissionGraphData {
  mission_id: string;
  nodes_count: number;
  edges_count: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphHealth {
  status: 'HEALTHY' | 'UNAVAILABLE' | 'ERROR' | string;
  connected?: boolean;
  host: string;
  port: number;
  graph_name: string;
  latency_ms: number;
  nodes_count?: number;
  relationships_count?: number;
  error?: string | null;
}

export interface TaskGraphContext {
  task_id: string;
  mission_id: string;
  dependencies: Array<{
    id: string;
    title: string;
    status: string;
    is_verified: boolean;
  }>;
  dependencies_met: boolean;
  prior_attempts: Array<{
    execution_id: string;
    attempt_number: number;
    status: string;
    agent_id: string;
    error_signature?: string;
  }>;
  causal_failure_history: Array<{
    execution_id: string;
    event_id: string;
    event_type: string;
    error_signature: string;
    reason: string;
  }>;
  decisions: Array<{
    decision_id: string;
    decision_type: string;
    action: string;
    reason: string;
  }>;
  handoffs: Array<{
    handoff_id: string;
    source_agent: string;
    target_agent: string;
    trigger: string;
  }>;
  verifications: Array<{
    verification_id: string;
    execution_id: string;
    decision: string;
    summary: string;
  }>;
}

export interface VerificationTrace {
  task_id: string;
  verification_id: string;
  decision: string;
  summary: string;
  verified_at: string;
  execution?: {
    id: string;
    attempt_number: number;
    status: string;
  };
  evidence: Array<{
    id: string;
    type: string;
    description: string;
    passed: boolean;
    empirical_data: any;
  }>;
}

declare global {
  interface Window {
    supervisor?: SupervisorDesktopBridge;
  }
}

export interface AdapterSetupGuide {
  adapter_id: string;
  display_name: string;
  provider: string;
  runtime_type: string;
  description: string;
  executable_name: string;
  install_method: string;
  install_command: string;
  verification_command: string;
  required_env_vars: string[];
  supported_os: string[];
  documentation_url: string;
  prerequisites: string[];
}

export interface GraphActivityEvent {
  id: string;
  operation_type: string;
  timestamp: string;
  description: string;
  status: string;
  mission_id?: string | null;
  task_id?: string | null;
  direction: 'READ' | 'WRITE';
  success: boolean;
}

