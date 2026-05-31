import { useEffect, useRef, useCallback } from "react";

// P5 §3: default to the page origin (Vite/reverse proxy) so the WS handshake
// carries the session cookie; VITE_WS_BASE overrides for cross-origin setups.
const WS_BASE = (() => {
  const env = import.meta.env.VITE_WS_BASE;
  if (env) return env.replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location?.host) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}`;
  }
  return "ws://127.0.0.1:8000";
})();

export interface WorkbenchMessage {
  topic: string;
  type: string;
  payload: Record<string, unknown>;
  ts: string;
}

type Handler = (msg: WorkbenchMessage) => void;

interface Subscription {
  topics: string[];
  handler: Handler;
}

class WorkbenchSocketSingleton {
  private ws: WebSocket | null = null;
  private subs = new Set<Subscription>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;

  subscribe(sub: Subscription) {
    this.subs.add(sub);
    this.ensureConnected();
    this.sendSubscribe(sub.topics);
    return () => {
      this.subs.delete(sub);
      if (this.subs.size === 0) {
        this.close();
      }
    };
  }

  private ensureConnected() {
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    this.connect();
  }

  private connect() {
    try {
      this.ws = new WebSocket(`${WS_BASE}/ws`);
    } catch (e) {
      console.error("WS connect failed:", e);
      this.scheduleReconnect();
      return;
    }
    this.ws.onopen = () => {
      this.reconnectAttempt = 0;
      const allTopics = new Set<string>();
      this.subs.forEach((s) => s.topics.forEach((t) => allTopics.add(t)));
      this.sendSubscribe([...allTopics]);
    };
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as WorkbenchMessage;
        this.subs.forEach((s) => {
          if (s.topics.includes(msg.topic)) {
            try {
              s.handler(msg);
            } catch (e) {
              console.error("WS handler threw:", e);
            }
          }
        });
      } catch {
        /* ignore non-JSON frames */
      }
    };
    this.ws.onclose = () => {
      this.ws = null;
      if (this.subs.size > 0) {
        this.scheduleReconnect();
      }
    };
    this.ws.onerror = () => {
      try {
        this.ws?.close();
      } catch {
        /* ignore */
      }
    };
  }

  private sendSubscribe(topics: string[]) {
    if (!topics.length) return;
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(JSON.stringify({ action: "subscribe", topics }));
    } catch (e) {
      console.error("WS subscribe send failed:", e);
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    const backoff = Math.min(30_000, 1_000 * Math.pow(2, this.reconnectAttempt));
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, backoff);
  }

  private close() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    try {
      this.ws?.close();
    } catch {
      /* ignore */
    }
    this.ws = null;
  }
}

const singleton = new WorkbenchSocketSingleton();

export function useWorkbenchSocket(topics: string[], handler: Handler) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  const stableHandler = useCallback((msg: WorkbenchMessage) => {
    handlerRef.current(msg);
  }, []);

  // Re-subscribe only when the set of topics actually changes — not on
  // every render. `topics` is intentionally read inside the effect via
  // closure rather than added to deps; callers typically pass a fresh
  // array literal each render.
  const topicsKey = topics.join(",");
  useEffect(() => {
    const unsub = singleton.subscribe({ topics, handler: stableHandler });
    return unsub;
  }, [topicsKey, stableHandler]);
}
