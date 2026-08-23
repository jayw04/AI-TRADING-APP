import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { opportunitiesApi } from "@/api/opportunities";
import type { OppHistoryCheckpoint, OppHistoryOccurrence } from "@/api/types";

const OFFSET_CHECKPOINTS = ["D1", "D5", "D10", "D20"] as const;

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return "—";
  return `$${v.toFixed(2)}`;
}

function fmtChange(v: number | null | undefined): string {
  if (v == null) return "—";
  const pct = v * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function changeClass(v: number | null | undefined): string {
  if (v == null) return "text-neutral-500";
  if (v > 0) return "text-emerald-300";
  if (v < 0) return "text-rose-300";
  return "text-neutral-400";
}

function chipLine(row: OppHistoryOccurrence): string {
  const chips = row.reason.chips ?? [];
  return chips.map((c) => c.value).join(" · ");
}

function checkpointMap(
  row: OppHistoryOccurrence,
): Record<string, OppHistoryCheckpoint> {
  return Object.fromEntries(row.checkpoints.map((c) => [c.checkpoint, c]));
}

function CheckpointStrip({ row }: { row: OppHistoryOccurrence }) {
  const byName = checkpointMap(row);
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 font-mono text-[10px] text-neutral-400">
      <span className="uppercase tracking-wide text-neutral-500">
        {row.family} · {row.horizon}
      </span>
      {OFFSET_CHECKPOINTS.map((name) => {
        const cp = byName[name];
        const pending = cp == null || cp.price == null;
        const mixed = !pending && cp.return_pct == null;
        return (
          <span key={name} title={mixed ? "later SEP print; return withheld (basis differs)" : undefined}>
            <span className="text-neutral-500">{name}</span>{" "}
            <span className={changeClass(cp?.return_pct)}>
              {pending ? "—" : fmtChange(cp.return_pct)}
            </span>
          </span>
        );
      })}
    </div>
  );
}

export default function OpportunityHistoryPage() {
  const [rows, setRows] = useState<OppHistoryOccurrence[]>([]);
  const [timeline, setTimeline] = useState<OppHistoryOccurrence[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await opportunitiesApi.history();
      setRows(resp.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openSymbol = async (symbol: string) => {
    if (selected === symbol) {
      setSelected(null);
      setTimeline([]);
      return;
    }
    setSelected(symbol);
    try {
      const resp = await opportunitiesApi.history({ symbol });
      setTimeline(resp.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-neutral-100">
            Opportunity History
          </h2>
          <p className="text-xs text-neutral-500">
            Durable DISC-001 occurrences. Current return and D1/D5/D10/D20 are
            live SEP on the proposal adjustment basis — not stored, not a
            signal, and not a hold period. GAP later SEP prints are facts
            without a mixed-basis return. “Why it left” re-evaluates the
            frozen family rule on a later Sharadar/GAP print — frozen-rule
            display, not a sell or exit signal.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/opportunities"
            className="rounded border border-neutral-800 bg-neutral-900 px-3 py-1 text-sm text-neutral-200 hover:bg-neutral-800"
          >
            Watchlist
          </Link>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="rounded border border-neutral-800 bg-neutral-900 px-3 py-1 text-sm text-neutral-200 hover:bg-neutral-800 disabled:opacity-60"
          >
            {loading ? "…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded border border-rose-800 bg-rose-950/40 p-2 text-sm text-rose-200">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-neutral-800 bg-neutral-900">
        {rows.length === 0 ? (
          <div className="py-8 text-center text-sm text-neutral-500">
            No durable occurrences yet. They appear after the 16:20 ET snapshot
            job ingests a CandidateSnapshot.
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-neutral-800 text-[10px] uppercase tracking-wide text-neutral-500">
              <tr>
                <th className="px-3 py-2 font-medium">Symbol</th>
                <th className="px-3 py-2 font-medium">Family / horizon</th>
                <th className="px-3 py-2 font-medium">Last seen</th>
                <th className="px-3 py-2 font-medium">First seen</th>
                <th className="px-3 py-2 font-medium">N</th>
                <th className="px-3 py-2 font-medium">Proposal</th>
                <th className="px-3 py-2 font-medium">Current</th>
                <th className="px-3 py-2 font-medium">Return</th>
                <th className="px-3 py-2 font-medium">D1 D5 D10 D20</th>
                <th className="px-3 py-2 font-medium">Why it left</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {rows.map((row) => {
                const active = selected === row.symbol;
                const byName = checkpointMap(row);
                return (
                  <tr
                    key={`${row.symbol}-${row.family}`}
                    className={active ? "bg-neutral-800/60" : ""}
                  >
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => void openSymbol(row.symbol)}
                        className="font-semibold text-sky-300 hover:underline"
                      >
                        {row.symbol}
                      </button>
                    </td>
                    <td className="px-3 py-2 text-[10px] uppercase tracking-wide text-neutral-400">
                      {row.family}
                      <div className="normal-case tracking-normal text-neutral-500">
                        {row.horizon}
                      </div>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-neutral-300">
                      {row.last_seen}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-neutral-500">
                      {row.first_seen}
                    </td>
                    <td className="px-3 py-2 text-neutral-400">
                      {row.occurrence_count}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {fmtPrice(row.proposal_price)}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {fmtPrice(row.current_price)}
                    </td>
                    <td
                      className={`px-3 py-2 font-mono text-xs ${changeClass(row.change_pct)}`}
                    >
                      {fmtChange(row.change_pct)}
                    </td>
                    <td className="px-3 py-2 font-mono text-[10px] text-neutral-400">
                      {OFFSET_CHECKPOINTS.map((name) => (
                        <span key={name} className="mr-2">
                          {name}{" "}
                          <span className={changeClass(byName[name]?.return_pct)}>
                            {byName[name]?.price == null
                              ? "—"
                              : fmtChange(byName[name]?.return_pct)}
                          </span>
                        </span>
                      ))}
                    </td>
                    <td className="px-3 py-2 text-xs text-neutral-300">
                      {row.why_left?.summary ?? "—"}
                      {row.why_left ? (
                        <div className="mt-0.5 text-[10px] text-neutral-500">
                          {row.why_left.not_a_signal}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-[10px] text-neutral-400">
                      {row.status_at_proposal}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-3">
          <h3 className="text-sm font-semibold text-neutral-100">
            {selected} timeline
          </h3>
          <p className="mb-2 text-[10px] text-neutral-500">
            Append-only family rows. D20 on a hours–1d GAP card is a fact, not
            the intended hold. Same-as-of re-ingest does not overwrite proposal
            facts.
          </p>
          {timeline.length === 0 ? (
            <div className="py-3 text-center text-xs text-neutral-500">
              No timeline rows.
            </div>
          ) : (
            <ul className="divide-y divide-neutral-800 text-sm">
              {timeline.map((row) => (
                <li
                  key={`${row.candidate_date}-${row.family}-${row.snapshot_sha256}`}
                  className="py-1.5"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <div>
                      <span className="font-mono text-xs text-neutral-300">
                        {row.candidate_date}
                      </span>
                    </div>
                    <span className="font-mono text-xs text-neutral-300">
                      {fmtPrice(row.proposal_price)}
                      <span className={`ml-2 ${changeClass(row.change_pct)}`}>
                        {fmtChange(row.change_pct)}
                      </span>
                    </span>
                  </div>
                  <div className="mt-0.5">
                    <CheckpointStrip row={row} />
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] text-neutral-400">
                    {chipLine(row)}
                  </div>
                  {row.why_left?.summary ? (
                    <p className="mt-1 text-xs text-neutral-300">
                      {row.why_left.summary}
                      <span className="ml-2 text-[10px] text-neutral-500">
                        {row.why_left.not_a_signal}
                      </span>
                    </p>
                  ) : null}
                  {row.reason.why ? (
                    <p className="mt-1 text-xs text-neutral-500">{row.reason.why}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
