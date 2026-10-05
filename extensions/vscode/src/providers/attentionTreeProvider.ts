import * as vscode from 'vscode';
import { SupervisorClient } from '../client/supervisorClient';
import { ApprovalRequest, AbsenceSession, BackendConnectionState } from '../types/models';

export class AttentionTreeItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly approval?: ApprovalRequest,
    public readonly absence?: AbsenceSession,
    public readonly isInfoNode: boolean = false
  ) {
    super(label, collapsibleState);

    if (approval) {
      this.contextValue = 'approvalItem';
      this.description = `[${approval.risk_level.toUpperCase()}] ${approval.action_type}`;
      this.tooltip = `Agent: ${approval.agent_id}\nAction: ${approval.action_type}\nTarget: ${approval.target}\nReason: ${approval.reason}\nStatus: ${approval.status}`;
      this.iconPath = new vscode.ThemeIcon('alert', new vscode.ThemeColor('charts.orange'));
    } else if (absence) {
      this.contextValue = 'absenceItem';
      const remainingMin = absence.remaining_seconds ? Math.max(0, Math.floor(absence.remaining_seconds / 60)) : 0;
      this.description = `${absence.status} (${remainingMin}m remaining)`;
      this.tooltip = `Absence Mode: ${absence.status}\nExpires in: ${remainingMin} minutes\nRetries: ${absence.policy?.max_retries}`;
      this.iconPath = new vscode.ThemeIcon('watch', new vscode.ThemeColor('charts.blue'));
    }
  }
}

export class AttentionTreeProvider implements vscode.TreeDataProvider<AttentionTreeItem> {
  private _onDidChangeTreeData: vscode.EventEmitter<AttentionTreeItem | undefined | null | void> =
    new vscode.EventEmitter<AttentionTreeItem | undefined | null | void>();
  readonly onDidChangeTreeData: vscode.Event<AttentionTreeItem | undefined | null | void> =
    this._onDidChangeTreeData.event;

  private client: SupervisorClient;
  private connectionState: BackendConnectionState = 'DISCONNECTED';

  constructor(client: SupervisorClient) {
    this.client = client;
    this.client.onStateChange((state) => {
      this.connectionState = state;
      this.refresh();
    });
  }

  public refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  public getTreeItem(element: AttentionTreeItem): vscode.TreeItem {
    return element;
  }

  public async getChildren(element?: AttentionTreeItem): Promise<AttentionTreeItem[]> {
    if (this.connectionState !== 'CONNECTED') {
      return [
        new AttentionTreeItem(
          `Supervisor Offline (${this.connectionState})`,
          vscode.TreeItemCollapsibleState.None,
          undefined,
          undefined,
          true
        ),
      ];
    }

    if (!element) {
      const items: AttentionTreeItem[] = [];

      // 1. Pending Approvals
      try {
        const approvals = await this.client.getApprovals();
        const pending = approvals.filter((a) => a.status === 'PENDING');
        for (const app of pending) {
          items.push(
            new AttentionTreeItem(
              `Approval: ${app.target}`,
              vscode.TreeItemCollapsibleState.Collapsed,
              app
            )
          );
        }
      } catch {
        // Approvals query failed
      }

      // 2. Active Absence Sessions
      try {
        const absenceSessions = await this.client.getActiveAbsenceSessions();
        for (const sess of absenceSessions) {
          items.push(
            new AttentionTreeItem(
              `Absence Mode: Mission ${sess.mission_id}`,
              vscode.TreeItemCollapsibleState.None,
              undefined,
              sess
            )
          );
        }
      } catch {
        // Absence query failed
      }

      if (items.length === 0) {
        const clearItem = new AttentionTreeItem(
          'Zero attention items. All operations nominal.',
          vscode.TreeItemCollapsibleState.None,
          undefined,
          undefined,
          true
        );
        clearItem.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
        return [clearItem];
      }

      return items;
    }

    // Children of an approval item
    if (element.approval) {
      const app = element.approval;
      const details: AttentionTreeItem[] = [];

      const reasonItem = new AttentionTreeItem(`Reason: ${app.reason}`, vscode.TreeItemCollapsibleState.None);
      reasonItem.iconPath = new vscode.ThemeIcon('comment');
      details.push(reasonItem);

      const agentItem = new AttentionTreeItem(`Agent: ${app.agent_id}`, vscode.TreeItemCollapsibleState.None);
      agentItem.iconPath = new vscode.ThemeIcon('account');
      details.push(agentItem);

      const approveAction = new AttentionTreeItem('Approve Action', vscode.TreeItemCollapsibleState.None);
      approveAction.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
      approveAction.command = {
        command: 'aiSupervisor.approveRequest',
        title: 'Approve Action',
        arguments: [app.id],
      };
      details.push(approveAction);

      const denyAction = new AttentionTreeItem('Deny Action', vscode.TreeItemCollapsibleState.None);
      denyAction.iconPath = new vscode.ThemeIcon('x', new vscode.ThemeColor('charts.red'));
      denyAction.command = {
        command: 'aiSupervisor.denyRequest',
        title: 'Deny Action',
        arguments: [app.id],
      };
      details.push(denyAction);

      return details;
    }

    return [];
  }
}
