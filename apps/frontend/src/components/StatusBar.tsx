import { useEffect, useState } from "react";
import { getWsClient } from "../ws/client";

export default function StatusBar() {
  const [lastHeartbeat, setLastHeartbeat] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const client = getWsClient();
    const offHeartbeat = client.on("system.heartbeat", (event) => {
      setLastHeartbeat(typeof event.ts === "string" ? event.ts : new Date().toISOString());
    });
    const offConnected = client.on("system.connected", () => {
      setConnected(true);
    });
    const offClosed = client.onConnectionChange((isOpen) => setConnected(isOpen));
    client.start();
    return () => {
      offHeartbeat();
      offConnected();
      offClosed();
    };
  }, []);

  return (
    <footer className="h-7 shrink-0 flex items-center justify-between px-3 border-t border-neutral-800 bg-neutral-950 text-[11px] text-neutral-500">
      <div className="flex items-center gap-2">
        <span
          aria-label={connected ? "Connected" : "Disconnected"}
          className={`size-2 rounded-full ${connected ? "bg-emerald-500" : "bg-neutral-600"}`}
        />
        <span>{connected ? "WS connected" : "WS disconnected"}</span>
      </div>
      <div>
        Last heartbeat:{" "}
        <span className="text-neutral-300 font-mono">
          {lastHeartbeat ?? "—"}
        </span>
      </div>
    </footer>
  );
}
