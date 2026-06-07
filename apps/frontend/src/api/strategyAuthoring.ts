import { apiFetch } from "./client";

export interface BacktestMetrics {
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  trade_count: number;
  starting_equity: number;
  ending_equity: number;
}

export interface AuthorBacktest {
  status: string; // ok | no_trades | syntax_error | unsafe_code | load_error | runtime_error | unavailable
  metrics: BacktestMetrics | null;
  trade_count: number;
  error: string | null;
}

export interface AuthorResult {
  code: string;
  assumptions: string[];
  explanation: string;
  cost_usd: number;
  model: string;
  prompt_version: string;
  backtest: AuthorBacktest;
  auto_fixed: boolean;
}

export interface SavedStrategy {
  id: number;
  name: string;
  status: string;
  code_path: string;
  authoring_method: string;
}

export interface AuthoringStatus {
  strategy_id: number;
  authoring_method: string;
  revision_count: number;
  out_of_sync: boolean;
}

export interface RevisionInput {
  kind: "generation" | "refinement";
  user_message: string;
  assumptions: string[];
  explanation: string;
  code: string;
  backtest: AuthorBacktest | null;
  cost_usd: number | null;
}

export const strategyAuthoringApi = {
  author: (description: string) =>
    apiFetch<AuthorResult>(`/api/v1/strategies/author`, {
      method: "POST",
      body: JSON.stringify({ description }),
    }),

  refine: (prior_code: string, request: string) =>
    apiFetch<AuthorResult>(`/api/v1/strategies/author/refine`, {
      method: "POST",
      body: JSON.stringify({ prior_code, request }),
    }),

  saveAuthored: (code: string, name: string, history: RevisionInput[] = []) =>
    apiFetch<SavedStrategy>(`/api/v1/strategies/author/save`, {
      method: "POST",
      body: JSON.stringify({ code, name, history }),
    }),

  status: (strategyId: number) =>
    apiFetch<AuthoringStatus>(`/api/v1/strategies/${strategyId}/authoring-status`),
};
