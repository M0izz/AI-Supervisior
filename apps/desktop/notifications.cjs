/**
 * Zero-Nag Notification Manager
 *
 * Enforces strict developer ergonomics:
 * - Silent for normal operational events (commands, tests passing, file edits)
 * - Surfaces only actionable / critical events:
 *   - APPROVAL_REQUIRED
 *   - CRITICAL_INTERVENTION
 *   - VERIFICATION_FAILED
 *   - MISSION_FAILED
 *   - MISSION_COMPLETED
 * - Debounces / rate-limits duplicate alerts within a 5-second sliding window
 */

let Notification;
try {
  Notification = require('electron').Notification;
} catch {
  // Headless / test runner environment
}

const ACTIONABLE_TYPES = new Set([
  'APPROVAL_REQUIRED',
  'APPROVAL_REQUESTED',
  'CRITICAL_INTERVENTION',
  'WATCHDOG_INTERVENTION',
  'VERIFICATION_FAILED',
  'VERIFICATION_REJECTED',
  'MISSION_FAILED',
  'MISSION_COMPLETED'
]);

class NotificationManager {
  constructor(options = {}) {
    this.enabled = options.enabled !== false;
    this.debounceMs = options.debounceMs || 5000;
    this.recentAlerts = new Map(); // key -> timestamp
  }

  isActionable(type, severity) {
    if (!type) return severity === 'CRITICAL' || severity === 'ERROR';
    return ACTIONABLE_TYPES.has(type) || severity === 'CRITICAL';
  }

  shouldNotify(options) {
    if (!this.enabled) return false;
    const { type, severity, id, title } = options;

    if (!this.isActionable(type, severity)) {
      return false; // Silent for benign events
    }

    const key = id || `${type}:${title}`;
    const now = Date.now();
    const lastNotified = this.recentAlerts.get(key);

    if (lastNotified && now - lastNotified < this.debounceMs) {
      return false; // Suppress duplicate burst
    }

    this.recentAlerts.set(key, now);
    this._prune(now);
    return true;
  }

  notify(options) {
    if (!this.shouldNotify(options)) {
      return false;
    }

    if (Notification && Notification.isSupported && Notification.isSupported()) {
      try {
        const notif = new Notification({
          title: options.title || 'AI Supervisor',
          body: options.body || '',
          urgency: options.severity === 'CRITICAL' ? 'critical' : 'normal',
          silent: false
        });
        notif.show();
        return true;
      } catch (err) {
        console.error('Failed to display native notification:', err);
      }
    }
    return false;
  }

  _prune(now) {
    for (const [k, ts] of this.recentAlerts.entries()) {
      if (now - ts > this.debounceMs * 2) {
        this.recentAlerts.delete(k);
      }
    }
  }
}

module.exports = {
  NotificationManager,
  ACTIONABLE_TYPES
};
