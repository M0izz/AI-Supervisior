import type {
  Mission,
  Task,
  AgentRecord,
  ApprovalRequest,
  Event,
  MemoryRecord,
  MemorySummary,
  MissionTelemetry,
  GlobalOverviewTelemetry,
  ApprovalResolutionAction
} from './types';

const API_BASE = import.meta.env.VITE_API_URL || '';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {})
    }
  });

  if (!res.ok) {
    let errMsg = `Request failed: ${res.status} ${res.statusText}`;
    try {
      const errBody = await res.json();
      if (errBody.detail) errMsg = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail);
    } catch {
      // fallback to status text
    }
    throw new Error(errMsg);
  }

  return res.json();
}

// Missions
export async function getMissions(): Promise<Mission[]> {
  return fetchJson<Mission[]>('/api/missions');
}
export const fetchMissions = getMissions;

export async function getMission(missionId: string): Promise<Mission> {
  return fetchJson<Mission>(`/api/missions/${missionId}`);
}

export async function getMissionState(missionId: string): Promise<{
  mission_id: string;
  title: string;
  status: string;
  supervisor_state: string;
  current_task_id: string | null;
  tasks_count: number;
  completed_tasks: number;
  pending_approvals_count: number;
  agents: AgentRecord[];
  active_agents_count: number;
  telemetry: any;
}> {
  return fetchJson(`/api/missions/${missionId}/state`);
}

export async function updateMissionStatus(missionId: string, status: string, reason?: string): Promise<{ status: string; mission: Mission }> {
  return fetchJson(`/api/missions/${missionId}/status`, {
    method: 'POST',
    body: JSON.stringify({ status, reason })
  });
}

export async function pauseMission(missionId: string, reason: string = 'Paused from Control Room UI'): Promise<{ status: string }> {
  return fetchJson(`/api/missions/${missionId}/pause`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
}

export async function resumeMission(missionId: string): Promise<{ status: string }> {
  return fetchJson(`/api/missions/${missionId}/resume`, {
    method: 'POST'
  });
}

export async function takeControl(missionId: string, operator: string = 'Operator', reason: string = 'Manual control assertion'): Promise<{ status: string }> {
  return fetchJson(`/api/missions/${missionId}/take-control`, {
    method: 'POST',
    body: JSON.stringify({ operator, reason })
  });
}

export async function seedDemoMission(): Promise<{ status: string; mission_id: string; tasks_count: number; mission: Mission }> {
  return fetchJson('/api/missions/seed-demo', {
    method: 'POST'
  });
}

// Tasks
export async function getMissionTasks(missionId: string): Promise<{
  tasks: Task[];
  graph: { nodes: any[]; edges: any[] };
}> {
  return fetchJson(`/api/missions/${missionId}/tasks`);
}

export async function getTask(missionId: string, taskId: string): Promise<Task> {
  return fetchJson(`/api/missions/${missionId}/tasks/${taskId}`);
}

// Telemetry
export async function getOverviewTelemetry(): Promise<{
  overview: GlobalOverviewTelemetry;
  missions: any[];
}> {
  return fetchJson('/api/telemetry/overview');
}
export const fetchTelemetry = getOverviewTelemetry;

export async function getMissionTelemetry(missionId: string): Promise<MissionTelemetry> {
  return fetchJson<MissionTelemetry>(`/api/missions/${missionId}/telemetry`);
}

// Agents
export async function getAgents(params?: { missionId?: string; agentType?: string; status?: string }): Promise<AgentRecord[]> {
  const q = new URLSearchParams();
  if (params?.missionId) q.set('mission_id', params.missionId);
  if (params?.agentType) q.set('agent_type', params.agentType);
  if (params?.status) q.set('status', params.status);
  const data = await fetchJson<{ agents: AgentRecord[]; count: number }>(`/api/agents?${q.toString()}`);
  return data.agents;
}
export const fetchAgents = getAgents;

export async function getAgent(agentId: string): Promise<AgentRecord> {
  return fetchJson<AgentRecord>(`/api/agents/${agentId}`);
}

export async function getAgentState(agentId: string): Promise<any> {
  return fetchJson(`/api/agents/${agentId}/state`);
}

export async function pauseAgent(agentId: string): Promise<{ status: string }> {
  return fetchJson(`/api/agents/${agentId}/pause`, { method: 'POST' });
}

export async function resumeAgent(agentId: string): Promise<{ status: string }> {
  return fetchJson(`/api/agents/${agentId}/resume`, { method: 'POST' });
}

// Approvals
export async function getApprovals(missionId?: string): Promise<ApprovalRequest[]> {
  const q = missionId ? `?mission_id=${missionId}` : '';
  const data = await fetchJson<{ requests: ApprovalRequest[]; count: number }>(`/api/approvals${q}`);
  return data.requests;
}
export const fetchApprovals = getApprovals;

export async function resolveApproval(
  approvalId: string,
  action: ApprovalResolutionAction,
  operator: string = 'human_operator',
  feedback?: string
): Promise<{ status: string; approval: ApprovalRequest }> {
  return fetchJson(`/api/approvals/${approvalId}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ action, operator, feedback })
  });
}

export async function cancelApproval(
  approvalId: string,
  operator: string = 'human_operator',
  reason?: string
): Promise<{ status: string; approval: ApprovalRequest }> {
  return fetchJson(`/api/approvals/${approvalId}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ operator, reason })
  });
}

// Events
export async function getSupervisorEvents(params?: {
  missionId?: string;
  eventType?: string;
  severity?: string;
  limit?: number;
  offset?: number;
}): Promise<Event[]> {
  const q = new URLSearchParams();
  if (params?.missionId) q.set('mission_id', params.missionId);
  if (params?.eventType) q.set('event_type', params.eventType);
  if (params?.severity) q.set('severity', params.severity);
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  const data = await fetchJson<{ events: Event[]; count: number }>(`/api/supervisor/events?${q.toString()}`);
  return data.events;
}

export async function getMissionEvents(missionId: string, limit: number = 100): Promise<Event[]> {
  const data = await fetchJson<{ events: Event[]; count: number }>(`/api/missions/${missionId}/events?limit=${limit}`);
  return data.events;
}

export async function getMissionTimeline(missionId: string): Promise<any[]> {
  const data = await fetchJson<{ mission_id: string; timeline: any[] }>(`/api/missions/${missionId}/timeline`);
  return data.timeline;
}

// Memory
export async function getAllMemory(params?: { missionId?: string; category?: string }): Promise<MemoryRecord[]> {
  const q = new URLSearchParams();
  if (params?.missionId) q.set('mission_id', params.missionId);
  if (params?.category) q.set('category', params.category);
  const data = await fetchJson<{ records: MemoryRecord[]; count: number }>(`/api/memory?${q.toString()}`);
  return data.records;
}
export const fetchMemory = getAllMemory;

export async function getMissionMemory(missionId: string): Promise<{
  mission_id: string;
  summary: MemorySummary;
  records: MemoryRecord[];
  count: number;
}> {
  return fetchJson(`/api/missions/${missionId}/memory`);
}

export async function addMissionMemory(
  missionId: string,
  payload: {
    fact: string;
    source: string;
    created_by?: string;
    status?: string;
    confidence?: number;
    category?: string;
    details?: string;
  }
): Promise<{ status: string; record: MemoryRecord }> {
  return fetchJson(`/api/missions/${missionId}/memory`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}
export const addMemoryRecord = addMissionMemory;
