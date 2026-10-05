import * as vscode from 'vscode';
import { SupervisorClient } from '../client/supervisorClient';
import { AdapterInfo, AgentRecord, BackendConnectionState } from '../types/models';

export class AgentTreeItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly adapter?: AdapterInfo,
    public readonly agent?: AgentRecord,
    public readonly isInfoNode: boolean = false
  ) {
    super(label, collapsibleState);

    if (adapter) {
      this.contextValue = 'adapterItem';
      const isAvail = adapter.availability?.available ?? false;
      const statusText = adapter.availability?.status || (isAvail ? 'AVAILABLE' : 'UNAVAILABLE');
      this.description = statusText;
      this.tooltip = `Provider: ${adapter.provider} (${adapter.adapter_id})\nStatus: ${statusText}\nCapabilities: ${adapter.capabilities.join(', ')}\n${adapter.availability?.message || ''}`;

      if (isAvail) {
        this.iconPath = new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor('charts.green'));
      } else if (statusText.includes('CONFIG')) {
        this.iconPath = new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor('charts.yellow'));
      } else {
        this.iconPath = new vscode.ThemeIcon('circle-slash', new vscode.ThemeColor('charts.red'));
      }
    } else if (agent) {
      this.contextValue = 'agentRecordItem';
      this.description = agent.status;
      this.tooltip = `Agent: ${agent.agent_id} (${agent.agent_type})\nStatus: ${agent.status}\nModel: ${agent.model}\nTask: ${agent.task_id || 'None'}`;
      this.iconPath = new vscode.ThemeIcon('robot');
    }
  }
}

export class AgentsTreeProvider implements vscode.TreeDataProvider<AgentTreeItem> {
  private _onDidChangeTreeData: vscode.EventEmitter<AgentTreeItem | undefined | null | void> =
    new vscode.EventEmitter<AgentTreeItem | undefined | null | void>();
  readonly onDidChangeTreeData: vscode.Event<AgentTreeItem | undefined | null | void> =
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

  public getTreeItem(element: AgentTreeItem): vscode.TreeItem {
    return element;
  }

  public async getChildren(element?: AgentTreeItem): Promise<AgentTreeItem[]> {
    if (this.connectionState !== 'CONNECTED') {
      return [
        new AgentTreeItem(
          `Supervisor Offline (${this.connectionState})`,
          vscode.TreeItemCollapsibleState.None,
          undefined,
          undefined,
          true
        ),
      ];
    }

    if (!element) {
      try {
        const adapters = await this.client.getAdapters();
        if (adapters.length === 0) {
          // Fallback to active agent registry list
          const agents = await this.client.getAgents();
          if (agents.length === 0) {
            return [
              new AgentTreeItem(
                'No registered providers found',
                vscode.TreeItemCollapsibleState.None,
                undefined,
                undefined,
                true
              ),
            ];
          }
          return agents.map(
            (a) =>
              new AgentTreeItem(
                `${a.agent_id} (${a.agent_type})`,
                vscode.TreeItemCollapsibleState.None,
                undefined,
                a
              )
          );
        }

        return adapters.map(
          (ad) =>
            new AgentTreeItem(
              ad.display_name || ad.adapter_id,
              vscode.TreeItemCollapsibleState.Collapsed,
              ad
            )
        );
      } catch (err: any) {
        return [
          new AgentTreeItem(
            `Error loading fleet: ${err.message}`,
            vscode.TreeItemCollapsibleState.None,
            undefined,
            undefined,
            true
          ),
        ];
      }
    }

    // Children of an adapter: capability list & executable path
    if (element.adapter) {
      const items: AgentTreeItem[] = [];
      const ad = element.adapter;

      const providerItem = new AgentTreeItem(
        `Provider: ${ad.provider} (v${ad.version})`,
        vscode.TreeItemCollapsibleState.None
      );
      providerItem.iconPath = new vscode.ThemeIcon('server');
      items.push(providerItem);

      if (ad.availability?.executable_path) {
        const pathItem = new AgentTreeItem(
          `Binary: ${ad.availability.executable_path}`,
          vscode.TreeItemCollapsibleState.None
        );
        pathItem.iconPath = new vscode.ThemeIcon('file-binary');
        items.push(pathItem);
      }

      for (const cap of ad.capabilities) {
        const capItem = new AgentTreeItem(
          `cap: ${cap}`,
          vscode.TreeItemCollapsibleState.None
        );
        capItem.iconPath = new vscode.ThemeIcon('gear');
        items.push(capItem);
      }

      return items;
    }

    return [];
  }
}
