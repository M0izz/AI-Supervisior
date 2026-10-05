import * as vscode from 'vscode';
import { SupervisorClient } from './client/supervisorClient';
import { MissionsTreeProvider } from './providers/missionsTreeProvider';
import { AgentsTreeProvider } from './providers/agentsTreeProvider';
import { AttentionTreeProvider } from './providers/attentionTreeProvider';
import { StatusBarManager } from './status/statusBar';
import { NotificationManager } from './notifications/notificationManager';
import { registerCommands } from './commands';

let client: SupervisorClient | undefined;
let statusBar: StatusBarManager | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration('aiSupervisor');
  const apiUrl = config.get<string>('apiUrl') || 'http://127.0.0.1:8000';
  const wsUrl = config.get<string>('websocketUrl') || 'ws://127.0.0.1:8000/ws/events';
  const autoConnect = config.get<boolean>('autoConnect') ?? true;
  const showNotifications = config.get<boolean>('showNotifications') ?? true;
  const showStatusBar = config.get<boolean>('showStatusBar') ?? true;

  // 1. Initialize Authoritative Supervisor Client
  client = new SupervisorClient({
    apiUrl,
    websocketUrl: wsUrl,
  });

  // 2. Initialize Tree View Providers
  const missionsProvider = new MissionsTreeProvider(client);
  const agentsProvider = new AgentsTreeProvider(client);
  const attentionProvider = new AttentionTreeProvider(client);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('aiSupervisor.missionsView', missionsProvider),
    vscode.window.registerTreeDataProvider('aiSupervisor.agentsView', agentsProvider),
    vscode.window.registerTreeDataProvider('aiSupervisor.attentionView', attentionProvider)
  );

  // 3. Initialize Status Bar
  statusBar = new StatusBarManager(client, showStatusBar);
  context.subscriptions.push(statusBar);

  // 4. Initialize Zero-Nag Notification Manager
  const notificationManager = new NotificationManager({
    enabled: showNotifications,
    debounceMs: 5000,
    onApproveAction: (approvalId) => {
      vscode.commands.executeCommand('aiSupervisor.approveRequest', approvalId);
    },
    onDenyAction: (approvalId) => {
      vscode.commands.executeCommand('aiSupervisor.denyRequest', approvalId);
    },
    onOpenControlRoom: () => {
      vscode.commands.executeCommand('aiSupervisor.openControlRoom');
    },
  });

  // Connect live event stream to notifications & tree refresh
  client.onEvent((event) => {
    notificationManager.handleEvent(event);
    missionsProvider.refresh();
    attentionProvider.refresh();
    statusBar?.update();
  });

  // 5. Register VS Code Commands
  registerCommands(
    context,
    client,
    missionsProvider,
    agentsProvider,
    attentionProvider,
    statusBar
  );

  // 6. Listen for Configuration Changes
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('aiSupervisor')) {
        const newConfig = vscode.workspace.getConfiguration('aiSupervisor');
        const newApiUrl = newConfig.get<string>('apiUrl') || 'http://127.0.0.1:8000';
        const newWsUrl = newConfig.get<string>('websocketUrl') || 'ws://127.0.0.1:8000/ws/events';
        const newShowNotifs = newConfig.get<boolean>('showNotifications') ?? true;
        const newShowStatus = newConfig.get<boolean>('showStatusBar') ?? true;

        client?.updateUrls(newApiUrl, newWsUrl);
        notificationManager.setEnabled(newShowNotifs);
        statusBar?.setEnabled(newShowStatus);
        statusBar?.update();
      }
    })
  );

  // 7. Auto-connect if enabled
  if (autoConnect) {
    client.connect();
  }

  console.info('AI Supervisor VS Code extension successfully activated.');
}

export function deactivate(): void {
  if (client) {
    client.disconnect();
    client = undefined;
  }
  if (statusBar) {
    statusBar.dispose();
    statusBar = undefined;
  }
}
