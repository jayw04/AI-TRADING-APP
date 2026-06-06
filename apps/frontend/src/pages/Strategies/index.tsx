import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { strategiesApi } from "@/api/strategies";
import { signalsApi } from "@/api/signals";
import { ApiError } from "@/api/client";
import type { Strategy } from "@/api/types";
import { ACTIVE_STRATEGY_STATUSES } from "@/api/types";
import { StatusBadge } from "@/components/strategies/StatusBadge";
import { NewStrategyModal } from "./NewStrategyModal";
import { useWorkbenchSocket } from "@/hooks/useWorkbenchSocket";

interface RowStats {
  signalsToday: number;
}

export default function StrategiesListPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [stats, setStats] = useState<Map<number, RowStats>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [actionPending, setActionPending] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await strategiesApi.list();
      setStrategies(resp.items);
      setError(null);

      const startOfDay = new Date();
      startOfDay.setHours(0, 0, 0, 0);
      const since = startOfDay.toISOString();
      const newStats = new Map<number, RowStats>();
      await Promise.all(
        resp.items.map(async (s) => {
          try {
            const sig = await signalsApi.list({ strategy_id: s.id, since, limit: 1000 });
            newStats.set(s.id, { signalsToday: sig.count });
          } catch {
            newStats.set(s.id, { signalsToday: 0 });
          }
        }),
      );
      setStats(newStats);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  useWorkbenchSocket(["strategies", "signals"], (msg) => {
    if (msg.topic === "strategies") {
      load();
    } else if (msg.topic === "signals") {
      const sid = msg.payload.strategy_id as number | null | undefined;
      if (sid !== null && sid !== undefined) {
        setStats((prev) => {
          const next = new Map(prev);
          const cur = next.get(sid) ?? { signalsToday: 0 };
          next.set(sid, { signalsToday: cur.signalsToday + 1 });
          return next;
        });
      }
    }
  });

  async function handleStart(s: Strategy) {
    if (!confirm(`Start strategy "${s.name}" on paper?`)) return;
    setActionPending(s.id);
    try {
      await strategiesApi.start(s.id);
      await load();
    } catch (e) {
      if (e instanceof ApiError) {
        alert(`Start failed: ${JSON.stringify(e.body)}`);
      } else {
        alert(`Start failed: ${e}`);
      }
    } finally {
      setActionPending(null);
    }
  }

  async function handleStop(s: Strategy) {
    if (!confirm(`Stop strategy "${s.name}"?`)) return;
    setActionPending(s.id);
    try {
      await strategiesApi.stop(s.id);
      await load();
    } catch (e) {
      alert(`Stop failed: ${e}`);
    } finally {
      setActionPending(null);
    }
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Strategies</h1>
        <div className="flex items-center gap-2">
          <Link
            to="/strategies/author"
            className="rounded bg-purple-700 px-3 py-1 text-sm font-semibold text-white hover:bg-purple-600"
          >
            ✨ Author with AI
          </Link>
          <button
            onClick={() => setShowNew(true)}
            className="rounded bg-blue-700 px-3 py-1 text-sm font-semibold text-white hover:bg-blue-600"
          >
            + New strategy
          </button>
          <button
            onClick={load}
            className="rounded bg-gray-700 px-3 py-1 text-sm text-gray-200"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-700 bg-red-900/40 p-2 text-red-200">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Symbols</th>
              <th className="px-3 py-2 text-right">Signals today</th>
              <th className="px-3 py-2">Schedule</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {strategies.length === 0 && !loading && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-center text-gray-500">
                  No strategies yet. Click &quot;+ New strategy&quot; to register one.
                </td>
              </tr>
            )}
            {strategies.map((s) => (
              <tr key={s.id} className="border-t border-gray-800 hover:bg-gray-900">
                <td className="px-3 py-2 font-semibold">
                  <Link to={`/strategies/${s.id}`} className="text-white hover:underline">
                    {s.name}
                  </Link>
                  <span className="ml-2 text-xs text-gray-500">v{s.version}</span>
                  {s.has_pending_reload && (
                    <span
                      data-testid={`reload-pending-${s.id}`}
                      className="ml-2 rounded bg-amber-700 px-1.5 py-0.5 text-[10px] font-semibold text-amber-100"
                    >
                      RELOAD PENDING
                    </span>
                  )}
                  {s.status === "error" && s.error_text && (
                    <div className="mt-1 text-xs text-rose-400">
                      {s.error_text.slice(0, 80)}{s.error_text.length > 80 ? "…" : ""}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 text-gray-300">{s.type}</td>
                <td className="px-3 py-2"><StatusBadge status={s.status} /></td>
                <td className="px-3 py-2 text-gray-300">{s.symbols.join(", ") || "—"}</td>
                <td className="px-3 py-2 text-right">{stats.get(s.id)?.signalsToday ?? 0}</td>
                <td className="px-3 py-2 font-mono text-xs text-gray-400">{s.schedule}</td>
                <td className="px-3 py-2 text-right">
                  {ACTIVE_STRATEGY_STATUSES.includes(s.status) ? (
                    <button
                      onClick={() => handleStop(s)}
                      disabled={actionPending === s.id}
                      className="rounded bg-red-800 px-2 py-1 text-xs font-semibold text-white hover:bg-red-700 disabled:bg-gray-700"
                    >
                      {actionPending === s.id ? "…" : "Stop"}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleStart(s)}
                      disabled={actionPending === s.id || s.status === "error"}
                      className="rounded bg-emerald-700 px-2 py-1 text-xs font-semibold text-white hover:bg-emerald-600 disabled:bg-gray-700"
                    >
                      {actionPending === s.id ? "…" : (s.status === "error" ? "Errored" : "Start")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showNew && (
        <NewStrategyModal
          onClose={() => setShowNew(false)}
          onCreated={async () => {
            setShowNew(false);
            await load();
          }}
        />
      )}
    </div>
  );
}
