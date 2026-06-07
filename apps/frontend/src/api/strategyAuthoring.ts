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

export interface AuthoringBudget {
  daily_cap_usd: number;
  spent_today_usd: number;
  remaining_usd: number;
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

  budget: () => apiFetch<AuthoringBudget>(`/api/v1/strategies/author/budget`),
};

export const PRESETS: { label: string; description: string }[] = [
  {
    label: "Moving-average crossover",
    description:
      "Buy when the 20-period EMA crosses above the 50-period EMA; exit when it crosses back below or a 2x ATR stop is hit.",
  },
  {
    label: "RSI mean reversion",
    description:
      "Buy when RSI(14) drops below 30; exit when it rises above 55. Risk 1% of equity per trade with a 2x ATR stop.",
  },
  {
    label: "Breakout",
    description:
      "Buy when price closes above the highest high of the last 20 bars; exit on a close below the 10-bar low or a 2x ATR stop.",
  },
];
