import * as vscode from 'vscode';
import { SupervisorClient } from '../client/supervisorClient';
import { BackendConnectionState } from '../types/models';

export class StatusBarManager implements vscode.Disposable {
  private statusBarItem: vscode.StatusBarItem;
  private client: SupervisorClient;
  private isEnabled: boolean;

  constructor(client: SupervisorClient, enabled: boolean = true) {
    this.client = client;
    this.isEnabled = enabled;

    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.statusBarItem.command = 'workbench.view.extension.ai-supervisor';

    this.client.onStateChange((state) => {
      this.update(state);
    });

    if (this.isEnabled) {
      this.statusBarItem.show();
    }
  }

  public setEnabled(enabled: boolean): void {
    this.isEnabled = enabled;
    if (enabled) {
      this.statusBarItem.show();
    } else {
      this.statusBarItem.hide();
    }
  }

  public async update(state?: BackendConnectionState): Promise<void> {
    const currentState = state || this.client.getState();

    if (currentState !== 'CONNECTED') {
      this.statusBarItem.text = `$(circle-slash) Supervisor: Offline`;
      this.statusBarItem.tooltip = `AI Supervisor backend is ${currentState.toLowerCase()}. Click to open view.`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
      return;
    }

    try {
      // Query summary state
      const [missions, approvals] = await Promise.all([
        this.client.getMissions().catch(() => []),
        this.client.getApprovals().catch(() => []),
      ]);

      const pendingApprovals = approvals.filter((a) => a.status === 'PENDING');
      const activeMissions = missions.filter((m) =>
        ['RUNNING', 'PLANNING', 'RECOVERING', 'VERIFYING', 'WAITING_APPROVAL'].includes(m.status)
      );

      if (pendingApprovals.length > 0) {
        this.statusBarItem.text = `$(warning) Supervisor: ${pendingApprovals.length} Attention`;
        this.statusBarItem.tooltip = `AI Supervisor: ${pendingApprovals.length} pending approval(s) requiring human action.`;
        this.statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
      } else if (activeMissions.length > 0) {
        this.statusBarItem.text = `$(shield) Supervisor: ${activeMissions.length} Active`;
        this.statusBarItem.tooltip = `AI Supervisor: ${activeMissions.length} active mission(s) running under supervision.`;
        this.statusBarItem.backgroundColor = undefined;
      } else {
        this.statusBarItem.text = `$(shield) Supervisor: Idle`;
        this.statusBarItem.tooltip = `AI Supervisor connected and nominal. Zero active missions.`;
        this.statusBarItem.backgroundColor = undefined;
      }
    } catch {
      this.statusBarItem.text = `$(shield) Supervisor: Live`;
      this.statusBarItem.tooltip = `AI Supervisor connected.`;
      this.statusBarItem.backgroundColor = undefined;
    }
  }

  public dispose(): void {
    this.statusBarItem.dispose();
  }
}
