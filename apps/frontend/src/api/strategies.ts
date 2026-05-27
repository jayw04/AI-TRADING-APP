import { apiFetch } from "./client";
import type {
  Strategy,
  StrategyActionResponse,
  StrategyCreateRequest,
  StrategyListResponse,
  StrategyRunListResponse,
  StrategyStatus,
  StrategyType,
  StrategyUpdateRequest,
  SignalListResponse,
  BacktestListResponse,
  BacktestRequest,
  BacktestResult,
  BacktestJob,
  BacktestJobSubmittedResponse,
} from "./types";

export const strategiesApi = {
  list: (params: { status?: StrategyStatus; type?: StrategyType; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.type) q.set("type", params.type);
    if (params.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q}` : "";
    return apiFetch<StrategyListResponse>(`/api/v1/strategies${suffix}`);
  },

  get: (id: number) => apiFetch<Strategy>(`/api/v1/strategies/${id}`),

  create: (body: StrategyCreateRequest) =>
    apiFetch<Strategy>("/api/v1/strategies", { method: "POST", body: JSON.stringify(body) }),

  update: (id: number, body: StrategyUpdateRequest) =>
    apiFetch<Strategy>(`/api/v1/strategies/${id}`, { method: "PUT", body: JSON.stringify(body) }),

  start: (id: number) =>
    apiFetch<StrategyActionResponse>(`/api/v1/strategies/${id}/start`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  stop: (id: number) =>
    apiFetch<StrategyActionResponse>(`/api/v1/strategies/${id}/stop`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  reload: (id: number) =>
    apiFetch<StrategyActionResponse>(`/api/v1/strategies/${id}/reload`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  listRuns: (id: number, limit = 50) =>
    apiFetch<StrategyRunListResponse>(`/api/v1/strategies/${id}/runs?limit=${limit}`),

  listSignals: (id: number, limit = 100) =>
    apiFetch<SignalListResponse>(`/api/v1/strategies/${id}/signals?limit=${limit}`),

  listBacktests: (id: number, limit = 50) =>
    apiFetch<BacktestListResponse>(`/api/v1/strategies/${id}/backtests?limit=${limit}`),

  getBacktest: (id: number, backtestId: number) =>
    apiFetch<BacktestResult>(`/api/v1/strategies/${id}/backtests/${backtestId}`),

  // Async submit: returns 202 + job_id. Caller subscribes to the `backtests`
  // WS topic for live progress (with a polling fallback via
  // backtestJobsApi.get); on status="completed", fetches the full result via
  // getBacktest(strategy_id, result_id).
  submitBacktest: (id: number, body: BacktestRequest) =>
    apiFetch<BacktestJobSubmittedResponse>(`/api/v1/strategies/${id}/backtest`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export const backtestJobsApi = {
  get: (jobId: number) => apiFetch<BacktestJob>(`/api/v1/backtest-jobs/${jobId}`),

  cancel: (jobId: number) =>
    apiFetch<BacktestJob>(`/api/v1/backtest-jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
