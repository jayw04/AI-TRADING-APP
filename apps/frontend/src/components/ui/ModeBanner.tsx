import { useQuery } from "@tanstack/react-query";
import { accountApi } from "@/api/account";
import { accountsApi } from "@/api/accounts";

export default function ModeBanner() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["account"],
    queryFn: accountApi.get,
    refetchInterval: 10_000,
    retry: false,
  });

  // P5 §1: a red LIVE banner shows whenever the user has ANY live account,
  // independent of which single account the AccountState endpoint resolves.
  // Best-effort — a missing/odd payload (e.g. in shells that stub fetch) just
  // yields zero live accounts rather than throwing.
  const accountsQuery = useQuery({
    queryKey: ["accounts"],
    queryFn: accountsApi.list,
    refetchInterval: 60_000,
    retry: false,
  });
  const items = accountsQuery.data?.items;
  const liveCount = Array.isArray(items)
    ? items.filter((a) => a.mode === "live").length
    : 0;

  if (liveCount > 0) {
    return (
      <div
        role="status"
        aria-label="Trading mode"
        className="flex items-center justify-center gap-2 bg-rose-700 py-1 text-xs font-bold uppercase tracking-wider text-white shadow-sm"
      >
        <span className="size-2 rounded-full bg-white animate-pulse" />
        {liveCount === 1
          ? "LIVE ACCOUNT — orders submitted to it move real money"
          : `${liveCount} LIVE ACCOUNTS — orders submitted to them move real money`}
      </div>
    );
  }

  if (data?.mode === "live") {
    return (
      <div
        role="status"
        aria-label="Trading mode"
        className="flex items-center justify-center gap-2 bg-rose-700 py-1 text-xs font-bold uppercase tracking-wider text-white shadow-sm"
      >
        <span className="size-2 rounded-full bg-white animate-pulse" />
        LIVE TRADING — real orders will be placed
      </div>
    );
  }
  if (data?.mode === "paper") {
    return (
      <div
        role="status"
        aria-label="Trading mode"
        className="flex items-center justify-center gap-2 bg-amber-500 py-1 text-xs font-bold uppercase tracking-wider text-amber-950"
      >
        <span className="size-2 rounded-full bg-amber-950" />
        PAPER TRADING — practice mode, no real orders
      </div>
    );
  }
  return (
    <div
      role="status"
      aria-label="Trading mode"
      className="flex items-center justify-center gap-2 bg-neutral-800 py-1 text-xs uppercase tracking-wider text-neutral-300"
    >
      <span className="size-2 rounded-full bg-neutral-500" />
      {error ? "Backend unreachable" : isLoading ? "Connecting…" : "Mode unknown"}
    </div>
  );
}
