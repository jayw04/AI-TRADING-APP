import { useCallback, useEffect, useState } from "react";
import { agentApi } from "@/api/agent";
import type {
  AgentBudget,
  AgentSessionDetail,
  AgentSessionMode,
  AgentSessionSummary,
} from "@/api/types";
import { useWorkbenchSocket } from "@/hooks/useWorkbenchSocket";
import { SessionList } from "./SessionList";
import { ChatPanel } from "./ChatPanel";
import { CostMeter } from "./CostMeter";

/**
 * Agent chat panel — top-level page at /agent.
 *
 * Layout: 288px session-list rail on the left, chat panel filling the
 * remainder. WS-driven (subscribes to the `agent` topic) for live
 * updates without polling; budget gets a 30s heartbeat poll on top.
 *
 * WS payloads are intentionally compact — we use them as triggers to
 * re-fetch the session detail, not as the source of truth. That way the
 * UI sees exactly what the server has (including any SYSTEM messages
 * emitted during the same turn).
 *
 * The placement decision deferred from P3 §1: top-level page, not a
 * docked side panel. A dedicated page is the right shape for chats that
 * include collapsible tool cards and suggestion action cards — they
 * need width.
 */
export default function AgentPage() {
  const [sessions, setSessions] = useState<AgentSessionSummary[]>([]);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [currentDetail, setCurrentDetail] =
    useState<AgentSessionDetail | null>(null);
  const [budget, setBudget] = useState<AgentBudget | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      const resp = await agentApi.listSessions();
      setSessions(resp.items);
      setCurrentId((existing) => {
        if (existing !== null) return existing;
        const active = resp.items.find((s) => s.status === "active");
        if (active) return active.id;
        if (resp.items.length > 0) return resp.items[0].id;
        return null;
      });
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const loadCurrent = useCallback(async () => {
    if (currentId === null) {
      setCurrentDetail(null);
      return;
    }
    try {
      const d = await agentApi.getSession(currentId);
      setCurrentDetail(d);
    } catch (e) {
      setError(String(e));
    }
  }, [currentId]);

  const loadBudget = useCallback(async () => {
    try {
      const b = await agentApi.getBudget();
      setBudget(b);
    } catch {
      // Best-effort; the meter just shows stale data if a poll fails.
    }
  }, []);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    void loadCurrent();
  }, [loadCurrent]);

  useEffect(() => {
    void loadBudget();
    const id = setInterval(() => void loadBudget(), 30_000);
    return () => clearInterval(id);
  }, [loadBudget]);

  useWorkbenchSocket(["agent"], (msg) => {
    const payload = msg.payload as { session_id?: number; role?: string };
    if (payload.session_id !== undefined && payload.session_id === currentId) {
      void loadCurrent();
    }
    if (
      msg.type === "agent.session_started" ||
      msg.type === "agent.session_ended" ||
      msg.type === "agent.session_capped" ||
      msg.type === "agent.session_error"
    ) {
      void loadSessions();
    }
    if (
      msg.type === "agent.message_appended" &&
      payload.role === "assistant"
    ) {
      void loadBudget();
    }
  });

  async function handleNewSession(mode: AgentSessionMode) {
    try {
      const s = await agentApi.startSession(mode);
      setCurrentId(s.id);
      await loadSessions();
    } catch (e) {
      alert(`Could not start session: ${e}`);
    }
  }

  async function handleSend(text: string) {
    if (currentId === null) return;
    try {
      await agentApi.appendMessage(currentId, text);
      await loadCurrent();
      await loadBudget();
    } catch (e) {
      alert(`Send failed: ${e}`);
    }
  }

  async function handleEnd() {
    if (currentId === null) return;
    try {
      await agentApi.endSession(currentId);
      await loadSessions();
      await loadCurrent();
    } catch (e) {
      alert(`End failed: ${e}`);
    }
  }

  return (
    <div className="flex h-[calc(100vh-64px)]">
      <div className="flex w-72 flex-col border-r border-gray-800 bg-gray-950">
        <div className="space-y-2 border-b border-gray-800 p-3">
          <div className="text-sm font-semibold text-gray-300">Agent</div>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => void handleNewSession("b2_interactive")}
              className="flex-1 rounded bg-blue-700 px-2 py-1 text-xs font-semibold text-white hover:bg-blue-600"
            >
              + B2 chat
            </button>
            <button
              type="button"
              onClick={() => void handleNewSession("b1_readonly")}
              className="flex-1 rounded bg-gray-700 px-2 py-1 text-xs font-semibold text-gray-200 hover:bg-gray-600"
            >
              + B1 read
            </button>
          </div>
          {budget && <CostMeter budget={budget} />}
        </div>
        <SessionList
          sessions={sessions}
          currentId={currentId}
          onSelect={setCurrentId}
        />
      </div>

      <div className="flex flex-1 flex-col">
        {error && (
          <div className="border-b border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
            {error}
          </div>
        )}
        {currentDetail ? (
          <ChatPanel
            session={currentDetail}
            onSend={handleSend}
            onEnd={handleEnd}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-gray-500">
            No session. Click "+ B2 chat" or "+ B1 read" to start.
          </div>
        )}
      </div>
    </div>
  );
}
