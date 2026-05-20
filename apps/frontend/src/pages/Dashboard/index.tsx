import { useQuery } from "@tanstack/react-query";
import { getAccount } from "../../api/account";

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["account"],
    queryFn: getAccount,
  });

  return (
    <div className="grid gap-4">
      <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
        <h2 className="text-lg font-semibold text-neutral-100">Dashboard</h2>
        <p className="text-sm text-neutral-400 mt-1">
          P0 placeholder. Real widgets land in P1+.
        </p>
      </div>

      <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
        <h3 className="text-sm font-semibold text-neutral-300 uppercase tracking-wide">
          Account (from <code className="text-neutral-400">/api/v1/account</code>)
        </h3>
        {isLoading && <p className="text-neutral-400 text-sm mt-2">Loading…</p>}
        {error && (
          <p className="text-rose-400 text-sm mt-2">
            Backend unreachable: {(error as Error).message}
          </p>
        )}
        {data && (
          <pre className="mt-2 text-sm text-neutral-200 bg-neutral-950 border border-neutral-800 rounded p-3 overflow-x-auto">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
