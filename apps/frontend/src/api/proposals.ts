import { apiFetch } from "./client";

export type ProposalState =
  | "DRAFT"
  | "REVIEWING"
  | "ACCEPTED"
  | "REJECTED"
  | "APPLIED";

export interface ProposalChange {
  param: string;
  from?: unknown;
  to?: unknown;
  reason?: string;
}

export interface Proposal {
  id: number;
  strategy_id: number;
  user_id: number;
  state: ProposalState;
  proposal_payload: {
    proposal_type?: string;
    changes?: ProposalChange[];
    confidence?: "LOW" | "MEDIUM" | "HIGH";
    summary?: string;
    rationale?: string;
  };
  evidence_bundle: Record<string, unknown>;
  evaluation_results: Record<string, unknown>;
  generated_at: string;
  transitioned_at: string;
}

function qs(params: Record<string, unknown>): string {
  const pairs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => [k, String(v)] as [string, string]);
  const s = new URLSearchParams(pairs).toString();
  return s ? `?${s}` : "";
}

export const proposalsApi = {
  list: (params: { strategy_id?: number; state?: ProposalState; limit?: number } = {}) =>
    apiFetch<{ items: Proposal[] }>(`/api/v1/proposals${qs(params)}`),

  get: (proposalId: number) => apiFetch<Proposal>(`/api/v1/proposals/${proposalId}`),

  propose: (strategyId: number) =>
    apiFetch<Proposal>(`/api/v1/strategies/${strategyId}/propose`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  accept: (proposalId: number, reviewNotes?: string) =>
    apiFetch<Proposal>(`/api/v1/proposals/${proposalId}`, {
      method: "PATCH",
      body: JSON.stringify({
        target_state: "ACCEPTED",
        ...(reviewNotes ? { review_notes: reviewNotes } : {}),
      }),
    }),

  reject: (proposalId: number, reason?: string) =>
    apiFetch<Proposal>(`/api/v1/proposals/${proposalId}`, {
      method: "PATCH",
      body: JSON.stringify({
        target_state: "REJECTED",
        ...(reason ? { rejection_reason: reason } : {}),
      }),
    }),

  apply: (proposalId: number) =>
    apiFetch<{ proposal_id: number; state: string; applied_changes: ProposalChange[] }>(
      `/api/v1/proposals/${proposalId}/apply`,
      { method: "POST", body: JSON.stringify({}) },
    ),
};
