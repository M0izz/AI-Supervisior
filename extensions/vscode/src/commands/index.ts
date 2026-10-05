import * as vscode from 'vscode';
import * as path from 'path';
import { SupervisorClient } from '../client/supervisorClient';
import { PathValidator } from '../utils/pathValidator';
import { MissionsTreeProvider } from '../providers/missionsTreeProvider';
import { AgentsTreeProvider } from '../providers/agentsTreeProvider';
import { AttentionTreeProvider } from '../providers/attentionTreeProvider';
import { StatusBarManager } from '../status/statusBar';
import { MissionTreeItem } from '../providers/missionsTreeProvider';
import { AttentionTreeItem } from '../providers/attentionTreeProvider';

export function registerCommands(
  context: vscode.ExtensionContext,
  client: SupervisorClient,
  missionsProvider: MissionsTreeProvider,
  agentsProvider: AgentsTreeProvider,
  attentionProvider: AttentionTreeProvider,
  statusBar: StatusBarManager
): void {
  const getWorkspaceRoots = (): string[] => {
    return (vscode.workspace.workspaceFolders || []).map((f) => f.uri.fsPath);
  };

  const getPrimaryWorkspaceRoot = async (): Promise<string | undefined> => {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
      vscode.window.showWarningMessage('No workspace folder open. Open a repository first.');
      return undefined;
    }
    if (folders.length === 1) {
      return folders[0].uri.fsPath;
    }
    // Multi-root: ask operator to choose
    const selected = await vscode.window.showQuickPick(
      folders.map((f) => ({ label: f.name, description: f.uri.fsPath, folder: f })),
      { placeHolder: 'Select workspace folder for the mission' }
    );
    return selected?.folder.uri.fsPath;
  };

  // 1. Start Mission
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.startMission', async () => {
      if (!vscode.workspace.isTrusted) {
        vscode.window.showErrorMessage(
          'AI Supervisor: Cannot start missions in an Untrusted Workspace. Trust this workspace to proceed.'
        );
        return;
      }

      const repoPath = await getPrimaryWorkspaceRoot();
      if (!repoPath) return;

      const goal = await vscode.window.showInputBox({
        prompt: 'What engineering goal should the AI Supervisor manage & verify?',
        placeHolder: 'e.g. Fix failing authentication tests and verify zero regressions',
        validateInput: (text) => (text && text.trim().length > 3 ? null : 'Goal must be at least 4 characters'),
      });

      if (!goal) return;

      const title = goal.length > 50 ? `${goal.slice(0, 47)}...` : goal;

      try {
        vscode.window.withProgress(
          {
            location: vscode.ProgressLocation.Notification,
            title: 'AI Supervisor: Creating mission...',
            cancellable: false,
          },
          async () => {
            const mission = await client.startMission(title, goal, repoPath);
            vscode.window.showInformationMessage(`Mission started: "${mission.title}" (${mission.id})`);
            missionsProvider.refresh();
            statusBar.update();
          }
        );
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to start mission: ${err.message}`);
      }
    })
  );

  // 2. Work on Selection
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.workOnSelection', async () => {
      if (!vscode.workspace.isTrusted) {
        vscode.window.showErrorMessage('AI Supervisor: Cannot execute on selection in Untrusted Workspace.');
        return;
      }

      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage('No active editor with code selection.');
        return;
      }

      const selection = editor.selection;
      const selectedText = editor.document.getText(selection);
      if (!selectedText || selectedText.trim().length === 0) {
        vscode.window.showWarningMessage('Please select code in the active editor first.');
        return;
      }

      const filePath = editor.document.uri.fsPath;
      const roots = getWorkspaceRoots();
      if (!PathValidator.isWithinWorkspace(filePath, roots)) {
        vscode.window.showErrorMessage('Selected file is outside active workspace.');
        return;
      }

      const repoPath = await getPrimaryWorkspaceRoot();
      const relativePath = path.relative(repoPath || '.', filePath);

      const instruction = await vscode.window.showInputBox({
        prompt: `Instruction for selected code in ${relativePath} (lines ${selection.start.line + 1}-${selection.end.line + 1})`,
        placeHolder: 'e.g. Refactor this function to handle null inputs cleanly and add tests',
      });

      if (!instruction) return;

      const goal = `Work on ${relativePath} (lines ${selection.start.line + 1}-${selection.end.line + 1}): ${instruction}`;
      const title = `Selection: ${relativePath} L${selection.start.line + 1}`;

      try {
        const mission = await client.startMission(title, goal, repoPath);
        vscode.window.showInformationMessage(`Mission created from selection: "${mission.title}"`);
        missionsProvider.refresh();
        statusBar.update();
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to create mission from selection: ${err.message}`);
      }
    })
  );

  // 3. Investigate Diagnostics
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.investigateDiagnostics', async () => {
      const editor = vscode.window.activeTextEditor;
      const uri = editor?.document.uri;

      const allDiagnostics = uri ? vscode.languages.getDiagnostics(uri) : [];
      const errorOrWarn = allDiagnostics.filter(
        (d) =>
          d.severity === vscode.DiagnosticSeverity.Error ||
          d.severity === vscode.DiagnosticSeverity.Warning
      );

      if (errorOrWarn.length === 0) {
        vscode.window.showInformationMessage('Zero errors or warnings detected in the active file.');
        return;
      }

      const repoPath = await getPrimaryWorkspaceRoot();
      const relativePath = uri ? path.relative(repoPath || '.', uri.fsPath) : 'Workspace';

      const confirm = await vscode.window.showQuickPick(['Yes, launch supervisory investigation', 'Cancel'], {
        placeHolder: `Found ${errorOrWarn.length} error(s)/warning(s) in ${relativePath}. Investigate with AI Supervisor?`,
      });

      if (confirm !== 'Yes, launch supervisory investigation') return;

      const diagSummary = errorOrWarn
        .slice(0, 5)
        .map((d) => `[Line ${d.range.start.line + 1}] ${d.message}`)
        .join('; ');

      const title = `Investigate diagnostics in ${relativePath}`;
      const goal = `Diagnose, fix, and independently verify ${errorOrWarn.length} issues in ${relativePath}: ${diagSummary}`;

      try {
        const mission = await client.startMission(title, goal, repoPath);
        vscode.window.showInformationMessage(`Diagnostic investigation started: "${mission.title}"`);
        missionsProvider.refresh();
        statusBar.update();
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to launch diagnostic investigation: ${err.message}`);
      }
    })
  );

  // 4. Pause Mission
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.pauseMission', async (item?: MissionTreeItem) => {
      let missionId = item?.mission?.id;
      if (!missionId) {
        const missions = await client.getMissions();
        const active = missions.filter((m) => ['RUNNING', 'PLANNING'].includes(m.status));
        if (active.length === 0) {
          vscode.window.showInformationMessage('No running missions to pause.');
          return;
        }
        const picked = await vscode.window.showQuickPick(
          active.map((m) => ({ label: m.title, description: m.id, mission: m }))
        );
        missionId = picked?.mission.id;
      }

      if (!missionId) return;

      try {
        await client.pauseMission(missionId);
        vscode.window.showInformationMessage(`Mission ${missionId} paused.`);
        missionsProvider.refresh();
        statusBar.update();
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to pause mission: ${err.message}`);
      }
    })
  );

  // 5. Resume Mission
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.resumeMission', async (item?: MissionTreeItem) => {
      let missionId = item?.mission?.id;
      if (!missionId) {
        const missions = await client.getMissions();
        const paused = missions.filter((m) => m.status === 'PAUSED');
        if (paused.length === 0) {
          vscode.window.showInformationMessage('No paused missions to resume.');
          return;
        }
        const picked = await vscode.window.showQuickPick(
          paused.map((m) => ({ label: m.title, description: m.id, mission: m }))
        );
        missionId = picked?.mission.id;
      }

      if (!missionId) return;

      try {
        await client.resumeMission(missionId);
        vscode.window.showInformationMessage(`Mission ${missionId} resumed.`);
        missionsProvider.refresh();
        statusBar.update();
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to resume mission: ${err.message}`);
      }
    })
  );

  // 6. Cancel Mission
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.cancelMission', async (item?: MissionTreeItem) => {
      let missionId = item?.mission?.id;
      if (!missionId) {
        const missions = await client.getMissions();
        const nonDone = missions.filter((m) => !['COMPLETED', 'CANCELLED', 'FAILED'].includes(m.status));
        if (nonDone.length === 0) {
          vscode.window.showInformationMessage('No active missions to cancel.');
          return;
        }
        const picked = await vscode.window.showQuickPick(
          nonDone.map((m) => ({ label: m.title, description: m.id, mission: m }))
        );
        missionId = picked?.mission.id;
      }

      if (!missionId) return;

      const confirm = await vscode.window.showWarningMessage(
        `Are you sure you want to cancel mission ${missionId}?`,
        { modal: true },
        'Yes, Cancel Mission'
      );

      if (confirm !== 'Yes, Cancel Mission') return;

      try {
        await client.cancelMission(missionId);
        vscode.window.showInformationMessage(`Mission ${missionId} cancelled.`);
        missionsProvider.refresh();
        statusBar.update();
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to cancel mission: ${err.message}`);
      }
    })
  );

  // 7. Refresh
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.refresh', async () => {
      missionsProvider.refresh();
      agentsProvider.refresh();
      attentionProvider.refresh();
      await statusBar.update();
      vscode.window.showInformationMessage('AI Supervisor state refreshed.');
    })
  );

  // 8. Open Control Room
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.openControlRoom', async () => {
      const config = vscode.workspace.getConfiguration('aiSupervisor');
      const url = config.get<string>('controlRoomUrl') || 'http://localhost:5173';
      try {
        await vscode.env.openExternal(vscode.Uri.parse(url));
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to open Control Room at ${url}: ${err.message}`);
      }
    })
  );

  // 9. Open Floating HUD
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.openHud', async () => {
      vscode.window.showInformationMessage(
        'AI Supervisor Desktop Floating HUD is running in background. Use system tray or taskbar to toggle visibility.'
      );
    })
  );

  // 10. Approve Action
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.approveRequest', async (approvalIdOrItem?: string | AttentionTreeItem) => {
      const approvalId = typeof approvalIdOrItem === 'string'
        ? approvalIdOrItem
        : approvalIdOrItem?.approval?.id;

      if (!approvalId) {
        vscode.window.showWarningMessage('No approval selected.');
        return;
      }

      try {
        await client.resolveApproval(approvalId, 'APPROVE_ONCE', 'vscode_user');
        vscode.window.showInformationMessage(`Action APPROVED for request ${approvalId}`);
        attentionProvider.refresh();
        statusBar.update();
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to approve request: ${err.message}`);
      }
    })
  );

  // 11. Deny Action
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.denyRequest', async (approvalIdOrItem?: string | AttentionTreeItem) => {
      const approvalId = typeof approvalIdOrItem === 'string'
        ? approvalIdOrItem
        : approvalIdOrItem?.approval?.id;

      if (!approvalId) {
        vscode.window.showWarningMessage('No approval selected.');
        return;
      }

      const feedback = await vscode.window.showInputBox({
        prompt: 'Reason for denial (optional guidance for agent recovery):',
        placeHolder: 'e.g. Migration must not drop existing users table',
      });

      try {
        await client.resolveApproval(approvalId, 'DENY', 'vscode_user', feedback);
        vscode.window.showWarningMessage(`Action DENIED for request ${approvalId}`);
        attentionProvider.refresh();
        statusBar.update();
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to deny request: ${err.message}`);
      }
    })
  );

  // 12. Arm Absence Mode
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.armAbsence', async () => {
      const missions = await client.getMissions();
      const active = missions.filter((m) => ['RUNNING', 'PLANNING'].includes(m.status));
      if (active.length === 0) {
        vscode.window.showWarningMessage('No active running missions to arm Absence Mode for.');
        return;
      }

      const picked = await vscode.window.showQuickPick(
        active.map((m) => ({ label: m.title, description: m.id, mission: m }))
      );
      if (!picked) return;

      try {
        const res = await client.armAbsence(picked.mission.id);
        vscode.window.showInformationMessage(`Absence Mode armed for mission: ${picked.mission.title}`);
        attentionProvider.refresh();
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to arm Absence Mode: ${err.message}`);
      }
    })
  );

  // 13. Cancel Absence Mode (Emergency Stop)
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.cancelAbsence', async () => {
      const sessions = await client.getActiveAbsenceSessions();
      if (sessions.length === 0) {
        vscode.window.showInformationMessage('No active Absence Mode sessions.');
        return;
      }

      const picked = await vscode.window.showQuickPick(
        sessions.map((s) => ({ label: `Mission: ${s.mission_id}`, description: s.absence_id, session: s }))
      );
      if (!picked) return;

      try {
        await client.cancelAbsence(picked.session.mission_id, 'Emergency Stop triggered via VS Code');
        vscode.window.showWarningMessage(`Absence Mode cancelled for mission ${picked.session.mission_id}`);
        attentionProvider.refresh();
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to cancel Absence Mode: ${err.message}`);
      }
    })
  );

  // 14. Open File Safely
  context.subscriptions.push(
    vscode.commands.registerCommand('aiSupervisor.openFile', async (filePath: string, line?: number) => {
      const roots = getWorkspaceRoots();
      if (!PathValidator.isWithinWorkspace(filePath, roots)) {
        vscode.window.showErrorMessage(`Security: File '${filePath}' is outside workspace roots.`);
        return;
      }

      try {
        const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(filePath));
        const editor = await vscode.window.showTextDocument(doc);
        if (line && line > 0) {
          const pos = new vscode.Position(line - 1, 0);
          editor.selection = new vscode.Selection(pos, pos);
          editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenter);
        }
      } catch (err: any) {
        vscode.window.showErrorMessage(`Failed to open file '${filePath}': ${err.message}`);
      }
    })
  );
}
