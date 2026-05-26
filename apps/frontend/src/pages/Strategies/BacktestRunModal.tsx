import { useEffect, useRef, useState } from "react";
import { backtestJobsApi, strategiesApi } from "@/api/strategies";
import { ApiError } from "@/api/client";
import type { BacktestJob, Strategy, BacktestResult } from "@/api/types";

interface Props {
  strategy: Strategy;
  onClose: () => void;
  onCompleted: (result: BacktestResult) => void;
}

const POLL_INTERVAL_MS = 1000;
const TERMINAL_STATUSES = new Set<BacktestJob["status"]>(["done", "failed", "cancelled"]);

export function BacktestRunModal({ strategy, onClose, onCompleted }: Props) {
  const now = new Date();
  const tenDaysAgo = new Date(now.getTime() - 10 * 86400_000);

  const [label, setLabel] = useState("default");
  const [start, setStart] = useState(tenDaysAgo.toISOString().slice(0, 10));
  const [end, setEnd] = useState(now.toISOString().slice(0, 10));
  const [initialEquity, setInitialEquity] = useState("100000");
  const [slippageBps, setSlippageBps] = useState("5");
  const [timeframe, setTimeframe] = useState("1Min");
  const [paramsText, setParamsText] = useState(JSON.stringify(strategy.params, null, 2));
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<BacktestJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    return () => { cancelledRef.current = true; };
  }, []);

  async function handleRun() {
    setError(null);
    setJob(null);
    let paramsParsed: Record<string, unknown>;
    try {
      paramsParsed = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch (e) {
      setError(`Params not valid JSON: ${e}`);
      return;
    }
    setRunning(true);
    try {
      const submitted = await strategiesApi.submitBacktest(strategy.id, {
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
        label: label.trim() || "default",
        initial_equity: initialEquity,
        slippage_bps: Number(slippageBps),
        timeframe,
        params: paramsParsed,
      });

      // Poll until terminal.
      while (!cancelledRef.current) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (cancelledRef.current) return;
        let next: BacktestJob;
        try {
          next = await backtestJobsApi.get(submitted.job_id);
        } catch (e) {
          setError(`Polling failed: ${e}`);
          setRunning(false);
          return;
        }
        setJob(next);
        if (TERMINAL_STATUSES.has(next.status)) {
          if (next.status === "done" && next.result_id !== null) {
            try {
              const result = await strategiesApi.getBacktest(strategy.id, next.result_id);
              onCompleted(result);
            } catch (e) {
              setError(`Fetching result failed: ${e}`);
              setRunning(false);
            }
            return;
          }
          if (next.status === "failed") {
            setError(next.error_text ?? "Backtest failed (no error_text returned)");
          } else if (next.status === "cancelled") {
            setError("Backtest was cancelled.");
          }
          setRunning(false);
          return;
        }
      }
    } catch (e) {
      if (e instanceof ApiError) setError(`${JSON.stringify(e.body)} (status ${e.status})`);
      else setError(String(e));
      setRunning(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70">
      <div className="w-[32rem] max-h-[90vh] overflow-y-auto rounded-lg border border-gray-700 bg-gray-950 p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Run backtest</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div className="space-y-3 text-sm text-gray-300">
          <label className="block">
            <span className="text-xs text-gray-400">Label</span>
            <input type="text" value={label} onChange={(e) => setLabel(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-xs text-gray-400">Start</span>
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">End</span>
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
            </label>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <label className="block">
              <span className="text-xs text-gray-400">Initial equity</span>
              <input type="text" value={initialEquity} onChange={(e) => setInitialEquity(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Slippage (bps)</span>
              <input type="number" min="0" value={slippageBps} onChange={(e) => setSlippageBps(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white" />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Timeframe</span>
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white">
                <option value="1Min">1Min</option>
                <option value="5Min">5Min</option>
                <option value="15Min">15Min</option>
                <option value="1Hour">1Hour</option>
                <option value="1Day">1Day</option>
              </select>
            </label>
          </div>

          <label className="block">
            <span className="text-xs text-gray-400">Params override (JSON)</span>
            <textarea value={paramsText} onChange={(e) => setParamsText(e.target.value)}
              rows={8} className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-xs text-white" />
          </label>

          {error && (
            <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
              {error}
            </div>
          )}

          {running && (
            <div className="space-y-1 rounded border border-blue-700 bg-blue-900/30 p-2 text-sm text-blue-200">
              <div>
                Backtest job {job ? `#${job.id}` : "queued"} — status:{" "}
                <span className="font-semibold">{job?.status ?? "submitting"}</span>
              </div>
              <div className="text-xs text-blue-300">
                Progress: {((job?.percent_complete ?? 0) * 100).toFixed(0)}%
                {job?.current_ts ? ` · at ${job.current_ts}` : ""}
              </div>
              <div className="text-xs text-blue-300/80">
                Don&apos;t close this window — it&apos;s polling the job and will open the
                results when done.
              </div>
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} disabled={running}
            className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200 disabled:opacity-50">Cancel</button>
          <button onClick={handleRun} disabled={running}
            className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700">
            {running ? "Running…" : "Run"}
          </button>
        </div>
      </div>
    </div>
  );
}
