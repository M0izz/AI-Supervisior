import {
  BackendConnectionState,
  Mission,
  Task,
  AgentRecord,
  AdapterInfo,
  ApprovalRequest,
  AbsenceSession,
  Event,
  ApprovalResolutionAction,
} from '../types/models';

export interface SupervisorClientOptions {
  apiUrl?: string;
  websocketUrl?: string;
  reconnectIntervalMs?: number;
  maxReconnectIntervalMs?: number;
}

export class SupervisorClient {
  private apiUrl: string;
  private wsUrl: string;
  private state: BackendConnectionState = 'DISCONNECTED';
  private ws: any = null;
  private reconnectTimer: any = null;
  private reconnectInterval: number;
  private maxReconnectInterval: number;
  private currentBackoff: number;
  private isExplicitlyClosed = false;

  private stateChangeListeners: ((state: BackendConnectionState) => void)[] = [];
  private eventListeners: ((event: Event) => void)[] = [];
  private seenEventIds = new Set<string>();

  constructor(options: SupervisorClientOptions = {}) {
    this.apiUrl = (options.apiUrl || 'http://127.0.0.1:8000').replace(/\/+$/, '');
    this.wsUrl = (options.websocketUrl || 'ws://127.0.0.1:8000/ws/events').replace(/\/+$/, '');
    this.reconnectInterval = options.reconnectIntervalMs || 2000;
    this.maxReconnectInterval = options.maxReconnectIntervalMs || 30000;
    this.currentBackoff = this.reconnectInterval;
  }

  public updateUrls(apiUrl: string, wsUrl: string): void {
    const apiChanged = this.apiUrl !== apiUrl.replace(/\/+$/, '');
    const wsChanged = this.wsUrl !== wsUrl.replace(/\/+$/, '');
    this.apiUrl = apiUrl.replace(/\/+$/, '');
    this.wsUrl = wsUrl.replace(/\/+$/, '');

    if (apiChanged || wsChanged) {
      if (this.state === 'CONNECTED' || this.state === 'CONNECTING') {
        this.disconnect();
        this.connect();
      }
    }
  }

  public getState(): BackendConnectionState {
    return this.state;
  }

  public onStateChange(listener: (state: BackendConnectionState) => void): () => void {
    this.stateChangeListeners.push(listener);
    listener(this.state);
    return () => {
      this.stateChangeListeners = this.stateChangeListeners.filter((l) => l !== listener);
    };
  }

  public onEvent(listener: (event: Event) => void): () => void {
    this.eventListeners.push(listener);
    return () => {
      this.eventListeners = this.eventListeners.filter((l) => l !== listener);
    };
  }

  private setState(newState: BackendConnectionState): void {
    if (this.state !== newState) {
      this.state = newState;
      for (const listener of this.stateChangeListeners) {
        try {
          listener(this.state);
        } catch (err) {
          console.error('[SupervisorClient] Error in state listener:', err);
        }
      }
    }
  }

  // --- HTTP Helpers ---
  private async fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.apiUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
      });
    } catch (err: any) {
      this.setState('DISCONNECTED');
      throw new Error(`Failed to reach Supervisor backend at ${this.apiUrl}: ${err?.message || err}`);
    }

    if (!response.ok) {
      let errorDetail = `HTTP ${response.status} ${response.statusText}`;
      try {
        const body: any = await response.json();
        if (body?.detail) {
          errorDetail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
        }
      } catch {
        // Fallback to status text
      }
      throw new Error(`Supervisor API Error (${response.status}): ${errorDetail}`);
    }

    return (await response.json()) as T;
  }

  // --- Probes & Health ---
  public async getStatus(): Promise<{ status: string; service: string; subsystems: Record<string, any> }> {
    try {
      const data = await this.fetchJson<any>('/health');
      if (this.state !== 'CONNECTED' && !this.ws) {
        this.setState('CONNECTED');
      }
      return data;
    } catch (err) {
      this.setState('DISCONNECTED');
      throw err;
    }
  }

  // --- Missions ---
  public async getMissions(): Promise<Mission[]> {
    const res = await this.fetchJson<any>('/api/missions');
    return Array.isArray(res) ? res : (res?.missions || []);
  }

  public async getMission(missionId: string): Promise<Mission> {
    return this.fetchJson<Mission>(`/api/missions/${encodeURIComponent(missionId)}`);
  }

  public async startMission(title: string, goal: string, repositoryPath?: string): Promise<Mission> {
    return this.fetchJson<Mission>('/api/missions', {
      method: 'POST',
      body: JSON.stringify({
        title,
        goal,
        repository_path: repositoryPath || '.',
      }),
    });
  }

  public async pauseMission(missionId: string, reason = 'Operator paused via VS Code'): Promise<{ status: string }> {
    return this.fetchJson(`/api/missions/${encodeURIComponent(missionId)}/pause`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  public async resumeMission(missionId: string): Promise<{ status: string }> {
    return this.fetchJson(`/api/missions/${encodeURIComponent(missionId)}/resume`, {
      method: 'POST',
    });
  }

  public async cancelMission(missionId: string, reason = 'Operator cancelled via VS Code'): Promise<{ status: string }> {
    return this.fetchJson(`/api/missions/${encodeURIComponent(missionId)}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  // --- Tasks ---
  public async getTasks(missionId: string): Promise<Task[]> {
    const res = await this.fetchJson<any>(`/api/missions/${encodeURIComponent(missionId)}/tasks`);
    return Array.isArray(res) ? res : (res?.tasks || []);
  }

  // --- Agents & Adapters ---
  public async getAgents(): Promise<AgentRecord[]> {
    const res = await this.fetchJson<any>('/api/agents');
    return Array.isArray(res) ? res : (res?.agents || []);
  }

  public async getAdapters(): Promise<AdapterInfo[]> {
    const res = await this.fetchJson<any>('/api/adapters');
    return Array.isArray(res) ? res : (res?.adapters || []);
  }

  // --- Approvals ---
  public async getApprovals(): Promise<ApprovalRequest[]> {
    const res = await this.fetchJson<any>('/api/approvals');
    return Array.isArray(res) ? res : (res?.approvals || res?.requests || []);
  }

  public async resolveApproval(
    approvalId: string,
    action: ApprovalResolutionAction,
    operator = 'vscode_operator',
    feedback?: string
  ): Promise<{ status: string; approval: ApprovalRequest }> {
    return this.fetchJson(`/api/approvals/${encodeURIComponent(approvalId)}/resolve`, {
      method: 'POST',
      body: JSON.stringify({
        action,
        operator,
        feedback,
      }),
    });
  }

  // --- Absence Mode ---
  public async getMissionAbsenceSession(missionId: string): Promise<{ active: boolean; session?: AbsenceSession; remaining_seconds?: number }> {
    return this.fetchJson(`/api/missions/${encodeURIComponent(missionId)}/absence`);
  }

  public async getActiveAbsenceSessions(): Promise<AbsenceSession[]> {
    const res = await this.fetchJson<any>('/api/absence/active');
    return Array.isArray(res) ? res : (res?.sessions || []);
  }

  public async armAbsence(missionId: string, policy?: Record<string, any>): Promise<{ status: string; session: AbsenceSession }> {
    return this.fetchJson(`/api/missions/${encodeURIComponent(missionId)}/absence/arm`, {
      method: 'POST',
      body: JSON.stringify({ policy, created_by: 'vscode_user' }),
    });
  }

  public async startAbsence(missionId: string): Promise<{ status: string; session: AbsenceSession }> {
    return this.fetchJson(`/api/missions/${encodeURIComponent(missionId)}/absence/start`, {
      method: 'POST',
    });
  }

  public async pauseAbsence(missionId: string, reason = 'Operator paused via VS Code'): Promise<{ status: string; session: AbsenceSession }> {
    return this.fetchJson(`/api/missions/${encodeURIComponent(missionId)}/absence/pause`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  public async resumeAbsence(missionId: string): Promise<{ status: string; session: AbsenceSession }> {
    return this.fetchJson(`/api/missions/${encodeURIComponent(missionId)}/absence/resume`, {
      method: 'POST',
    });
  }

  public async cancelAbsence(missionId: string, reason = 'Emergency stop triggered from VS Code'): Promise<{ status: string; session: AbsenceSession }> {
    return this.fetchJson(`/api/missions/${encodeURIComponent(missionId)}/absence/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  // --- WebSocket Connection ---
  public connect(): void {
    this.isExplicitlyClosed = false;
    this.clearReconnectTimer();

    // First do an HTTP probe to test health
    this.getStatus()
      .then(() => {
        this.openWebSocket();
      })
      .catch((err) => {
        console.warn(`[SupervisorClient] Initial health check failed: ${err.message}`);
        this.setState('DISCONNECTED');
        this.scheduleReconnect();
      });
  }

  private openWebSocket(): void {
    if (this.isExplicitlyClosed) return;
    if (this.ws) {
      try {
        this.ws.close();
      } catch {}
      this.ws = null;
    }

    this.setState('CONNECTING');

    try {
      const WebSocketClass = (globalThis as any).WebSocket;
      if (!WebSocketClass) {
        console.warn('[SupervisorClient] Global WebSocket not available in environment.');
        this.setState('CONNECTED'); // Fallback to HTTP polling mode
        return;
      }

      this.ws = new WebSocketClass(this.wsUrl);

      this.ws.onopen = () => {
        this.currentBackoff = this.reconnectInterval;
        this.setState('CONNECTED');
        console.info(`[SupervisorClient] WebSocket connected to ${this.wsUrl}`);
      };

      this.ws.onmessage = (event: any) => {
        try {
          const raw = typeof event.data === 'string' ? event.data : event.data?.toString();
          const parsed = JSON.parse(raw);
          if (parsed && typeof parsed === 'object') {
            const evId = parsed.event_id || parsed.id || `${parsed.type}_${parsed.timestamp}`;
            if (!this.seenEventIds.has(evId)) {
              this.seenEventIds.add(evId);
              // Limit seen set size
              if (this.seenEventIds.size > 2000) {
                const first = this.seenEventIds.values().next().value;
                if (first) this.seenEventIds.delete(first);
              }
              this.dispatchLiveEvent(parsed as Event);
            }
          }
        } catch (err) {
          console.warn('[SupervisorClient] Error parsing incoming WebSocket event:', err);
        }
      };

      this.ws.onerror = (err: any) => {
        console.warn('[SupervisorClient] WebSocket error:', err?.message || err);
        // Do not crash; onclose will handle reconnect
      };

      this.ws.onclose = () => {
        this.ws = null;
        if (!this.isExplicitlyClosed) {
          this.setState('DISCONNECTED');
          this.scheduleReconnect();
        }
      };
    } catch (err) {
      console.warn('[SupervisorClient] Error instantiating WebSocket:', err);
      this.setState('DISCONNECTED');
      this.scheduleReconnect();
    }
  }

  private dispatchLiveEvent(event: Event): void {
    for (const listener of this.eventListeners) {
      try {
        listener(event);
      } catch (err) {
        console.error('[SupervisorClient] Error in event listener:', err);
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.isExplicitlyClosed) return;
    this.clearReconnectTimer();

    this.reconnectTimer = setTimeout(() => {
      this.currentBackoff = Math.min(this.currentBackoff * 1.5, this.maxReconnectInterval);
      this.openWebSocket();
    }, this.currentBackoff);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  public disconnect(): void {
    this.isExplicitlyClosed = true;
    this.clearReconnectTimer();
    if (this.ws) {
      try {
        this.ws.close();
      } catch {}
      this.ws = null;
    }
    this.setState('DISCONNECTED');
  }
}
