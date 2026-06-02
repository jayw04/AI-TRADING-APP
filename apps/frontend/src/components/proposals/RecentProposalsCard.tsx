import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { proposalsApi, type ProposalState } from "@/api/proposals";

const STATE_CLASS: Record<ProposalState, string> = {
  DRAFT: "bg-neutral-800 text-neutral-300",
  REVIEWING: "bg-blue-900/50 text-blue-300",
  ACCEPTED: "bg-green-900/50 text-green-300",
  REJECTED: "bg-red-900/50 text-red-300",
  APPLIED: "bg-purple-900/50 text-purple-300",
};

export default function RecentProposalsCard() {
  const list = useQuery({
    queryKey: ["proposals", "list", "ALL"],
    queryFn: () => proposalsApi.list({ limit: 5 }),
    retry: false,
  });

  const items = list.data?.items ?? [];

  return (
    <section className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-neutral-300 uppercase tracking-wide">
          Recent Proposals
        </h3>
        <Link to="/proposals" className="text-xs text-blue-400 hover:underline">
          View all
        </Link>
      </div>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-neutral-500">
          No proposals yet. Generate one from the{" "}
          <Link to="/proposals" className="text-blue-400 hover:underline">
            Proposals page
          </Link>
          .
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((p) => (
            <li key={p.id} className="flex items-center gap-2 text-sm">
              <span
                className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATE_CLASS[p.state]}`}
              >
                {p.state}
              </span>
              <span className="truncate text-neutral-200">
                {p.proposal_payload.summary ?? `Proposal #${p.id}`}
              </span>
              <span className="ml-auto text-xs text-neutral-500">
                #{p.strategy_id}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
