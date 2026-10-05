/**
 * AI Supervisor System Tray Manager
 *
 * Provides persistent background presence:
 * - Dynamic status indicator (LIVE / DISCONNECTED)
 * - Single-click toggles HUD
 * - Double-click opens Control Room
 * - Context menu with quick supervisory controls
 */

let Tray, Menu, nativeImage;
try {
  const electron = require('electron');
  Tray = electron.Tray;
  Menu = electron.Menu;
  nativeImage = electron.nativeImage;
} catch {
  // Headless / test runner environment
}
const path = require('path');
const fs = require('fs');

class TrayManager {
  constructor(appManager) {
    this.appManager = appManager;
    this.tray = null;
    this.isHudVisible = true;
    this.backendState = 'STARTING';
  }

  createTray() {
    const icon = this._createTrayIcon();
    this.tray = new Tray(icon);
    this.tray.setToolTip('AI Supervisor — Control Plane');

    this.tray.on('click', () => {
      this.appManager.toggleHud();
    });

    this.tray.on('double-click', () => {
      this.appManager.showControlRoom();
    });

    this.updateMenu();
    return this.tray;
  }

  updateState({ hudVisible, backendState }) {
    if (typeof hudVisible === 'boolean') this.isHudVisible = hudVisible;
    if (backendState) this.backendState = backendState;
    this.updateMenu();
  }

  updateMenu() {
    if (!this.tray) return;

    const statusLabel = this.backendState === 'LIVE' 
      ? '● AI Supervisor: LIVE' 
      : `○ AI Supervisor: ${this.backendState}`;

    const contextMenu = Menu.buildFromTemplate([
      {
        label: statusLabel,
        enabled: false
      },
      { type: 'separator' },
      {
        label: this.isHudVisible ? 'Hide Floating HUD' : 'Show Floating HUD',
        click: () => this.appManager.toggleHud()
      },
      {
        label: 'Open Control Room',
        click: () => this.appManager.showControlRoom()
      },
      { type: 'separator' },
      {
        label: 'Quit AI Supervisor',
        click: () => this.appManager.quit()
      }
    ]);

    this.tray.setContextMenu(contextMenu);
  }

  destroy() {
    if (this.tray) {
      this.tray.destroy();
      this.tray = null;
    }
  }

  _createTrayIcon() {
    // 16x16 standard 1-bit or RGBA icon fallback (dark square with cyan dot)
    // 16x16 PNG Base64 data url for tray icon
    const base64Png = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAMUlEQVQ4T2NkYGD4z0ABYBw1gGE0DBhG0wBG08B4aWCUBoZGwyD7j171jE0eowYQbgAALJ0F9Qv9rCcAAAAASUVORK5CYII=';
    const buffer = Buffer.from(base64Png, 'base64');
    return nativeImage.createFromBuffer(buffer);
  }
}

module.exports = {
  TrayManager
};
