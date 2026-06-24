import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { proposalsApi, type Proposal, type ProposalState } from "@/api/proposals";
import { tradingProfileApi } from "@/api/tradingProfile";
import { EvalBadge, EvalPanel } from "@/components/proposals/EvalPanel";

const STATE_FILTERS: Array<{ label: string; value: ProposalState | "ALL" }> = [
  { label: "All", value: "ALL" },
  { label: "Reviewing", value: "REVIEWING" },
  { label: "Accepted", value: "ACCEPTED" },
  { label: "Applied", value: "APPLIED" },
  { label: "Rejected", value: "REJECTED" },
];

const STATE_CLASS: Record<ProposalState, string> = {
  DRAFT: "bg-neutral-800 text-neutral-300",
  REVIEWING: "bg-blue-900/50 text-blue-300",
  ACCEPTED: "bg-green-900/50 text-green-300",
  REJECTED: "bg-red-900/50 text-red-300",
  APPLIED: "bg-purple-900/50 text-purple-300",
};

const CONFIDENCE_CLASS: Record<string, string> = {
  LOW: "bg-neutral-800 text-neutral-400",
  MEDIUM: "bg-blue-900/50 text-blue-300",
  HIGH: "bg-green-900/50 text-green-300",
};

function StateBadge({ state }: { state: ProposalState }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATE_CLASS[state]}`}>
      {state}
    </span>
  );
}

function ConfidenceBadge({ confidence }: { confidence?: string }) {
  if (!confidence) return null;
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs font-medium ${CONFIDENCE_CLASS[confidence] ?? CONFIDENCE_CLASS.LOW}`}
    >
      {confidence}
    </span>
  );
}

function ProposalDetail({ proposal }: { proposal: Proposal }) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["proposals"] });

  const accept = useMutation({
    mutationFn: () => proposalsApi.accept(proposal.id),
    onSuccess: invalidate,
  });
  const reject = useMutation({
    mutationFn: () => proposalsApi.reject(proposal.id, "rejected from UI"),
    onSuccess: invalidate,
  });
  const apply = useMutation({
    mutationFn: () => proposalsApi.apply(proposal.id),
    onSuccess: invalidate,
  });
  const rerunEval = useMutation({
    mutationFn: () => proposalsApi.rerunEval(proposal.id),
    onSuccess: invalidate,
  });

  const p = proposal.proposal_payload;
  return (
    <div className="mt-2 rounded border border-neutral-800 bg-neutral-950 p-3 text-xs">
      {p.rationale && <p className="text-neutral-300">{p.rationale}</p>}
      {(p.changes ?? []).length > 0 && (
        <table className="mt-2 w-full text-left">
          <thead className="text-neutral-500">
            <tr>
              <th className="pr-2">Param</th>
              <th className="pr-2">From</th>
              <th className="pr-2">To</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody className="text-neutral-300">
            {(p.changes ?? []).map((c, i) => (
              <tr key={i}>
                <td className="pr-2 font-mono">{c.param}</td>
                <td className="pr-2 font-mono">{String(c.from)}</td>
                <td className="pr-2 font-mono">{String(c.to)}</td>
                <td>{c.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <EvalPanel ev={proposal.evaluation_results} />
      {proposal.evaluation_results?.status === "failed" && (
        <button
          type="button"
          onClick={() => rerunEval.mutate()}
          disabled={rerunEval.isPending}
          className="mt-2 rounded bg-blue-900/50 px-2 py-1 text-xs font-medium text-blue-300 hover:bg-blue-900/70 disabled:opacity-50"
        >
          {rerunEval.isPending ? "Re-running…" : "Re-run evaluation"}
        </button>
      )}

      <details className="mt-2">
        <summary className="cursor-pointer text-neutral-500">Evidence bundle</summary>
        <pre className="mt-1 overflow-x-auto rounded bg-black/40 p-2 text-[10px] text-neutral-400">
          {JSON.stringify(proposal.evidence_bundle, null, 2)}
        </pre>
      </details>

      <div className="mt-3 flex gap-2">
        {proposal.state === "REVIEWING" && (
          <>
            <button
              type="button"
              onClick={() => accept.mutate()}
              disabled={accept.isPending}
              className="rounded bg-green-700 px-2.5 py-1 font-medium text-white hover:bg-green-600 disabled:opacity-50"
            >
              Accept
            </button>
            <button
              type="button"
              onClick={() => reject.mutate()}
              disabled={reject.isPending}
              className="rounded bg-red-900/70 px-2.5 py-1 font-medium text-red-200 hover:bg-red-800 disabled:opacity-50"
            >
              Reject
            </button>
          </>
        )}
        {proposal.state === "ACCEPTED" && (
          <button
            type="button"
            onClick={() => {
              if (
                window.confirm(
                  "Apply this proposal? It mutates the strategy's parameters (the strategy must be idle).",
                )
              ) {
                apply.mutate();
              }
            }}
            disabled={apply.isPending}
            className="rounded bg-purple-700 px-2.5 py-1 font-medium text-white hover:bg-purple-600 disabled:opacity-50"
          >
            Apply to strategy
          </button>
        )}
        {apply.isError && (
          <span className="text-red-300">Apply failed (is the strategy idle?).</span>
        )}
      </div>
    </div>
  );
}

export default function Proposals() {
  const [filter, setFilter] = useState<ProposalState | "ALL">("ALL");
  const [openId, setOpenId] = useState<number | null>(null);
  const [strategyId, setStrategyId] = useState<number | "">("");
  const queryClient = useQueryClient();

  const profile = useQuery({
    queryKey: ["trading-profile"],
    queryFn: tradingProfileApi.get,
  });
  const hideLow = Boolean(
    (profile.data?.agent_envelope as Record<string, unknown> | undefined)
      ?.hide_low_confidence_proposals,
  );

  const strategies = useQuery({
    queryKey: ["strategies", "for-proposals"],
    queryFn: () => apiFetch<{ items: Array<{ id: number; name: string }> }>("/api/v1/strategies"),
  });

  const list = useQuery({
    queryKey: ["proposals", "list", filter],
    queryFn: () =>
      proposalsApi.list(filter === "ALL" ? {} : { state: filter }),
  });

  const awaiting = useQuery({
    queryKey: ["proposals", "awaiting_review"],
    queryFn: () => proposalsApi.listAwaitingReview(),
    retry: false,
  });
  const awaitingCount = awaiting.data?.items.length ?? 0;

  const generate = useMutation({
    mutationFn: (sid: number) => proposalsApi.propose(sid),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["proposals"] }),
  });

  const items = (list.data?.items ?? []).filter(
    (p) => !(hideLow && p.proposal_payload.confidence === "LOW"),
  );

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-neutral-100">Strategy Proposals</h1>
        {awaitingCount > 0 && (
          <Link
            to="/proposals/review"
            className="rounded bg-amber-900/50 px-2 py-1 text-xs font-medium text-amber-300 hover:bg-amber-900/70"
          >
            {awaitingCount} awaiting review
          </Link>
        )}
      </div>
      <p className="mt-1 text-xs text-neutral-400">
        Pick one of <span className="text-neutral-200">your existing strategies</span> below — the
        agent suggests <span className="text-neutral-200">parameter adjustments</span> for it (e.g.
        entry/exit levels, position sizing). This page tunes strategies you already created; it does
        not screen or pick tickers. You review, accept, and explicitly apply — nothing changes until
        you do.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-neutral-800 bg-neutral-900 p-3">
        <select
          value={strategyId}
          onChange={(e) => setStrategyId(e.target.value === "" ? "" : Number(e.target.value))}
          className="rounded bg-neutral-800 px-2 py-1 text-sm text-white"
        >
          <option value="">Select one of your strategies…</option>
          {(strategies.data?.items ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} (#{s.id})
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={strategyId === "" || generate.isPending}
          onClick={() => strategyId !== "" && generate.mutate(strategyId)}
          className="rounded bg-blue-700 px-3 py-1 text-sm font-medium text-white hover:bg-blue-600 disabled:opacity-50"
        >
          {generate.isPending ? "Generating…" : "Generate proposal"}
        </button>
        {generate.isError && (
          <span className="text-xs text-red-300">Generation failed or was budget-rejected.</span>
        )}
      </div>

      <div className="mt-4 flex gap-2">
        {STATE_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => setFilter(f.value)}
            className={`rounded px-2.5 py-1 text-xs ${
              filter === f.value
                ? "bg-blue-700 text-white"
                : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-2">
        {list.isLoading && <div className="text-sm text-neutral-400">Loading…</div>}
        {!list.isLoading && items.length === 0 && (
          <div className="text-sm text-neutral-500">No proposals yet.</div>
        )}
        {items.map((p) => (
          <div
            key={p.id}
            className="rounded-lg border border-neutral-800 bg-neutral-900 p-3"
          >
            <button
              type="button"
              onClick={() => setOpenId(openId === p.id ? null : p.id)}
              className="flex w-full items-center justify-between text-left"
            >
              <div className="flex items-center gap-2">
                <StateBadge state={p.state} />
                <ConfidenceBadge confidence={p.proposal_payload.confidence} />
                <EvalBadge ev={p.evaluation_results} />
                <span className="text-sm text-neutral-200">
                  {p.proposal_payload.summary ?? `Proposal #${p.id}`}
                </span>
              </div>
              <span className="text-xs text-neutral-500">strategy #{p.strategy_id}</span>
            </button>
            {openId === p.id && <ProposalDetail proposal={p} />}
          </div>
        ))}
      </div>
    </div>
  );
}
