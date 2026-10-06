import { useEffect, useRef, useState, useCallback } from 'react';
import type { Event, InterventionDetail } from './types';

interface UseWebSocketOptions {
  url?: string;
  onEvent?: (event: Event) => void;
  onIntervention?: (intervention: InterventionDetail) => void;
  reconnectInterval?: number;
  maxReconnectInterval?: number;
}

export function useWebSocket({
  url,
  onEvent,
  onIntervention,
  reconnectInterval = 2000,
  maxReconnectInterval = 15000
}: UseWebSocketOptions = {}) {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [events, setEvents] = useState<Event[]>([]);
  const [latency, setLatency] = useState<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef<number>(0);
  const reconnectTimeoutRef = useRef<any>(null);
  const pingIntervalRef = useRef<any>(null);
  const lastPingTime = useRef<number>(0);

  // Compute WebSocket URL
  const getWsUrl = useCallback(() => {
    if (url) return url;

    // 1. Explicit VITE_WS_URL override if supplied
    const envWsUrl = (import.meta.env.VITE_WS_URL || '').trim();
    if (envWsUrl) {
      return envWsUrl.endsWith('/ws/events') ? envWsUrl : `${envWsUrl.replace(/\/+$/, '')}/ws/events`;
    }

    // 2. Derive from VITE_API_URL (e.g., https://api.onrender.com -> wss://api.onrender.com/ws/events)
    const envApiUrl = (import.meta.env.VITE_API_URL || '').trim();
    if (envApiUrl) {
      try {
        const parsed = new URL(envApiUrl);
        const wsProto = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${wsProto}//${parsed.host}/ws/events`;
      } catch {
        if (envApiUrl.startsWith('http://') || envApiUrl.startsWith('https://')) {
          const wsUrl = envApiUrl.replace(/^http/, 'ws').replace(/\/+$/, '');
          return `${wsUrl}/ws/events`;
        }
      }
    }

    // 3. Local Vite dev server fallback (e.g., localhost:5173 -> localhost:8000)
    if (window.location.port === '5173') {
      return `ws://${window.location.hostname}:8000/ws/events`;
    }

    // 4. Same-origin fallback for production reverse-proxies
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}/ws/events`;
  }, [url]);

  const connect = useCallback(() => {
    try {
      const wsUrl = getWsUrl();
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        reconnectAttempts.current = 0;

        // Periodic Ping/Pong for RTT latency tracking and keepalive
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            lastPingTime.current = Date.now();
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 10000);
      };

      ws.onmessage = (messageEvent) => {
        try {
          const data = JSON.parse(messageEvent.data);

          // Handle Pong for Latency
          if (data.type === 'pong') {
            if (lastPingTime.current > 0) {
              setLatency(Date.now() - lastPingTime.current);
            }
            return;
          }

          const parsedEvent: Event = {
            id: data.id || data.event_id || `ev-${Date.now()}-${Math.random()}`,
            event_id: data.event_id || data.id,
            timestamp: data.timestamp || new Date().toISOString(),
            type: data.type || data.event_type || 'UNKNOWN',
            event_type: data.event_type || data.type || 'UNKNOWN',
            severity: data.severity || 'INFO',
            mission_id: data.mission_id,
            task_id: data.task_id,
            agent_id: data.agent_id,
            payload: data.payload || data
          };

          // Append to event ring buffer (max 300 events)
          setEvents((prev) => [parsedEvent, ...prev.slice(0, 299)]);

          // Trigger onEvent callback
          onEvent?.(parsedEvent);

          // Detect Supervisor Intervention
          const typeStr = parsedEvent.event_type || parsedEvent.type;
          if (
            typeStr === 'INTERVENTION_TRIGGERED' ||
            typeStr === 'ANOMALY_DETECTED' ||
            typeStr.includes('LOOP_DETECTED') ||
            parsedEvent.payload?.intervention_type
          ) {
            const p = parsedEvent.payload || {};
            const intervention: InterventionDetail = {
              anomaly: p.anomaly_type || p.anomaly || typeStr,
              anomaly_type: p.anomaly_type || typeStr,
              evidence: p.evidence || p.reason || 'Supervisor anomaly signature match',
              action: p.action || p.strategy || 'SUPERVISOR INTERVENTION',
              target: p.target || parsedEvent.agent_id || 'fleet',
              confidence: typeof p.confidence === 'number' ? p.confidence : 0.94,
              reason: p.reason || p.concise_reason || p.message || 'Empirical threshold violation',
              timestamp: parsedEvent.timestamp,
              mission_id: parsedEvent.mission_id || undefined,
              task_id: parsedEvent.task_id || undefined
            };
            onIntervention?.(intervention);
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message', err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        setLatency(null);
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);

        // Exponential backoff reconnect
        const timeout = Math.min(
          reconnectInterval * Math.pow(1.5, reconnectAttempts.current),
          maxReconnectInterval
        );
        reconnectAttempts.current += 1;
        reconnectTimeoutRef.current = setTimeout(connect, timeout);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (err) {
      console.error('WebSocket connection error:', err);
    }
  }, [getWsUrl, onEvent, onIntervention, reconnectInterval, maxReconnectInterval]);

  useEffect(() => {
    connect();

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
    };
  }, [connect]);

  return { isConnected, latency, events };
}
