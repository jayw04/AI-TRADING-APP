import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { riskApi } from "@/api/risk";
import type { RiskLimits as RiskLimitsRow } from "@/api/risk";
import { accountsApi } from "@/api/accounts";
import { RiskStateBanner } from "@/components/risk/RiskStateBanner";

const EDITABLE: { key: keyof RiskLimitsRow; label: string }[] = [
  { key: "max_position_qty", label: "Max position qty" },
  { key: "max_position_notional", label: "Max position notional ($)" },
  { key: "max_gross_exposure", label: "Max gross exposure ($)" },
  { key: "max_daily_loss", label: "Max daily loss ($)" },
  { key: "max_orders_per_minute", label: "Max orders / minute" },
  { key: "max_orders_per_day", label: "Max orders / day" },
];

function LimitsCard({ row }: { row: RiskLimitsRow }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    const init: Record<string, string> = {};
    for (const { key } of EDITABLE) {
      const v = row[key];
      init[key] = v === null || v === undefined ? "" : String(v);
    }
    setDraft(init);
  }, [row]);

  const save = useMutation({
    mutationFn: () => {
      const changes: Record<string, string> = {};
      for (const { key } of EDITABLE) {
        if (draft[key] !== "") changes[key] = draft[key];
      }
      return riskApi.updateLimits(row.id, changes as Partial<RiskLimitsRow>);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["risk-limits"] }),
  });

  const isLive = row.broker_mode === "live";

  return (
    <div
      className={`rounded-lg border p-4 ${
        isLive ? "border-red-800 bg-red-950/20" : "border-neutral-800 bg-neutral-900"
      }`}
    >
      <div className="mb-3 flex items-center gap-2">
        <span
          className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${
            isLive ? "bg-red-900/60 text-red-200" : "bg-neutral-800 text-neutral-300"
          }`}
        >
          {row.broker_mode}
        </span>
        <span className="text-xs text-neutral-500">{row.scope_type}</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {EDITABLE.map(({ key, label }) => (
          <label key={key} className="block text-xs text-neutral-400">
            {label}
            <input
              type="text"
              inputMode="decimal"
              value={draft[key] ?? ""}
              onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
              placeholder="unlimited"
              className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 font-mono text-sm text-white"
            />
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        {save.isError && <span className="text-xs text-red-300">Save failed.</span>}
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="rounded bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

export default function RiskLimits() {
  const limitsQuery = useQuery({ queryKey: ["risk-limits"], queryFn: riskApi.listLimits });
  const accountsQuery = useQuery({ queryKey: ["accounts"], queryFn: accountsApi.list });

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-lg font-semibold text-neutral-100">Risk Limits</h1>
      <p className="mt-1 text-xs text-neutral-400">
        Paper and live trading each have their own limits. Live defaults are conservative — raise
        them only deliberately. Edits are audit-logged.
      </p>

      {accountsQuery.data?.items?.map((a) => (
        <div key={a.id} className="mt-4">
          <RiskStateBanner accountId={a.id} accountLabel={a.label} />
        </div>
      ))}

      <div className="mt-6 space-y-3">
        {limitsQuery.isLoading && <div className="text-sm text-neutral-400">Loading…</div>}
        {limitsQuery.data?.items?.map((row) => <LimitsCard key={row.id} row={row} />)}
      </div>
    </div>
  );
}
