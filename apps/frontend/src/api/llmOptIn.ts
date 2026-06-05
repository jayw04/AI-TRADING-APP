import { apiFetch } from "./client";

export interface OptInEligibility {
  eligible: boolean;
  b_trade_count: number;
  window_days: number;
  min_trades: number;
  min_days: number;
  harness_active: boolean;
  reasons: string[];
}

export interface LLMOptInStatus {
  status: "none" | "pending" | "active";
  strategy_id: number;
  opt_in_id?: number;
  seconds_remaining?: number;
  daily_cap_cents?: number;
  spend_today_cents?: number;
  eligibility: OptInEligibility | null;
}

export const llmOptInApi = {
  status: (strategyId: number) =>
    apiFetch<LLMOptInStatus>(`/api/v1/strategies/${strategyId}/llm-opt-in`),

  optIn: (strategyId: number, acknowledgment_text: string, totp_code: string) =>
    apiFetch<{ status: string; opt_in_id: number; activates_at: string }>(
      `/api/v1/strategies/${strategyId}/llm-opt-in`,
      { method: "POST", body: JSON.stringify({ acknowledgment_text, totp_code }) },
    ),

  optOut: (strategyId: number) =>
    apiFetch<{ status: string }>(`/api/v1/strategies/${strategyId}/llm-opt-out`, {
      method: "POST",
      body: "{}",
    }),
};

export const RISK_ACK_PHRASE =
  "I understand LLM-driven trading is non-deterministic and I accept the risk";
