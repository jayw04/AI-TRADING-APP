import OrderTicket from "@/components/ticket/OrderTicket";

export default function OpportunitiesPage() {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
        <h2 className="text-lg font-semibold text-neutral-100">Opportunities</h2>
        <p className="text-sm text-neutral-400 mt-1">
          Full discovery UI (scanners, watchlists, alerts) lands in P4. For now, this
          page hosts the order ticket so you can place paper orders end-to-end
          through the risk engine.
        </p>
        <ul className="text-sm text-neutral-300 mt-4 list-disc pl-5 space-y-1">
          <li>
            Live quotes refresh every 5s while a symbol is entered.
          </li>
          <li>
            Rejections from the risk engine show a plain-English explanation.
          </li>
          <li>
            See <span className="font-mono text-neutral-400">Orders</span> and{" "}
            <span className="font-mono text-neutral-400">Positions</span> pages for
            outcomes.
          </li>
        </ul>
      </div>
      <OrderTicket />
    </div>
  );
}
