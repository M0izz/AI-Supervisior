/**
 * AI Supervisor Desktop Preload Bridge
 *
 * Enforces strict security boundaries:
 * - contextIsolation: true
 * - nodeIntegration: false
 * - No Node internals exposed (no fs, no child_process, no process, no os)
 * - Exposes only a narrow, typed window.supervisor API via contextBridge
 */

const { contextBridge, ipcRenderer } = require('electron');

const supervisorBridge = {
  getStatus: () => ipcRenderer.invoke('supervisor:get-status'),
  openControlRoom: () => ipcRenderer.invoke('supervisor:open-control-room'),
  hideControlRoom: () => ipcRenderer.invoke('supervisor:hide-control-room'),
  showHud: () => ipcRenderer.invoke('supervisor:show-hud'),
  hideHud: () => ipcRenderer.invoke('supervisor:hide-hud'),
  toggleHud: () => ipcRenderer.invoke('supervisor:toggle-hud'),
  minimizeToTray: () => ipcRenderer.invoke('supervisor:minimize-to-tray'),
  notify: (options) => ipcRenderer.invoke('supervisor:notify', options),
  getConfig: () => ipcRenderer.invoke('supervisor:get-config'),
  quit: () => ipcRenderer.invoke('supervisor:quit'),
  
  onHudToggle: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const subscription = () => callback();
    ipcRenderer.on('supervisor:on-hud-toggle', subscription);
    return () => {
      ipcRenderer.removeListener('supervisor:on-hud-toggle', subscription);
    };
  },

  onBackendStateChange: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const subscription = (_event, state) => callback(state);
    ipcRenderer.on('supervisor:on-backend-state', subscription);
    return () => {
      ipcRenderer.removeListener('supervisor:on-backend-state', subscription);
    };
  }
};

contextBridge.exposeInMainWorld('supervisor', supervisorBridge);
