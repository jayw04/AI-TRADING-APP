import { useCallback, useEffect, useRef, useState } from "react";
import { backtestJobsApi, strategiesApi } from "@/api/strategies";
import { ApiError } from "@/api/client";
import { useWorkbenchSocket, type WorkbenchMessage } from "@/hooks/useWorkbenchSocket";
import type { BacktestJob, BacktestJobStatus, BacktestResult, Strategy } from "@/api/types";

interface Props {
  strategy: Strategy;
  onClose: () => void;
  onCompleted: (result: BacktestResult) => void;
}

// Polling cadence as fallback in case a WS message is missed (or the modal
// mounts after `backtest.queued` already fired). We poll fast (1s) until the
// first WS frame arrives, then slow down (5s) since WS is driving updates.
const POLL_FAST_MS = 1000;
const POLL_SLOW_MS = 5000;

const TERMINAL_STATUSES = new Set<BacktestJobStatus>([
  "completed",
  "failed",
  "cancelled",
]);

const WS_TOPICS = ["backtests"];

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
  const [jobId, setJobId] = useState<number | null>(null);
  const [job, setJob] = useState<BacktestJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [wsActive, setWsActive] = useState(false);

  // Latest job_id in a ref so the WS handler (memoized once) can compare
  // without re-subscribing on every state change.
  const activeJobIdRef = useRef<number | null>(null);
  activeJobIdRef.current = jobId;

  // Guard so the cleanup unmount can stop the poll loop without racing.
  const unmountedRef = useRef(false);
  useEffect(() => {
    return () => {
      unmountedRef.current = true;
    };
  }, []);

  // Fetch the full result + bubble up. Centralized so both WS and poll paths
  // hit the same code.
  const finalize = useCallback(
    async (j: BacktestJob) => {
      if (j.status === "completed" && j.result_id !== null) {
        try {
          const result = await strategiesApi.getBacktest(strategy.id, j.result_id);
          if (!unmountedRef.current) {
            onCompleted(result);
          }
        } catch (e) {
          setError(`Fetching result failed: ${e}`);
          setRunning(false);
        }
        return;
      }
      if (j.status === "failed") {
        setError(j.error_text ?? "Backtest failed (no error_text returned)");
      } else if (j.status === "cancelled") {
        setError("Backtest was cancelled.");
      }
      setRunning(false);
    },
    [strategy.id, onCompleted],
  );

  // WS handler — promotes the job from the bus events. Avoids depending on
  // the current `job` state so the subscription identity stays stable across
  // renders.
  const handleWs = useCallback(
    (msg: WorkbenchMessage) => {
      const payload = msg.payload as {
        job_id?: number;
        percent_complete?: number;
        current_ts?: string | null;
        error_text?: string;
        backtest_id?: number;
      };
      if (
        typeof payload.job_id !== "number" ||
        payload.job_id !== activeJobIdRef.current
      ) {
        return;
      }
      setWsActive(true);
      setJob((prev) => {
        // Synthesize a BacktestJob-shaped object from event fields, falling
        // back to the prior snapshot for fields the event doesn't carry.
        const base: BacktestJob =
          prev ??
          ({
            id: payload.job_id!,
            user_id: 0,
            strategy_id: strategy.id,
            result_id: null,
            status: "queued",
            label: "",
            percent_complete: 0,
            current_ts: null,
            submitted_at: new Date().toISOString(),
            started_at: null,
            completed_at: null,
            error_text: null,
          } as BacktestJob);
        switch (msg.topic) {
          case "backtest.started":
            return { ...base, status: "running", started_at: msg.ts };
          case "backtest.progress":
            return {
              ...base,
              status: "running",
              percent_complete: payload.percent_complete ?? base.percent_complete,
              current_ts: payload.current_ts ?? base.current_ts,
            };
          case "backtest.completed":
            return {
              ...base,
              status: "completed",
              result_id: payload.backtest_id ?? base.result_id,
              percent_complete: 1,
              completed_at: msg.ts,
            };
          case "backtest.failed":
            return {
              ...base,
              status: "failed",
              error_text: payload.error_text ?? base.error_text,
              completed_at: msg.ts,
            };
          case "backtest.cancelled":
            return {
              ...base,
              status: "cancelled",
              completed_at: msg.ts,
            };
          default:
            return prev;
        }
      });
    },
    [strategy.id],
  );

  useWorkbenchSocket(WS_TOPICS, handleWs);

  // When job transitions to terminal status, finalize() fires once.
  const terminalFiredRef = useRef(false);
  useEffect(() => {
    if (!job || terminalFiredRef.current) return;
    if (TERMINAL_STATUSES.has(job.status)) {
      terminalFiredRef.current = true;
      void finalize(job);
    }
  }, [job, finalize]);

  async function handleRun() {
    setError(null);
    setJob(null);
    setJobId(null);
    setWsActive(false);
    terminalFiredRef.current = false;

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
      setJobId(submitted.job_id);
      // Start the polling fallback. The WS handler runs in parallel and
      // updates `wsActive`; the poll loop slows down once WS is confirmed
      // live and stops on terminal status.
      void runPollFallback(submitted.job_id);
    } catch (e) {
      if (e instanceof ApiError) setError(`${JSON.stringify(e.body)} (status ${e.status})`);
      else setError(String(e));
      setRunning(false);
    }
  }

  async function runPollFallback(thisJobId: number) {
    while (!unmountedRef.current) {
      // If we already fired terminal handling from a WS event, stop polling.
      if (terminalFiredRef.current) return;
      const delay = wsActive ? POLL_SLOW_MS : POLL_FAST_MS;
      await new Promise((r) => setTimeout(r, delay));
      if (unmountedRef.current || terminalFiredRef.current) return;
      // Only poll the job that's still active — if Run was clicked again,
      // jobId changed and this loop should exit.
      if (activeJobIdRef.current !== thisJobId) return;
      let next: BacktestJob;
      try {
        next = await backtestJobsApi.get(thisJobId);
      } catch (e) {
        // Don't surface transient poll failures unless WS isn't carrying us.
        if (!wsActive) {
          setError(`Polling failed: ${e}`);
          setRunning(false);
        }
        return;
      }
      // Prefer WS-synthesized state when WS is live, but adopt fields the
      // poll knows that events don't carry (label, etc.).
      setJob((prev) => {
        if (prev && TERMINAL_STATUSES.has(prev.status)) return prev;
        return next;
      });
      if (TERMINAL_STATUSES.has(next.status)) return;
    }
  }

  async function handleCancel() {
    if (jobId === null) {
      onClose();
      return;
    }
    setCancelling(true);
    try {
      await backtestJobsApi.cancel(jobId);
      // Don't close the modal here — wait for backtest.cancelled to arrive,
      // which the WS handler turns into a terminal status. That keeps the
      // failure flow consistent (user sees confirmation, then dismisses).
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`Cancel failed: ${JSON.stringify(e.body)} (status ${e.status})`);
      } else {
        setError(`Cancel failed: ${e}`);
      }
    } finally {
      setCancelling(false);
    }
  }

  const progressPct = Math.round((job?.percent_complete ?? 0) * 100);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70">
      <div className="w-[32rem] max-h-[90vh] overflow-y-auto rounded-lg border border-gray-700 bg-gray-950 p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Run backtest</h2>
          <button
            onClick={onClose}
            disabled={running && !TERMINAL_STATUSES.has(job?.status ?? "queued")}
            className="text-gray-400 hover:text-white disabled:opacity-30"
          >
            ✕
          </button>
        </div>

        <div className="space-y-3 text-sm text-gray-300">
          <label className="block">
            <span className="text-xs text-gray-400">Label</span>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              disabled={running}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white disabled:opacity-50"
            />
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-xs text-gray-400">Start</span>
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                disabled={running}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white disabled:opacity-50"
              />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">End</span>
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                disabled={running}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white disabled:opacity-50"
              />
            </label>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <label className="block">
              <span className="text-xs text-gray-400">Initial equity</span>
              <input
                type="text"
                value={initialEquity}
                onChange={(e) => setInitialEquity(e.target.value)}
                disabled={running}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white disabled:opacity-50"
              />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Slippage (bps)</span>
              <input
                type="number"
                min="0"
                value={slippageBps}
                onChange={(e) => setSlippageBps(e.target.value)}
                disabled={running}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white disabled:opacity-50"
              />
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Timeframe</span>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                disabled={running}
                className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white disabled:opacity-50"
              >
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
            <textarea
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              disabled={running}
              rows={8}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-xs text-white disabled:opacity-50"
            />
          </label>

          {error && (
            <div
              data-testid="bt-error"
              className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200"
            >
              {error}
            </div>
          )}

          {running && (
            <div
              data-testid="bt-status"
              className="space-y-2 rounded border border-blue-700 bg-blue-900/30 p-3 text-sm text-blue-200"
            >
              <div className="flex items-center justify-between">
                <span>
                  Backtest {jobId !== null ? `#${jobId}` : "queued"} —{" "}
                  <span className="font-semibold">{job?.status ?? "submitting"}</span>
                </span>
                <span className="text-xs text-blue-300/80">
                  {wsActive ? "live" : "polling"}
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded bg-blue-950">
                <div
                  data-testid="bt-progress-bar"
                  className="h-full bg-blue-500 transition-[width] duration-300"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-xs text-blue-300">
                <span>{progressPct}%</span>
                {job?.current_ts ? <span>at {job.current_ts}</span> : null}
              </div>
              <div className="text-xs text-blue-300/80">
                You can close this window — the backtest keeps running and will
                appear in the Backtests tab when done.
              </div>
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          {running && jobId !== null && !TERMINAL_STATUSES.has(job?.status ?? "queued") && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="rounded bg-amber-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50"
            >
              {cancelling ? "Cancelling…" : "Cancel backtest"}
            </button>
          )}
          <button
            onClick={onClose}
            disabled={running && !TERMINAL_STATUSES.has(job?.status ?? "queued")}
            className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200 disabled:opacity-50"
          >
            Close
          </button>
          <button
            onClick={handleRun}
            disabled={running}
            className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700"
          >
            {running ? "Running…" : "Run"}
          </button>
        </div>
      </div>
    </div>
  );
}
