import { apiFetch } from "./client";

export interface DriftFindingPayload {
  strategy_id: number;
  breached: string[];
  win_rate: { live: number; baseline: number; delta_pp: number };
  avg_return_per_trade: { live: number; baseline: number; delta_pct: number };
  trade_count: number;
  detected_at: string;
}

export interface DriftStatus {
  status: "drift_detected" | "no_recent_drift";
  strategy_id: number;
  lookback_days: number;
  detected_at?: string;
  payload?: DriftFindingPayload;
}

export interface DriftFinding {
  strategy_id: number;
  detected_at: string | null;
  breached: string[];
  win_rate: { live?: number; baseline?: number; delta_pp?: number };
  avg_return_per_trade: { live?: number; baseline?: number; delta_pct?: number };
  trade_count: number | null;
  audit_id: number;
}

export interface DriftCheckResult {
  kind: "drift_detected" | "within_thresholds" | "skip";
  strategy_id: number;
  reason?: string;
  breached?: string[];
  win_rate_delta_pp?: number;
  avg_return_delta_pct?: number;
}

export const driftApi = {
  // Per-strategy status (card + MCP) — latest finding within lookback or none.
  status: (strategyId: number, lookbackDays = 7) =>
    apiFetch<DriftStatus>(
      `/api/v1/strategies/${strategyId}/drift-status?lookback_days=${lookbackDays}`,
    ),

  // On-demand re-evaluation ("Re-check now").
  check: (strategyId: number) =>
    apiFetch<DriftCheckResult>(`/api/v1/strategies/${strategyId}/drift-check`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // User-level list across strategies (the morning-brief section's single call).
  findings: (limit = 10) =>
    apiFetch<{ items: DriftFinding[] }>(`/api/v1/drift-findings?limit=${limit}`),
};
