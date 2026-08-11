import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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

/** How long the "Saved" confirmation stays on screen. */
const SAVED_NOTICE_MS = 6000;

/** Render a stored limit for humans: the API returns Decimals as strings
 * ("100000.0000"), and echoing that back in a confirmation reads like a
 * different number than the one the user typed. */
function display(v: unknown): string {
  if (v === null || v === undefined || v === "") return "unlimited";
  const n = Number(v);
  return Number.isNaN(n) ? String(v) : String(n);
}

/** Is the typed value the same limit as the stored one? Compares numerically
 * so "110000" and the server's "110000.0000" are recognised as equal —
 * otherwise every re-save looks dirty and writes an empty-diff audit entry
 * (observed 2026-08-10: a duplicate save produced changes {old:{},new:{}}). */
function unchanged(typed: string, stored: unknown): boolean {
  const s = stored === null || stored === undefined ? "" : String(stored);
  if (typed === s) return true;
  if (typed.trim() === "" || s.trim() === "") return false;
  const a = Number(typed);
  const b = Number(s);
  return !Number.isNaN(a) && !Number.isNaN(b) && a === b;
}

function LimitsCard({ row }: { row: RiskLimitsRow }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    const init: Record<string, string> = {};
    for (const { key } of EDITABLE) {
      const v = row[key];
      init[key] = v === null || v === undefined ? "" : String(v);
    }
    setDraft(init);
  }, [row]);

  // The confirmation is transient: it answers "did that work?" and then gets
  // out of the way, so it can never be mistaken for the current saved state.
  useEffect(() => {
    if (saved === null) return;
    const t = setTimeout(() => setSaved(null), SAVED_NOTICE_MS);
    return () => clearTimeout(t);
  }, [saved]);

  // Fields the user actually altered. Drives both the disabled state and the
  // confirmation text, so the two can never disagree.
  const changed = EDITABLE.filter(
    ({ key }) => draft[key] !== undefined && draft[key] !== "" && !unchanged(draft[key], row[key]),
  ).map(({ key, label }) => ({
    key,
    label: label.replace(/ \(\$\)$/, ""),
    from: display(row[key]),
    to: display(draft[key]),
  }));

  const save = useMutation({
    mutationFn: (v: { payload: Record<string, string>; summary: string; close: boolean }) =>
      riskApi.updateLimits(row.id, v.payload as Partial<RiskLimitsRow>),
    onSuccess: (_data, v) => {
      queryClient.invalidateQueries({ queryKey: ["risk-limits"] });
      if (v.close) navigate("/settings");
      else setSaved(v.summary);
    },
  });

  function submit(close: boolean) {
    if (changed.length === 0) return;
    // Send only what changed. The endpoint diffs server-side anyway, but a
    // minimal payload keeps the audit entry's `changes` free of no-op fields.
    const payload = Object.fromEntries(changed.map((c) => [c.key, c.to]));
    const summary = changed.map((c) => `${c.label} ${c.from} → ${c.to}`).join(" · ");
    save.mutate({ payload, summary, close });
  }

  const isLive = row.broker_mode === "live";
  const blocked = save.isPending || changed.length === 0;

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
              onChange={(e) => {
                setSaved(null); // a stale "Saved" must not sit beside a fresh edit
                setDraft((d) => ({ ...d, [key]: e.target.value }));
              }}
              placeholder="unlimited"
              className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 font-mono text-sm text-white"
            />
          </label>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        {save.isError && <span className="text-xs text-red-300">Save failed.</span>}
        {saved !== null && !save.isError && (
          <span role="status" className="mr-auto text-xs font-medium text-green-300">
            ✓ Saved · {saved}
          </span>
        )}
        {saved === null && changed.length > 0 && !save.isPending && (
          <span className="mr-auto text-xs text-neutral-500">
            {changed.length} unsaved change{changed.length === 1 ? "" : "s"}
          </span>
        )}
        <button
          type="button"
          onClick={() => submit(false)}
          disabled={blocked}
          className="rounded bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700 disabled:text-neutral-400"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={() => submit(true)}
          disabled={blocked}
          className="rounded border border-neutral-600 px-3 py-1.5 text-xs font-semibold text-neutral-200 hover:bg-neutral-800 disabled:border-neutral-800 disabled:text-neutral-500"
        >
          Save &amp; close
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
