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

export type EvalStatus =
  | "pending"
  | "running"
  | "complete"
  | "skipped"
  | "failed";

export type ReviewRating = "thumbs_up" | "thumbs_down";

export interface HumanReview {
  sampled_at?: string;
  reviewed_at?: string | null;
  rating?: ReviewRating | null;
  reason?: string | null;
}

export interface EvaluationResults {
  status?: EvalStatus;
  skipped_reason?: string;
  failure_reason?: string;
  started_at?: string;
  completed_at?: string;
  window_days?: number;
  baseline_job_id?: number;
  variant_job_id?: number;
  baseline_metrics?: Record<string, number>;
  variant_metrics?: Record<string, number>;
  delta_metrics?: Record<string, number>;
  verdict?:
    | "above_baseline"
    | "below_baseline"
    | "insufficient_evidence"
    | "needs_review";
  human_review?: HumanReview;
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
  evaluation_results: EvaluationResults;
  generated_at: string;
  transitioned_at: string;
}

export interface ProposalEvalSummary {
  strategy_id: number;
  window_days: number;
  n_proposals: number;
  n_eval_complete: number;
  n_eval_pending: number;
  n_eval_skipped: number;
  n_eval_failed: number;
  n_above_baseline: number;
  n_below_baseline: number;
  n_insufficient_evidence?: number;
  n_needs_review?: number;
  recent_metrics_summary: Record<string, unknown> | null;
  n_reviewed: number;
  n_thumbs_up: number;
  n_thumbs_down: number;
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

  // P3 (review): re-run a failed/skipped eval without regenerating the proposal.
  rerunEval: (proposalId: number) =>
    apiFetch<Proposal>(`/api/v1/proposals/${proposalId}/rerun-eval`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  evalSummary: (strategyId: number, windowDays = 30) =>
    apiFetch<ProposalEvalSummary>(
      `/api/v1/strategies/${strategyId}/proposal-eval-summary?window=${windowDays}`,
    ),

  // P6 §2b-review: sampled-but-not-yet-rated proposals (the review queue).
  listAwaitingReview: () =>
    apiFetch<{ items: Proposal[] }>(
      `/api/v1/proposals?awaiting_review=true&limit=100`,
    ),

  review: (proposalId: number, rating: ReviewRating, reason?: string) =>
    apiFetch<Proposal>(`/api/v1/proposals/${proposalId}/review`, {
      method: "POST",
      body: JSON.stringify({ rating, ...(reason ? { reason } : {}) }),
    }),
};
