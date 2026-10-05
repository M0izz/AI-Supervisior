import * as vscode from 'vscode';
import { Event } from '../types/models';

export interface NotificationManagerOptions {
  enabled?: boolean;
  debounceMs?: number;
  onApproveAction?: (approvalId: string) => void;
  onDenyAction?: (approvalId: string) => void;
  onOpenControlRoom?: () => void;
}

export class NotificationManager {
  private enabled: boolean;
  private debounceMs: number;
  private lastNotificationTimes = new Map<string, number>();

  private onApproveAction?: (approvalId: string) => void;
  private onDenyAction?: (approvalId: string) => void;
  private onOpenControlRoom?: () => void;

  constructor(options: NotificationManagerOptions = {}) {
    this.enabled = options.enabled ?? true;
    this.debounceMs = options.debounceMs ?? 5000;
    this.onApproveAction = options.onApproveAction;
    this.onDenyAction = options.onDenyAction;
    this.onOpenControlRoom = options.onOpenControlRoom;
  }

  public setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  public handleEvent(event: Event): void {
    if (!this.enabled) return;

    const eventType = (event.type || '').toUpperCase();
    const payload = event.payload || {};

    // 1. Approval Required
    if (eventType.includes('APPROVAL_REQUIRED') || eventType === 'APPROVAL_CREATED') {
      const approvalId = payload.approval_id || payload.id || 'unknown';
      const reason = payload.reason || payload.action_type || 'High-risk action requires operator approval';
      const debounceKey = `approval_${approvalId}`;

      if (this.shouldDebounce(debounceKey)) return;

      vscode.window
        .showWarningMessage(
          `AI Supervisor: Approval Required — ${reason}`,
          'Approve',
          'Deny',
          'Open Control Room'
        )
        .then((selection) => {
          if (selection === 'Approve' && this.onApproveAction) {
            this.onApproveAction(approvalId);
          } else if (selection === 'Deny' && this.onDenyAction) {
            this.onDenyAction(approvalId);
          } else if (selection === 'Open Control Room' && this.onOpenControlRoom) {
            this.onOpenControlRoom();
          }
        });
      return;
    }

    // 2. Supervisory Watchdog Intervention
    if (
      eventType.includes('WATCHDOG') ||
      eventType.includes('SUPERVISOR_INTERVENTION') ||
      eventType === 'ANOMALY_DETECTED'
    ) {
      const anomaly = payload.anomaly_type || payload.reason || 'Supervisory anomaly detected';
      const debounceKey = `intervention_${anomaly}`;

      if (this.shouldDebounce(debounceKey)) return;

      vscode.window
        .showErrorMessage(
          `AI Supervisor Watchdog: ${anomaly} — Intervention triggered.`,
          'Inspect in Control Room'
        )
        .then((selection) => {
          if (selection === 'Inspect in Control Room' && this.onOpenControlRoom) {
            this.onOpenControlRoom();
          }
        });
      return;
    }

    // 3. Verification Result (Failures & Rejections)
    if (eventType.includes('VERIFICATION_REJECTED') || eventType.includes('VERIFICATION_FAILED')) {
      const reason = payload.reason || payload.summary || 'Ground truth tests or safety policy rejected agent claims';
      const debounceKey = `ver_fail_${reason}`;

      if (this.shouldDebounce(debounceKey)) return;

      vscode.window.showErrorMessage(`AI Supervisor Verification REJECTED: ${reason}`);
      return;
    }

    // 4. Cross-Provider Handoff Started
    if (eventType.includes('HANDOFF_STARTED') || eventType.includes('HANDOFF_EXECUTED')) {
      const source = payload.source_agent || payload.from_agent || 'Worker';
      const target = payload.target_agent || payload.to_agent || 'Recovery Agent';
      const reason = payload.trigger || payload.reason || 'Fault recovery handoff';
      const debounceKey = `handoff_${source}_${target}`;

      if (this.shouldDebounce(debounceKey)) return;

      vscode.window.showInformationMessage(
        `AI Supervisor Handoff: ${source} → ${target} (${reason})`
      );
      return;
    }

    // 5. Mission Completed / Failed
    if (eventType === 'MISSION_COMPLETED' || eventType.includes('COMPLETED_VERIFIED')) {
      const title = payload.title || payload.mission_title || event.mission_id || 'Mission';
      const debounceKey = `msn_done_${title}`;
      if (this.shouldDebounce(debounceKey)) return;

      vscode.window.showInformationMessage(`AI Supervisor: Mission "${title}" independently verified & COMPLETED ✓`);
      return;
    }

    if (eventType === 'MISSION_FAILED') {
      const title = payload.title || payload.mission_title || event.mission_id || 'Mission';
      const reason = payload.reason || 'Critical failure';
      const debounceKey = `msn_fail_${title}`;
      if (this.shouldDebounce(debounceKey)) return;

      vscode.window.showErrorMessage(`AI Supervisor: Mission "${title}" FAILED: ${reason}`);
      return;
    }

    // 6. Absence Mode Expiration or Pause
    if (eventType.includes('ABSENCE_EXPIRED') || eventType.includes('ABSENCE_PAUSED')) {
      const reason = payload.reason || 'Ceiling reached';
      const debounceKey = `absence_${eventType}`;
      if (this.shouldDebounce(debounceKey)) return;

      vscode.window.showWarningMessage(`AI Supervisor Absence Mode: ${reason}`);
    }
  }

  private shouldDebounce(key: string): boolean {
    const now = Date.now();
    const last = this.lastNotificationTimes.get(key) || 0;
    if (now - last < this.debounceMs) {
      return true;
    }
    this.lastNotificationTimes.set(key, now);

    // Evict old entries
    if (this.lastNotificationTimes.size > 200) {
      for (const [k, timestamp] of this.lastNotificationTimes.entries()) {
        if (now - timestamp > this.debounceMs * 2) {
          this.lastNotificationTimes.delete(k);
        }
      }
    }
    return false;
  }
}
