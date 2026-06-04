import { useCallback, useEffect, useState } from "react";
import type { Strategy } from "@/api/types";
import { proposalsApi, type Proposal } from "@/api/proposals";
import {
  variantsApi,
  type VariantComparison,
  type VariantComparisonResponse,
  type EquityCurvePoint,
} from "@/api/variants";

interface Props {
  strategy: Strategy;
}

/**
 * P6b §2c-variant — paper-variant ("validation") card on the strategy detail
 * page. Three states:
 *   - active:   an in-flight variant → metrics table + equity chart + Stop
 *   - eligible: LIVE parent + an ACCEPTED proposal → Validate button
 *   - empty:    neither → advisory message
 *
 * Plain useState/useEffect (not React Query) to match DriftCard — the strategy
 * detail page manages its own data without a QueryClientProvider. UI vocabulary
 * is "validation," not "variant" (the backend `auto_validate_proposals` concept).
 */
export function VariantCard({ strategy }: Props) {
  const [resp, setResp] = useState<VariantComparisonResponse | null>(null);
  const [eligible, setEligible] = useState<Proposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [comparison, proposals] = await Promise.all([
        variantsApi.comparison(strategy.id),
        proposalsApi.list({ strategy_id: strategy.id, state: "ACCEPTED" }),
      ]);
      setResp(comparison);
      // Most-recent ACCEPTED proposal (the candidate to validate).
      const latest = (proposals.items ?? [])
        .slice()
        .sort(
          (a, b) =>
            new Date(b.generated_at).getTime() -
            new Date(a.generated_at).getTime(),
        )[0];
      setEligible(latest ?? null);
    } catch {
      /* advisory card — keep prior state on a transient failure */
    } finally {
      setLoading(false);
    }
  }, [strategy.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onValidate(proposalId: number) {
    if (!window.confirm("Spawn a paper variant to validate this proposal?")) return;
    setPending(true);
    setError(null);
    try {
      await variantsApi.validate(proposalId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start validation");
    } finally {
      setPending(false);
    }
  }

  async function onStop(proposalId: number) {
    if (!window.confirm("Stop validation and terminate the paper variant?")) return;
    setPending(true);
    setError(null);
    try {
      await variantsApi.stopValidation(proposalId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to stop validation");
    } finally {
      setPending(false);
    }
  }

  const active =
    resp?.status === "variant_active" && resp.comparison
      ? resp.comparison
      : null;

  return (
    <div className="rounded border border-neutral-800 bg-neutral-950 p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-neutral-300">
        Validation
      </div>

      {error && <div className="mt-2 text-[11px] text-rose-400">{error}</div>}

      {loading && !resp && (
        <div className="mt-2 text-[11px] text-neutral-500">Loading…</div>
      )}

      {!loading &&
        (active ? (
          <ActiveValidation
            comparison={active}
            pending={pending}
            onStop={onStop}
          />
        ) : eligible && strategy.status === "live" ? (
          <EligibleProposal
            proposal={eligible}
            pending={pending}
            onValidate={onValidate}
          />
        ) : (
          <div className="mt-2 text-[11px] text-neutral-400">
            No active validation. Accept a proposal on this live strategy to
            validate it on a paper variant.
          </div>
        ))}
    </div>
  );
}

function EligibleProposal({
  proposal,
  pending,
  onValidate,
}: {
  proposal: Proposal;
  pending: boolean;
  onValidate: (proposalId: number) => void;
}) {
  const summary = proposal.proposal_payload?.summary ?? `Proposal #${proposal.id}`;
  return (
    <div className="mt-2 space-y-2">
      <div className="text-[11px] text-neutral-400">
        Accepted proposal awaiting validation:
      </div>
      <div className="text-[11px] text-neutral-200">{summary}</div>
      <button
        type="button"
        onClick={() => onValidate(proposal.id)}
        disabled={pending}
        className="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
      >
        {pending ? "Starting…" : "Validate this proposal"}
      </button>
    </div>
  );
}

function ActiveValidation({
  comparison,
  pending,
  onStop,
}: {
  comparison: VariantComparison;
  pending: boolean;
  onStop: (proposalId: number) => void;
}) {
  return (
    <div className="mt-2 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[11px]">
          <span className="rounded bg-sky-900/50 px-1.5 py-0.5 font-semibold text-sky-200">
            Validating
          </span>
          <span className="text-neutral-500">
            Since {new Date(comparison.window_start).toLocaleDateString()}
          </span>
        </div>
        <button
          type="button"
          onClick={() =>
            comparison.spawn_proposal_id != null &&
            onStop(comparison.spawn_proposal_id)
          }
          disabled={pending || comparison.spawn_proposal_id == null}
          className="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
        >
          {pending ? "Stopping…" : "Stop validation"}
        </button>
      </div>

      <MetricsTable comparison={comparison} />
      <VariantEquityChart
        live={comparison.live_equity_curve}
        variant={comparison.variant_equity_curve}
      />
    </div>
  );
}

function MetricsTable({ comparison }: { comparison: VariantComparison }) {
  const lm = comparison.live_metrics;
  const vm = comparison.variant_metrics;
  const d = comparison.deltas;

  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
  const pct2 = (v: number) => `${(v * 100).toFixed(2)}%`;
  const num = (v: number) => v.toFixed(2);
  const dPct = (v: number | null) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  const dPp = (v: number | null) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)} pp`;

  return (
    <table className="w-full text-[11px]">
      <thead>
        <tr className="text-neutral-500">
          <th className="text-left font-normal">Metric</th>
          <th className="text-right font-normal">Live</th>
          <th className="text-right font-normal">Variant</th>
          <th className="text-right font-normal">Δ</th>
        </tr>
      </thead>
      <tbody className="text-neutral-200">
        <tr>
          <td className="text-neutral-400">Trades</td>
          <td className="text-right font-mono">{comparison.live_trade_count}</td>
          <td className="text-right font-mono">{comparison.variant_trade_count}</td>
          <td className="text-right font-mono text-neutral-500">—</td>
        </tr>
        <tr>
          <td className="text-neutral-400">Win rate</td>
          <td className="text-right font-mono">{pct(lm.win_rate)}</td>
          <td className="text-right font-mono">{pct(vm.win_rate)}</td>
          <td className="text-right font-mono">{dPp(d.win_rate_delta_pp)}</td>
        </tr>
        <tr>
          <td className="text-neutral-400">Avg return/trade</td>
          <td className="text-right font-mono">{pct2(lm.avg_return_per_trade)}</td>
          <td className="text-right font-mono">{pct2(vm.avg_return_per_trade)}</td>
          <td className="text-right font-mono">{dPct(d.avg_return_delta_pct)}</td>
        </tr>
        <tr>
          <td className="text-neutral-400">Sharpe</td>
          <td className="text-right font-mono">{num(lm.sharpe_ratio)}</td>
          <td className="text-right font-mono">{num(vm.sharpe_ratio)}</td>
          <td className="text-right font-mono">{dPct(d.sharpe_delta_pct)}</td>
        </tr>
        <tr>
          <td className="text-neutral-400">Max drawdown</td>
          <td className="text-right font-mono">{pct(lm.max_drawdown)}</td>
          <td className="text-right font-mono">{pct(vm.max_drawdown)}</td>
          <td className="text-right font-mono">{dPct(d.max_drawdown_delta_pct)}</td>
        </tr>
      </tbody>
    </table>
  );
}

// Two-series inline SVG (zero-dependency, like BacktestResultsView's chart).
// Live = gray (#6b7280), variant = blue (#3b82f6) — both color-blind-safe.
const CHART_W = 480;
const CHART_H = 150;
const CHART_PAD = { top: 8, right: 8, bottom: 8, left: 8 };

function VariantEquityChart({
  live,
  variant,
}: {
  live: EquityCurvePoint[];
  variant: EquityCurvePoint[];
}) {
  const all = [...live, ...variant];
  if (all.length < 2) {
    return (
      <div className="py-4 text-center text-[11px] text-neutral-500">
        Not enough equity history to chart yet.
      </div>
    );
  }

  const times = all.map((p) => new Date(p.ts).getTime());
  const vals = all.map((p) => p.equity);
  const tMin = Math.min(...times);
  const tMax = Math.max(...times);
  const vMin = Math.min(...vals);
  const vMax = Math.max(...vals);
  const vPad = (vMax - vMin) * 0.08 || 1;
  const yMin = vMin - vPad;
  const yMax = vMax + vPad;

  const w = CHART_W - CHART_PAD.left - CHART_PAD.right;
  const h = CHART_H - CHART_PAD.top - CHART_PAD.bottom;
  const xScale = (t: number) =>
    CHART_PAD.left + ((t - tMin) / (tMax - tMin || 1)) * w;
  const yScale = (v: number) =>
    CHART_PAD.top + (1 - (v - yMin) / (yMax - yMin || 1)) * h;

  const toPath = (pts: EquityCurvePoint[]) =>
    pts
      .map(
        (p, i) =>
          `${i === 0 ? "M" : "L"} ${xScale(new Date(p.ts).getTime()).toFixed(1)} ${yScale(p.equity).toFixed(1)}`,
      )
      .join(" ");

  return (
    <div>
      <svg
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        preserveAspectRatio="none"
        style={{ width: "100%", height: CHART_H }}
        role="img"
        aria-label="Variant versus live equity"
      >
        {live.length >= 2 && (
          <path d={toPath(live)} fill="none" stroke="#6b7280" strokeWidth={1.5} />
        )}
        {variant.length >= 2 && (
          <path d={toPath(variant)} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
        )}
      </svg>
      <div className="mt-1 flex gap-3 text-[10px] text-neutral-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-3 bg-neutral-500" /> Live
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-3 bg-sky-500" /> Variant
        </span>
      </div>
    </div>
  );
}
