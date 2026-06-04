import { apiFetch } from "./client";

// Mirrors the backend VariantSideMetrics dataclass (P6b §2b). All five fields
// are non-null numbers — the metric functions return 0.0, never null.
export interface VariantSideMetrics {
  trade_count: number;
  win_rate: number;
  avg_return_per_trade: number;
  sharpe_ratio: number;
  max_drawdown: number;
}

// Deltas CAN be null (the backend `_pct_delta` returns None on a zero/None
// denominator).
export interface VariantDeltas {
  sharpe_delta_pct: number | null;
  max_drawdown_delta_pct: number | null;
  win_rate_delta_pp: number | null;
  avg_return_delta_pct: number | null;
}

export interface EquityCurvePoint {
  ts: string; // ISO datetime
  equity: number;
}

// P6b §3a evidence bundle (minimal shape the promote UI reads).
export interface GateCriterion {
  name: string;
  passed: boolean;
  details: Record<string, unknown>;
}

export interface EvidenceBundle {
  captured_at: string;
  all_criteria_passed: boolean;
  gate_results: {
    duration: GateCriterion;
    sharpe_margin: GateCriterion;
    absolute_return: GateCriterion;
    drawdown_divergence: GateCriterion;
  };
}

// Lifecycle states the variant card sub-renders on (P6b §3b).
export type ProposalLifecycleState =
  | "EVALUATING"
  | "EVIDENCE_READY"
  | "PROMOTING"
  | "PROMOTED";

export interface VariantComparison {
  parent_strategy_id: number;
  variant_strategy_id: number;
  spawn_proposal_id: number | null;
  window_start: string;
  window_end: string;
  live_metrics: VariantSideMetrics;
  variant_metrics: VariantSideMetrics;
  deltas: VariantDeltas;
  live_trade_count: number;
  variant_trade_count: number;
  live_equity_curve: EquityCurvePoint[];
  variant_equity_curve: EquityCurvePoint[];
  // P6b §3b additive fields.
  proposal_state?: ProposalLifecycleState | null;
  evidence_bundle?: EvidenceBundle | null;
  eligible_for_promotion?: boolean;
  parent_last_promoted_at?: string | null;
}

export interface VariantComparisonResponse {
  status: "no_active_variant" | "variant_active";
  strategy_id: number;
  variant_strategy_id?: number;
  comparison?: VariantComparison;
  // Always present so the card can render the post-promotion lockout state.
  parent_last_promoted_at?: string | null;
}

export interface InFlightVariant {
  variant_strategy_id: number;
  parent_strategy_id: number | null;
  parent_strategy_name: string | null;
  parent_strategy_status: string | null;
  spawn_proposal_id: number | null;
  spawned_at: string | null;
}

export const variantsApi = {
  // Per-strategy comparison (keyed by the PARENT strategy id).
  comparison: (strategyId: number) =>
    apiFetch<VariantComparisonResponse>(
      `/api/v1/strategies/${strategyId}/variant-comparison`,
    ),

  // User-scoped in-flight variants for the Dashboard widget.
  listInFlight: () =>
    apiFetch<{ items: InFlightVariant[] }>(`/api/v1/variants`),

  // Spawn a paper variant for an ACCEPTED proposal (§2a endpoint).
  validate: (proposalId: number) =>
    apiFetch<unknown>(`/api/v1/proposals/${proposalId}/validate`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // Terminate the in-flight variant (§2a endpoint).
  stopValidation: (proposalId: number) =>
    apiFetch<unknown>(`/api/v1/proposals/${proposalId}/stop-validation`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // P6b §3b: user-gated promotion (EVIDENCE_READY → PROMOTING, 24h cooldown).
  promote: (proposalId: number) =>
    apiFetch<unknown>(`/api/v1/proposals/${proposalId}/promote`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // P6b §3b: reject evidence (EVIDENCE_READY) or cancel cooldown (PROMOTING) →
  // REJECTED terminal. Same endpoint serves both UX moments.
  rejectPromotion: (proposalId: number) =>
    apiFetch<unknown>(`/api/v1/proposals/${proposalId}/reject-promotion`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
