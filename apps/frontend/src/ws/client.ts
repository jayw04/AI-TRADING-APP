/**
 * Workbench WebSocket client.
 *
 * - Connects to `${VITE_WS_BASE}/ws`.
 * - Exponential-backoff reconnect (250ms → 8s, with jitter).
 * - Topic-style listener API: `client.on("system.heartbeat", handler)`.
 *   Listeners match by the `type` field of incoming events.
 * - `onConnectionChange(handler)` for raw open/close transitions.
 *
 * P0: a singleton via `getWsClient()`. Per-topic subscription protocol with
 * the backend lands in P1+.
 */

export type WsEvent = { type: string; [key: string]: unknown };

type Listener<T = WsEvent> = (event: T) => void;
type ConnectionListener = (isOpen: boolean) => void;

const WS_BASE = (import.meta.env.VITE_WS_BASE ?? "ws://127.0.0.1:8000").replace(/\/$/, "");

export class WorkbenchWsClient {
  private url: string;
  private socket: WebSocket | null = null;
  private listeners = new Map<string, Set<Listener>>();
  private connectionListeners = new Set<ConnectionListener>();
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private started = false;
  private closedManually = false;

  constructor(url = `${WS_BASE}/ws`) {
    this.url = url;
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    this.closedManually = false;
    this.connect();
  }

  stop(): void {
    this.closedManually = true;
    this.started = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
  }

  on(type: string, handler: Listener): () => void {
    let set = this.listeners.get(type);
    if (!set) {
      set = new Set();
      this.listeners.set(type, set);
    }
    set.add(handler);
    return () => {
      set?.delete(handler);
    };
  }

  onConnectionChange(handler: ConnectionListener): () => void {
    this.connectionListeners.add(handler);
    return () => {
      this.connectionListeners.delete(handler);
    };
  }

  private connect(): void {
    if (typeof WebSocket === "undefined") return;
    try {
      this.socket = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket.addEventListener("open", () => {
      this.reconnectAttempt = 0;
      this.connectionListeners.forEach((fn) => fn(true));
    });
    this.socket.addEventListener("message", (msg) => {
      let parsed: WsEvent | null = null;
      try {
        parsed = JSON.parse(msg.data) as WsEvent;
      } catch {
        return;
      }
      const handlers = this.listeners.get(parsed.type);
      handlers?.forEach((h) => h(parsed!));
    });
    const onCloseOrError = () => {
      this.connectionListeners.forEach((fn) => fn(false));
      if (!this.closedManually) this.scheduleReconnect();
    };
    this.socket.addEventListener("close", onCloseOrError);
    this.socket.addEventListener("error", onCloseOrError);
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const base = Math.min(250 * 2 ** this.reconnectAttempt, 8000);
    const jitter = Math.random() * 250;
    const delay = base + jitter;
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }
}

let singleton: WorkbenchWsClient | null = null;

export function getWsClient(): WorkbenchWsClient {
  if (!singleton) singleton = new WorkbenchWsClient();
  return singleton;
}
