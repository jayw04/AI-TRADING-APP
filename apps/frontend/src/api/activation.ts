import { apiFetch } from "./client";

export interface Prerequisite {
  name: string;
  satisfied: boolean;
  detail: string;
}

export interface ActivationStatus {
  strategy_id: number;
  status: string;
  prerequisites: Prerequisite[];
  all_satisfied: boolean;
  initiated_at: string | null;
  completes_at: string | null;
  seconds_remaining: number;
}

export const activationApi = {
  status: (strategyId: number) =>
    apiFetch<ActivationStatus>(`/api/v1/strategies/${strategyId}/activation`),

  activate: (
    strategyId: number,
    body: { confirmation_name: string; totp_code: string },
  ) =>
    apiFetch<ActivationStatus>(`/api/v1/strategies/${strategyId}/activate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  cancelActivation: (strategyId: number) =>
    apiFetch<{ ok: boolean }>(`/api/v1/strategies/${strategyId}/activate/cancel`, {
      method: "POST",
      body: "{}",
    }),

  deactivate: (strategyId: number, liquidate: boolean) =>
    apiFetch<{ strategy_id: number; new_status: string; liquidation_orders: number[] }>(
      `/api/v1/strategies/${strategyId}/deactivate`,
      { method: "POST", body: JSON.stringify({ liquidate }) },
    ),
};
