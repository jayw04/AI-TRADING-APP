import { apiFetch } from "./client";

export interface RiskState {
  circuit_breaker: {
    account_id: number;
    tripped: boolean;
    tripped_at: string | null;
    realized_pnl_today: string;
    unrealized_pnl_now: string;
    max_daily_loss: string;
    headroom: string;
  };
  pdt: {
    account_id: number;
    is_at_risk: boolean;
    day_trade_count: number;
    threshold: number;
    window_days: number;
    account_equity: string | null;
    equity_threshold: string;
  };
}

export interface RiskLimits {
  id: number;
  user_id: number;
  broker_mode: "paper" | "live";
  scope_type: string;
  scope_id: number | null;
  max_position_qty: number | null;
  max_position_notional: string | null;
  max_gross_exposure: string | null;
  max_daily_loss: string | null;
  max_orders_per_minute: number | null;
  max_orders_per_day: number | null;
  allow_short: boolean;
}

export const riskApi = {
  accountRiskState: (accountId: number) =>
    apiFetch<RiskState>(`/api/v1/accounts/${accountId}/risk-state`),
  resetCircuitBreaker: (accountId: number, confirmationText: string) =>
    apiFetch<{ ok: boolean }>(
      `/api/v1/accounts/${accountId}/risk/reset-circuit-breaker`,
      { method: "POST", body: JSON.stringify({ confirmation_text: confirmationText }) },
    ),
  listLimits: () =>
    apiFetch<{ items: RiskLimits[]; count: number }>("/api/v1/risk-limits"),
  updateLimits: (id: number, changes: Partial<RiskLimits>) =>
    apiFetch<RiskLimits>(`/api/v1/risk-limits/${id}`, {
      method: "PUT",
      body: JSON.stringify(changes),
    }),
  getAccount: (accountId: number) =>
    apiFetch<{ id: number; label: string }>(`/api/v1/accounts/${accountId}`),
};
