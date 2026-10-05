import * as vscode from 'vscode';
import { SupervisorClient } from '../client/supervisorClient';
import { Mission, Task, BackendConnectionState } from '../types/models';

export class MissionTreeItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly mission?: Mission,
    public readonly task?: Task,
    public readonly isInfoNode: boolean = false
  ) {
    super(label, collapsibleState);

    if (mission && !task) {
      this.contextValue = 'missionItem';
      this.description = mission.status;
      this.tooltip = `Mission: ${mission.title}\nGoal: ${mission.goal}\nStatus: ${mission.status}`;
      this.iconPath = this.getMissionIcon(mission.status);
    } else if (task) {
      this.contextValue = 'taskItem';
      this.description = task.status;
      this.tooltip = `Task: ${task.title}\nAssigned: ${task.assigned_agent_id || 'Unassigned'}\nStatus: ${task.status}`;
      this.iconPath = this.getTaskIcon(task.status);
    }
  }

  private getMissionIcon(status: string): vscode.ThemeIcon {
    switch (status.toUpperCase()) {
      case 'RUNNING':
        return new vscode.ThemeIcon('play-circle', new vscode.ThemeColor('charts.blue'));
      case 'VERIFYING':
        return new vscode.ThemeIcon('shield', new vscode.ThemeColor('charts.yellow'));
      case 'COMPLETED':
        return new vscode.ThemeIcon('pass', new vscode.ThemeColor('charts.green'));
      case 'FAILED':
        return new vscode.ThemeIcon('error', new vscode.ThemeColor('charts.red'));
      case 'PAUSED':
        return new vscode.ThemeIcon('debug-pause', new vscode.ThemeColor('charts.orange'));
      case 'WAITING_APPROVAL':
        return new vscode.ThemeIcon('alert', new vscode.ThemeColor('charts.orange'));
      default:
        return new vscode.ThemeIcon('circle-outline');
    }
  }

  private getTaskIcon(status: string): vscode.ThemeIcon {
    switch (status.toUpperCase()) {
      case 'COMPLETED':
      case 'VERIFIED':
        return new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
      case 'IN_PROGRESS':
        return new vscode.ThemeIcon('sync~spin', new vscode.ThemeColor('charts.blue'));
      case 'FAILED':
        return new vscode.ThemeIcon('x', new vscode.ThemeColor('charts.red'));
      default:
        return new vscode.ThemeIcon('circle-small');
    }
  }
}

export class MissionsTreeProvider implements vscode.TreeDataProvider<MissionTreeItem> {
  private _onDidChangeTreeData: vscode.EventEmitter<MissionTreeItem | undefined | null | void> =
    new vscode.EventEmitter<MissionTreeItem | undefined | null | void>();
  readonly onDidChangeTreeData: vscode.Event<MissionTreeItem | undefined | null | void> =
    this._onDidChangeTreeData.event;

  private client: SupervisorClient;
  private connectionState: BackendConnectionState = 'DISCONNECTED';
  private cachedMissions: Mission[] = [];

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

  public getTreeItem(element: MissionTreeItem): vscode.TreeItem {
    return element;
  }

  public async getChildren(element?: MissionTreeItem): Promise<MissionTreeItem[]> {
    if (this.connectionState !== 'CONNECTED') {
      return [
        new MissionTreeItem(
          `Supervisor Offline (${this.connectionState}) — Click to Reconnect`,
          vscode.TreeItemCollapsibleState.None,
          undefined,
          undefined,
          true
        ),
      ];
    }

    if (!element) {
      // Root: list of missions
      try {
        const missions = await this.client.getMissions();
        this.cachedMissions = missions;

        if (missions.length === 0) {
          const emptyItem = new MissionTreeItem(
            'No active missions. Click + to start.',
            vscode.TreeItemCollapsibleState.None,
            undefined,
            undefined,
            true
          );
          emptyItem.command = {
            command: 'aiSupervisor.startMission',
            title: 'Start Mission',
          };
          return [emptyItem];
        }

        return missions.map(
          (m) =>
            new MissionTreeItem(
              m.title || m.id,
              vscode.TreeItemCollapsibleState.Collapsed,
              m
            )
        );
      } catch (err: any) {
        return [
          new MissionTreeItem(
            `Error loading missions: ${err.message}`,
            vscode.TreeItemCollapsibleState.None,
            undefined,
            undefined,
            true
          ),
        ];
      }
    }

    // Children of a mission
    if (element.mission && !element.task) {
      const items: MissionTreeItem[] = [];
      const m = element.mission;

      // Status & verification line
      const statusLabel = `Status: ${m.status}`;
      const statusItem = new MissionTreeItem(statusLabel, vscode.TreeItemCollapsibleState.None);
      statusItem.iconPath = new vscode.ThemeIcon('info');
      items.push(statusItem);

      // Active Agent
      if (m.active_agent_id) {
        const agentItem = new MissionTreeItem(
          `Active Agent: ${m.active_agent_id}`,
          vscode.TreeItemCollapsibleState.None
        );
        agentItem.iconPath = new vscode.ThemeIcon('account');
        items.push(agentItem);
      }

      // Tasks
      try {
        const tasks = await this.client.getTasks(m.id);
        for (const t of tasks) {
          items.push(
            new MissionTreeItem(
              `${t.id}: ${t.title}`,
              vscode.TreeItemCollapsibleState.None,
              m,
              t
            )
          );
        }
      } catch {
        // No task details available
      }

      return items;
    }

    return [];
  }
}
