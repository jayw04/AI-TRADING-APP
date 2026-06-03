import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { proposalsApi, type Proposal, type ReviewRating } from "@/api/proposals";
import { EvalPanel } from "@/components/proposals/EvalPanel";

const STATE_CLASS: Record<string, string> = {
  DRAFT: "bg-neutral-800 text-neutral-300",
  REVIEWING: "bg-blue-900/50 text-blue-300",
  ACCEPTED: "bg-green-900/50 text-green-300",
  REJECTED: "bg-red-900/50 text-red-300",
  APPLIED: "bg-purple-900/50 text-purple-300",
};

function ReviewQueueItem({
  proposal,
  onSubmit,
  pending,
}: {
  proposal: Proposal;
  onSubmit: (rating: ReviewRating, reason?: string) => void;
  pending: boolean;
}) {
  const [reason, setReason] = useState("");
  const p = proposal.proposal_payload;

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-3">
      <div className="flex items-center gap-2">
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATE_CLASS[proposal.state] ?? STATE_CLASS.DRAFT}`}
        >
          {proposal.state}
        </span>
        {p.confidence && (
          <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs font-medium text-neutral-300">
            {p.confidence}
          </span>
        )}
        <span className="text-sm text-neutral-200">
          {p.summary ?? `Proposal #${proposal.id}`}
        </span>
        <span className="ml-auto text-xs text-neutral-500">
          strategy #{proposal.strategy_id}
        </span>
      </div>

      {p.rationale && (
        <p className="mt-2 text-xs text-neutral-300">{p.rationale}</p>
      )}

      {(p.changes ?? []).length > 0 && (
        <table className="mt-2 w-full text-left text-xs">
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

      <div className="mt-3 flex items-center gap-2">
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Optional reason…"
          rows={2}
          className="flex-1 rounded bg-neutral-800 px-2 py-1 text-xs text-neutral-200"
        />
        <button
          type="button"
          onClick={() => onSubmit("thumbs_up", reason || undefined)}
          disabled={pending}
          className="rounded bg-green-700 px-2.5 py-1 text-sm font-medium text-white hover:bg-green-600 disabled:opacity-50"
        >
          👍 Useful
        </button>
        <button
          type="button"
          onClick={() => onSubmit("thumbs_down", reason || undefined)}
          disabled={pending}
          className="rounded bg-red-900/70 px-2.5 py-1 text-sm font-medium text-red-200 hover:bg-red-800 disabled:opacity-50"
        >
          👎 Not useful
        </button>
      </div>
    </div>
  );
}

export default function ReviewQueue() {
  const queryClient = useQueryClient();

  const list = useQuery({
    queryKey: ["proposals", "awaiting_review"],
    queryFn: () => proposalsApi.listAwaitingReview(),
  });

  const review = useMutation({
    mutationFn: ({
      id,
      rating,
      reason,
    }: {
      id: number;
      rating: ReviewRating;
      reason?: string;
    }) => proposalsApi.review(id, rating, reason),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["proposals"] }),
  });

  const items = list.data?.items ?? [];

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-lg font-semibold text-neutral-100">
        Review Queue{items.length > 0 ? ` (${items.length})` : ""}
      </h1>
      <p className="mt-1 text-xs text-neutral-400">
        Sampled proposals from the past week. Your thumbs-up/down helps evaluate
        the agent's reasoning beyond what backtests can measure.
      </p>

      <div className="mt-4 space-y-2">
        {list.isLoading && (
          <div className="text-sm text-neutral-400">Loading review queue…</div>
        )}
        {!list.isLoading && items.length === 0 && (
          <div className="text-sm text-neutral-500">
            You're all caught up — no proposals awaiting review.
          </div>
        )}
        {items.map((p) => (
          <ReviewQueueItem
            key={p.id}
            proposal={p}
            pending={review.isPending}
            onSubmit={(rating, reason) =>
              review.mutate({ id: p.id, rating, reason })
            }
          />
        ))}
      </div>
    </div>
  );
}
