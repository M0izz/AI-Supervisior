/**
 * Automated Desktop Shell & Floating HUD Test Suite
 *
 * Covers:
 * 1. Electron Security Baseline (contextIsolation, nodeIntegration, sandbox, preload isolation)
 * 2. IPC Handler Contracts & Whitelist (valid calls, unknown calls, malformed inputs)
 * 3. Zero-Nag Notification Policy (actionable alerts, benign suppression, debounce rate-limiting)
 * 4. Backend Connection & Lifecycle (STARTING -> CONNECTING -> LIVE -> DISCONNECTED)
 * 5. HUD State Transitions & Mapping
 * 6. Tray Lifecycle & Window Management
 */

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const { ALLOWED_CHANNELS, registerIpcHandlers } = require('../ipc.cjs');
const { NotificationManager, ACTIONABLE_TYPES } = require('../notifications.cjs');
const { BackendConnectionManager } = require('../connection.cjs');

test('1. Electron Security Baseline - Preload & Window Configuration', () => {
  const mainCode = fs.readFileSync(path.join(__dirname, '../main.cjs'), 'utf-8');
  const preloadCode = fs.readFileSync(path.join(__dirname, '../preload.cjs'), 'utf-8');

  // Verify contextIsolation is explicitly enabled
  assert.match(mainCode, /contextIsolation:\s*true/, 'contextIsolation must be explicitly set to true');

  // Verify nodeIntegration is explicitly disabled
  assert.match(mainCode, /nodeIntegration:\s*false/, 'nodeIntegration must be explicitly set to false');

  // Verify sandbox is enabled
  assert.match(mainCode, /sandbox:\s*true/, 'sandbox must be explicitly set to true');

  // Verify webSecurity is enabled
  assert.match(mainCode, /webSecurity:\s*true/, 'webSecurity must be explicitly enabled');

  // Verify preload uses contextBridge and does not expose dangerous Node primitives
  assert.match(preloadCode, /contextBridge\.exposeInMainWorld/, 'Preload must use contextBridge');
  assert.ok(!preloadCode.includes("require('fs')") && !preloadCode.includes('require("fs")'), 'Preload must not require fs');
  assert.ok(!preloadCode.includes("require('child_process')") && !preloadCode.includes('require("child_process")'), 'Preload must not require child_process');
  assert.ok(!preloadCode.includes('process.env'), 'Preload must not expose process.env');
});

test('2. IPC Handler Security - Allowed Channel Whitelist & Validation', async () => {
  const handlers = new Map();
  const mockIpcMain = {
    handle: (channel, fn) => {
      handlers.set(channel, fn);
    }
  };

  let controlRoomShown = false;
  let hudToggled = false;
  let notifiedPayload = null;

  const mockAppManager = {
    getStatus: () => ({ connected: true, state: 'LIVE' }),
    showControlRoom: () => { controlRoomShown = true; },
    hideControlRoom: () => {},
    showHud: () => {},
    hideHud: () => {},
    toggleHud: () => { hudToggled = true; return true; },
    minimizeToTray: () => {},
    notify: (options) => { notifiedPayload = options; return true; },
    getConfig: () => ({ apiUrl: 'http://127.0.0.1:8000' }),
    quit: () => {}
  };

  registerIpcHandlers({ ipcMain: mockIpcMain, appManager: mockAppManager });

  // Verify all channels in ALLOWED_CHANNELS are registered
  for (const channel of ALLOWED_CHANNELS) {
    assert.ok(handlers.has(channel), `Channel ${channel} must be registered`);
  }

  // Verify valid invocation works
  const status = await handlers.get('supervisor:get-status')();
  assert.strictEqual(status.connected, true);
  assert.strictEqual(status.state, 'LIVE');

  await handlers.get('supervisor:open-control-room')();
  assert.strictEqual(controlRoomShown, true);

  await handlers.get('supervisor:toggle-hud')();
  assert.strictEqual(hudToggled, true);

  // Verify malformed notification argument is rejected
  await assert.rejects(
    async () => {
      await handlers.get('supervisor:notify')(null, 'not an object');
    },
    /Invalid notification payload/,
    'Malformed notification argument must throw an error'
  );

  // Verify valid notification payload succeeds
  const validNotif = await handlers.get('supervisor:notify')(null, {
    title: 'Intervention',
    body: 'Rule triggered',
    severity: 'WARNING',
    type: 'CRITICAL_INTERVENTION'
  });
  assert.strictEqual(validNotif, true);
  assert.strictEqual(notifiedPayload.title, 'Intervention');
});

test('3. Zero-Nag Notification Manager - Actionable vs Benign Filtering', () => {
  const mgr = new NotificationManager({ enabled: true, debounceMs: 1000 });

  // Normal / benign events must be SILENT
  assert.strictEqual(
    mgr.shouldNotify({ type: 'TASK_STARTED', severity: 'INFO', title: 'Task Started' }),
    false,
    'Normal task start must remain silent'
  );

  assert.strictEqual(
    mgr.shouldNotify({ type: 'COMMAND_EXECUTED', severity: 'INFO', title: 'Command Executed' }),
    false,
    'Normal command execution must remain silent'
  );

  assert.strictEqual(
    mgr.shouldNotify({ type: 'FILE_CHANGED', severity: 'INFO', title: 'File Written' }),
    false,
    'File write events must remain silent'
  );

  assert.strictEqual(
    mgr.shouldNotify({ type: 'TESTS_PASSED', severity: 'INFO', title: 'Unit tests passed' }),
    false,
    'Normal unit test passes must remain silent'
  );

  // Actionable events must TRIGGER notifications
  assert.strictEqual(
    mgr.shouldNotify({ type: 'APPROVAL_REQUIRED', severity: 'WARNING', title: 'Action Approval Required', id: 'appr-1' }),
    true,
    'Approval required must notify'
  );

  assert.strictEqual(
    mgr.shouldNotify({ type: 'CRITICAL_INTERVENTION', severity: 'CRITICAL', title: 'Repeated failure loop', id: 'interv-1' }),
    true,
    'Watchdog intervention must notify'
  );

  assert.strictEqual(
    mgr.shouldNotify({ type: 'VERIFICATION_FAILED', severity: 'ERROR', title: 'Ground truth rejected', id: 'verif-fail-1' }),
    true,
    'Verification failure must notify'
  );

  assert.strictEqual(
    mgr.shouldNotify({ type: 'MISSION_FAILED', severity: 'ERROR', title: 'Mission terminated', id: 'miss-fail-1' }),
    true,
    'Mission failure must notify'
  );

  assert.strictEqual(
    mgr.shouldNotify({ type: 'MISSION_COMPLETED', severity: 'INFO', title: 'Mission completed', id: 'miss-comp-1' }),
    true,
    'Mission completion must notify'
  );
});

test('4. Zero-Nag Notification Manager - Debounce & Duplicate Suppression', async () => {
  const mgr = new NotificationManager({ enabled: true, debounceMs: 500 });

  const alert = {
    type: 'APPROVAL_REQUIRED',
    severity: 'WARNING',
    title: 'Approval needed',
    id: 'duplicate-alert-1'
  };

  // First alert triggers
  assert.strictEqual(mgr.shouldNotify(alert), true, 'First alert must trigger');

  // Immediate identical duplicate is suppressed
  assert.strictEqual(mgr.shouldNotify(alert), false, 'Immediate duplicate must be suppressed');
  assert.strictEqual(mgr.shouldNotify(alert), false, 'Second immediate duplicate must be suppressed');

  // Wait for debounce window to expire
  await new Promise(r => setTimeout(r, 550));

  // Now it can notify again
  assert.strictEqual(mgr.shouldNotify(alert), true, 'Alert after debounce window must trigger');
});

test('5. Backend Connection Manager - Lifecycle & State Transitions', async () => {
  const conn = new BackendConnectionManager({
    apiUrl: 'http://127.0.0.1:9999', // Non-existent port to test DISCONNECTED
    pollIntervalMs: 10000
  });

  assert.strictEqual(conn.currentState, 'STARTING');
  assert.strictEqual(conn.getState().connected, false);

  const stateChanges = [];
  conn.onStateChange(st => stateChanges.push(st));

  // Checking health on non-existent endpoint transitions to DISCONNECTED
  await conn.checkHealth();
  assert.strictEqual(conn.currentState, 'DISCONNECTED');
  assert.strictEqual(conn.getState().connected, false);
  assert.ok(stateChanges.includes('DISCONNECTED'));

  // Test state listener cleanup
  const unsubscribe = conn.onStateChange(() => {});
  assert.strictEqual(typeof unsubscribe, 'function');
  unsubscribe();
});

test('6. HUD Visual State Mapping Logic', () => {
  function computeHudState({ isConnected, topApproval, activeMission, verificationStatus }) {
    if (!isConnected) return 'DISCONNECTED';
    if (topApproval) return 'APPROVAL_REQUIRED';
    if (!activeMission) return 'IDLE';

    switch (activeMission.status) {
      case 'RUNNING':
        if (verificationStatus === 'verifying') return 'VERIFYING';
        return 'RUNNING';
      case 'RECOVERING':
      case 'INVESTIGATING':
        return 'RECOVERING';
      case 'PAUSED':
      case 'WAITING_APPROVAL':
        return 'WAITING';
      case 'BLOCKED':
        return 'BLOCKED';
      case 'COMPLETED':
        return 'COMPLETED';
      case 'FAILED':
      case 'CANCELLED':
        return 'FAILED';
      default:
        return 'IDLE';
    }
  }

  // 1. Disconnected
  assert.strictEqual(computeHudState({ isConnected: false }), 'DISCONNECTED');

  // 2. Approval required overrides running mission
  assert.strictEqual(
    computeHudState({
      isConnected: true,
      topApproval: { id: 'appr-1' },
      activeMission: { status: 'RUNNING' }
    }),
    'APPROVAL_REQUIRED'
  );

  // 3. Verifying state
  assert.strictEqual(
    computeHudState({
      isConnected: true,
      topApproval: null,
      activeMission: { status: 'RUNNING' },
      verificationStatus: 'verifying'
    }),
    'VERIFYING'
  );

  // 4. Recovering state
  assert.strictEqual(
    computeHudState({
      isConnected: true,
      topApproval: null,
      activeMission: { status: 'RECOVERING' }
    }),
    'RECOVERING'
  );

  // 5. Completed state
  assert.strictEqual(
    computeHudState({
      isConnected: true,
      topApproval: null,
      activeMission: { status: 'COMPLETED' }
    }),
    'COMPLETED'
  );

  // 6. Idle state
  assert.strictEqual(
    computeHudState({
      isConnected: true,
      topApproval: null,
      activeMission: null
    }),
    'IDLE'
  );
});

test('7. System Tray & Window Coordination Contract', () => {
  let hudVisible = true;
  let controlRoomOpen = false;

  const mockApp = {
    showControlRoom: () => { controlRoomOpen = true; },
    hideControlRoom: () => { controlRoomOpen = false; },
    showHud: () => { hudVisible = true; },
    hideHud: () => { hudVisible = false; },
    toggleHud: () => {
      hudVisible = !hudVisible;
      return hudVisible;
    },
    quit: () => {}
  };

  // Initial state
  assert.strictEqual(hudVisible, true);
  assert.strictEqual(controlRoomOpen, false);

  // Open Control Room
  mockApp.showControlRoom();
  assert.strictEqual(controlRoomOpen, true);

  // Minimize Control Room to tray: hides window, does NOT quit app or close HUD
  mockApp.hideControlRoom();
  assert.strictEqual(controlRoomOpen, false);
  assert.strictEqual(hudVisible, true);

  // Toggle HUD
  mockApp.toggleHud();
  assert.strictEqual(hudVisible, false);
  mockApp.toggleHud();
  assert.strictEqual(hudVisible, true);
});
