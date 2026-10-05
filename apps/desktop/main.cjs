/**
 * AI Supervisor Desktop Shell — Main Process
 *
 * Core Principles:
 * - Desktop is a CLIENT to the Supervisor backend, not a second Supervisor.
 * - Strict Electron security baseline:
 *     contextIsolation: true
 *     nodeIntegration: false
 *     sandbox: true
 * - Two-window model:
 *     1. Control Room: Full detailed supervision window.
 *     2. Floating HUD: Compact, persistent, always-on-top status widget.
 * - Zero-Nag UX: Notifications restricted to actionable interventions/approvals.
 */

const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('path');
const fs = require('fs');

const { registerIpcHandlers } = require('./ipc.cjs');
const { NotificationManager } = require('./notifications.cjs');
const { TrayManager } = require('./tray.cjs');
const { BackendConnectionManager } = require('./connection.cjs');

class SupervisorDesktopApp {
  constructor() {
    this.controlRoomWindow = null;
    this.hudWindow = null;
    this.trayManager = null;
    this.notificationManager = null;
    this.connectionManager = null;

    this.isQuitting = false;
    this.isHudVisible = true;

    // Config
    this.apiUrl = process.env.SUPERVISOR_API_URL || 'http://127.0.0.1:8000';
    this.wsUrl = process.env.SUPERVISOR_WS_URL || 'ws://127.0.0.1:8000/ws/events';
    this.isDev = process.env.NODE_ENV === 'development' || process.argv.includes('--dev');
    this.devServerUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173';
  }

  async init() {
    // Single instance lock
    const gotLock = app.requestSingleInstanceLock();
    if (!gotLock) {
      app.quit();
      return;
    }

    app.on('second-instance', () => {
      this.showControlRoom();
    });

    // Subsystems
    this.notificationManager = new NotificationManager({ enabled: true, debounceMs: 5000 });
    this.connectionManager = new BackendConnectionManager({
      apiUrl: this.apiUrl,
      wsUrl: this.wsUrl,
      pollIntervalMs: 5000
    });
    this.trayManager = new TrayManager(this);

    // Register typed IPC
    registerIpcHandlers({ ipcMain, appManager: this });

    // Track backend connection
    this.connectionManager.onStateChange((state) => {
      this.trayManager.updateState({ backendState: state });
      this._broadcastToWindows('supervisor:on-backend-state', state);
    });

    await app.whenReady();

    this.trayManager.createTray();
    this.createControlRoomWindow();
    this.createHudWindow();
    this.connectionManager.start();

    app.on('activate', () => {
      if (!this.controlRoomWindow) {
        this.createControlRoomWindow();
      } else {
        this.controlRoomWindow.show();
      }
    });

    app.on('before-quit', () => {
      this.isQuitting = true;
      this.connectionManager.stop();
    });
  }

  getPreloadPath() {
    return path.join(__dirname, 'preload.cjs');
  }

  getRendererUrl(routeHash = '') {
    if (this.isDev) {
      return `${this.devServerUrl}/${routeHash}`;
    }
    const distPath = path.join(__dirname, '../control-room/dist/index.html');
    if (fs.existsSync(distPath)) {
      return `file://${distPath}${routeHash}`;
    }
    // Fallback to dev server
    return `${this.devServerUrl}/${routeHash}`;
  }

  createControlRoomWindow() {
    this.controlRoomWindow = new BrowserWindow({
      width: 1280,
      height: 820,
      minWidth: 1024,
      minHeight: 600,
      title: 'AI Supervisor — Control Room',
      backgroundColor: '#090c10',
      show: !process.argv.includes('--start-minimized'),
      webPreferences: {
        preload: this.getPreloadPath(),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webSecurity: true
      }
    });

    this._applySecurityGuards(this.controlRoomWindow);

    this.controlRoomWindow.loadURL(this.getRendererUrl(''));

    // Closing Control Room hides to tray rather than exiting
    this.controlRoomWindow.on('close', (event) => {
      if (!this.isQuitting) {
        event.preventDefault();
        this.controlRoomWindow.hide();
      }
    });

    this.controlRoomWindow.on('closed', () => {
      this.controlRoomWindow = null;
    });
  }

  createHudWindow() {
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;

    const hudWidth = 380;
    const hudHeight = 240;
    const margin = 20;

    this.hudWindow = new BrowserWindow({
      width: hudWidth,
      height: hudHeight,
      x: screenWidth - hudWidth - margin,
      y: screenHeight - hudHeight - margin,
      minWidth: 320,
      minHeight: 200,
      frame: false,
      transparent: false,
      resizable: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      backgroundColor: '#090d16',
      show: true,
      title: 'AI Supervisor HUD',
      webPreferences: {
        preload: this.getPreloadPath(),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webSecurity: true
      }
    });

    this._applySecurityGuards(this.hudWindow);

    this.hudWindow.loadURL(this.getRendererUrl('#hud'));

    this.hudWindow.on('closed', () => {
      this.hudWindow = null;
    });
  }

  _applySecurityGuards(win) {
    // Prevent external navigation away from application bundle
    win.webContents.on('will-navigate', (event, url) => {
      if (!url.startsWith('file://') && !url.startsWith(this.devServerUrl)) {
        event.preventDefault();
      }
    });

    // Prevent renderer from spawning arbitrary windows
    win.webContents.setWindowOpenHandler(() => {
      return { action: 'deny' };
    });
  }

  showControlRoom() {
    if (!this.controlRoomWindow) {
      this.createControlRoomWindow();
    } else {
      if (this.controlRoomWindow.isMinimized()) this.controlRoomWindow.restore();
      this.controlRoomWindow.show();
      this.controlRoomWindow.focus();
    }
  }

  hideControlRoom() {
    if (this.controlRoomWindow && !this.controlRoomWindow.isDestroyed()) {
      this.controlRoomWindow.hide();
    }
  }

  showHud() {
    if (!this.hudWindow) {
      this.createHudWindow();
    } else {
      this.hudWindow.show();
    }
    this.isHudVisible = true;
    this.trayManager.updateState({ hudVisible: true });
  }

  hideHud() {
    if (this.hudWindow && !this.hudWindow.isDestroyed()) {
      this.hudWindow.hide();
    }
    this.isHudVisible = false;
    this.trayManager.updateState({ hudVisible: false });
  }

  toggleHud() {
    if (this.isHudVisible) {
      this.hideHud();
      return false;
    } else {
      this.showHud();
      return true;
    }
  }

  minimizeToTray() {
    this.hideControlRoom();
    this.hideHud();
  }

  notify(options) {
    return this.notificationManager.notify(options);
  }

  getStatus() {
    const conn = this.connectionManager.getState();
    return {
      connected: conn.connected,
      state: conn.state,
      backendUrl: this.apiUrl,
      wsUrl: this.wsUrl,
      hudVisible: this.isHudVisible,
      controlRoomOpen: !!(this.controlRoomWindow && this.controlRoomWindow.isVisible()),
      platform: process.platform,
      version: app.getVersion ? app.getVersion() : '1.0.0'
    };
  }

  getConfig() {
    return {
      apiUrl: this.apiUrl,
      wsUrl: this.wsUrl,
      notificationsEnabled: this.notificationManager.enabled,
      hudEnabled: true
    };
  }

  quit() {
    this.isQuitting = true;
    app.quit();
  }

  _broadcastToWindows(channel, ...args) {
    if (this.controlRoomWindow && !this.controlRoomWindow.isDestroyed()) {
      this.controlRoomWindow.webContents.send(channel, ...args);
    }
    if (this.hudWindow && !this.hudWindow.isDestroyed()) {
      this.hudWindow.webContents.send(channel, ...args);
    }
  }
}

// Instantiate and launch when executed directly
if (require.main === module) {
  const desktopApp = new SupervisorDesktopApp();
  desktopApp.init().catch(err => {
    console.error('Fatal Desktop Shell startup failure:', err);
    process.exit(1);
  });
}

module.exports = {
  SupervisorDesktopApp
};
