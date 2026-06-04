import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { variantsApi } from "@/api/variants";

/**
 * P6b §2c-variant — Dashboard "Active Validations" widget. Lists the user's
 * in-flight paper variants, each linking to its parent strategy. React-query
 * (the Dashboard tree has the QueryClientProvider, cf. MorningBriefCard).
 *
 * Renders NOTHING when there are no in-flight variants — silence-when-empty is
 * the Dashboard convention; an empty widget would just be noise.
 */
export function VariantsCard() {
  const { data, isLoading } = useQuery({
    queryKey: ["variants", "in-flight"],
    queryFn: variantsApi.listInFlight,
    retry: false,
  });

  if (isLoading) return null;
  const items = data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <section className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
      <h3 className="text-sm font-semibold text-neutral-300 uppercase tracking-wide">
        Active validations ({items.length})
      </h3>
      <p className="text-sm text-neutral-400 mt-1">
        Paper variants validating accepted proposals against live behavior.
      </p>
      <ul className="mt-3 divide-y divide-neutral-800 text-sm">
        {items.map((v) => (
          <li key={v.variant_strategy_id} className="py-2">
            <Link
              to={`/strategies/${v.parent_strategy_id}`}
              className="flex items-center justify-between hover:text-sky-300"
            >
              <span className="font-semibold text-neutral-100">
                {v.parent_strategy_name ??
                  `Strategy #${v.parent_strategy_id ?? "—"}`}
              </span>
              <span className="text-[11px] text-neutral-500">
                {v.spawned_at
                  ? `Since ${new Date(v.spawned_at).toLocaleDateString()}`
                  : "—"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
