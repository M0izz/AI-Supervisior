/**
 * Desktop IPC Registration & Security Gate
 *
 * Implements strict, typed IPC contracts.
 * Rejects unknown channels and validates message shapes.
 */

const ALLOWED_CHANNELS = new Set([
  'supervisor:get-status',
  'supervisor:open-control-room',
  'supervisor:hide-control-room',
  'supervisor:show-hud',
  'supervisor:hide-hud',
  'supervisor:toggle-hud',
  'supervisor:minimize-to-tray',
  'supervisor:notify',
  'supervisor:get-config',
  'supervisor:quit'
]);

function registerIpcHandlers({ ipcMain, appManager }) {
  if (!ipcMain) return;

  ipcMain.handle('supervisor:get-status', async () => {
    return appManager.getStatus();
  });

  ipcMain.handle('supervisor:open-control-room', async () => {
    appManager.showControlRoom();
    return true;
  });

  ipcMain.handle('supervisor:hide-control-room', async () => {
    appManager.hideControlRoom();
    return true;
  });

  ipcMain.handle('supervisor:show-hud', async () => {
    appManager.showHud();
    return true;
  });

  ipcMain.handle('supervisor:hide-hud', async () => {
    appManager.hideHud();
    return true;
  });

  ipcMain.handle('supervisor:toggle-hud', async () => {
    return appManager.toggleHud();
  });

  ipcMain.handle('supervisor:minimize-to-tray', async () => {
    appManager.minimizeToTray();
    return true;
  });

  ipcMain.handle('supervisor:notify', async (_event, options) => {
    if (!options || typeof options !== 'object') {
      throw new Error('Invalid notification payload: must be an object');
    }
    return appManager.notify(options);
  });

  ipcMain.handle('supervisor:get-config', async () => {
    return appManager.getConfig();
  });

  ipcMain.handle('supervisor:quit', async () => {
    appManager.quit();
  });
}

module.exports = {
  registerIpcHandlers,
  ALLOWED_CHANNELS
};
