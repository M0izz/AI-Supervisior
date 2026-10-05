/**
 * Supervisor Backend Connection Manager
 *
 * Tracks the authoritative local FastAPI backend lifecycle:
 * STARTING -> CONNECTING -> LIVE -> DEGRADED -> DISCONNECTED
 *
 * Never presents mock data when backend is down.
 */

const http = require('http');

class BackendConnectionManager {
  constructor(options = {}) {
    this.apiUrl = options.apiUrl || process.env.SUPERVISOR_API_URL || 'http://127.0.0.1:8000';
    this.wsUrl = options.wsUrl || process.env.SUPERVISOR_WS_URL || 'ws://127.0.0.1:8000/ws/events';
    this.pollIntervalMs = options.pollIntervalMs || 5000;
    this.currentState = 'STARTING';
    this.listeners = new Set();
    this.timer = null;
    this.lastHealthData = null;
  }

  start() {
    this.checkHealth();
    this.timer = setInterval(() => this.checkHealth(), this.pollIntervalMs);
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  onStateChange(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  getState() {
    return {
      state: this.currentState,
      connected: this.currentState === 'LIVE',
      apiUrl: this.apiUrl,
      wsUrl: this.wsUrl,
      health: this.lastHealthData
    };
  }

  checkHealth() {
    return new Promise((resolve) => {
      try {
        const url = new URL('/health', this.apiUrl);
        const req = http.get(url, { timeout: 3000 }, (res) => {
          let body = '';
          res.on('data', chunk => body += chunk);
          res.on('end', () => {
            if (res.statusCode === 200) {
              try {
                this.lastHealthData = JSON.parse(body);
                this._setState('LIVE');
                resolve(true);
              } catch {
                this._setState('DEGRADED');
                resolve(false);
              }
            } else {
              this._setState('DEGRADED');
              resolve(false);
            }
          });
        });

        req.on('error', () => {
          this._setState('DISCONNECTED');
          resolve(false);
        });

        req.on('timeout', () => {
          req.destroy();
          this._setState('DISCONNECTED');
          resolve(false);
        });
      } catch {
        this._setState('DISCONNECTED');
        resolve(false);
      }
    });
  }

  _setState(newState) {
    if (this.currentState !== newState) {
      this.currentState = newState;
      for (const listener of this.listeners) {
        try {
          listener(newState);
        } catch (err) {
          console.error('Connection state listener error:', err);
        }
      }
    }
  }
}

module.exports = {
  BackendConnectionManager
};
