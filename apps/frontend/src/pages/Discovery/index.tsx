import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import {
  scannerApi,
  type ScannerDefinition,
  type ScannerDefinitionInput,
  type ScannerRun,
  type ScannerRunSummary,
  type ScannerVocabulary,
  type UniverseKind,
} from "@/api/scanner";
import { tradingProfileApi } from "@/api/tradingProfile";
import { strategyTemplatesApi } from "@/api/strategyTemplates";

type ApplyState =
  | { status: "applying" }
  | { status: "done"; id: number }
  | { status: "error" };

/**
 * P8 §3 — Discovery view. Author a boolean criterion over supported indicator
 * names + a universe, save it, run it, and act on the matches (add to
 * watchlist). Deterministic screening — no AI (P8 Decision 1). Zero-dep.
 */

const UNIVERSE_LABELS: Record<UniverseKind, string> = {
  discovery_feeds: "Discovery feeds (most-actives + movers)",
  watchlist: "My watchlist",
  symbols: "Specific symbols",
};

const OPERATOR_CHIPS = ["<", ">", "<=", ">=", "and", "or", "/"];

// Common ready-made criteria — click to fill the box, then tweak. Each uses only
// supported indicators/fields so it validates as-is. (label, default scan name, expr)
const CRITERIA_PRESETS: { label: string; name: string; expr: string }[] = [
  { label: "Oversold (RSI < 30)", name: "Oversold", expr: "RSI14 < 30" },
  { label: "Overbought (RSI > 70)", name: "Overbought", expr: "RSI14 > 70" },
  { label: "High rel. volume", name: "High Volume", expr: "RELVOL20 > 2" },
  { label: "Liquid movers", name: "Liquid Movers", expr: "RELVOL20 > 2 and close > 5" },
  { label: "Volatile (ATR > 3%)", name: "Volatile", expr: "ATR14 / close > 0.03" },
  { label: "Uptrend (> 200d SMA)", name: "Uptrend", expr: "close > SMA200" },
  { label: "EMA20 > EMA50", name: "EMA Cross", expr: "EMA20 > EMA50" },
  { label: "MACD bullish", name: "MACD Bullish", expr: "macd > signal" },
  { label: "Breakout (> upper BB)", name: "Breakout", expr: "close > bb_upper" },
  { label: "Momentum + volume", name: "Momentum", expr: "RSI14 > 50 and RELVOL20 > 1.5" },
];

function errDetail(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    const detail = (e.body as { detail?: string } | null)?.detail;
    if (detail) return detail;
  }
  return fallback;
}

function parseSymbols(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
}

export default function Discovery() {
  const [definitions, setDefinitions] = useState<ScannerDefinition[]>([]);
  const [vocab, setVocab] = useState<ScannerVocabulary | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [criteria, setCriteria] = useState("");
  const [universeKind, setUniverseKind] = useState<UniverseKind>("discovery_feeds");
  const [symbolsText, setSymbolsText] = useState("");
  const [scheduled, setScheduled] = useState(false);

  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [latestRun, setLatestRun] = useState<ScannerRun | null>(null);
  const [runs, setRuns] = useState<ScannerRunSummary[]>([]);
  const [applied, setApplied] = useState<Record<string, ApplyState>>({});

  const refreshDefinitions = useCallback(() => {
    scannerApi.list().then(setDefinitions).catch(() => setDefinitions([]));
  }, []);

  useEffect(() => {
    refreshDefinitions();
    scannerApi.vocabulary().then(setVocab).catch(() => setVocab(null));
  }, [refreshDefinitions]);

  function resetForm() {
    setSelectedId(null);
    setName("");
    setCriteria("");
    setUniverseKind("discovery_feeds");
    setSymbolsText("");
    setScheduled(false);
    setFormError(null);
    setRunError(null);
    setNotice(null);
    setLatestRun(null);
    setRuns([]);
  }

  function selectDefinition(d: ScannerDefinition) {
    setSelectedId(d.id);
    setName(d.name);
    setCriteria(d.criteria);
    setUniverseKind(d.universe_kind);
    setSymbolsText((d.universe_symbols ?? []).join(", "));
    setScheduled(d.scheduled);
    setFormError(null);
    setRunError(null);
    setNotice(null);
    setLatestRun(null);
    scannerApi.listRuns(d.id).then(setRuns).catch(() => setRuns([]));
  }

  function buildInput(): ScannerDefinitionInput {
    return {
      name: name.trim(),
      criteria: criteria.trim(),
      universe: {
        kind: universeKind,
        symbols: universeKind === "symbols" ? parseSymbols(symbolsText) : null,
      },
      scheduled,
    };
  }

  async function handleSave() {
    setSaving(true);
    setFormError(null);
    setNotice(null);
    try {
      const input = buildInput();
      const saved =
        selectedId === null
          ? await scannerApi.create(input)
          : await scannerApi.update(selectedId, input);
      refreshDefinitions();
      selectDefinition(saved);
      setNotice(selectedId === null ? "Scan created." : "Scan saved.");
    } catch (e) {
      setFormError(errDetail(e, "Could not save the scan."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (selectedId === null) return;
    setSaving(true);
    try {
      await scannerApi.remove(selectedId);
      refreshDefinitions();
      resetForm();
    } catch (e) {
      setFormError(errDetail(e, "Could not delete the scan."));
    } finally {
      setSaving(false);
    }
  }

  async function handleRun() {
    if (selectedId === null) return;
    setRunning(true);
    setRunError(null);
    setNotice(null);
    try {
      const run = await scannerApi.run(selectedId);
      setLatestRun(run);
      setApplied({});
      scannerApi.listRuns(selectedId).then(setRuns).catch(() => undefined);
    } catch (e) {
      setRunError(
        e instanceof ApiError && e.status === 503
          ? "Market data is not available right now — try again shortly."
          : errDetail(e, "The scan could not run."),
      );
    } finally {
      setRunning(false);
    }
  }

  async function applyTemplate(symbol: string) {
    setApplied((s) => ({ ...s, [symbol]: { status: "applying" } }));
    try {
      const result = await strategyTemplatesApi.applyRange(symbol);
      setApplied((s) => ({ ...s, [symbol]: { status: "done", id: result.id } }));
    } catch {
      setApplied((s) => ({ ...s, [symbol]: { status: "error" } }));
    }
  }

  async function addToWatchlist(symbol: string) {
    setNotice(null);
    try {
      const profile = await tradingProfileApi.get();
      const wl = (profile.watchlist ?? {}) as Record<string, unknown> & {
        swing_candidates?: string[];
      };
      const swing = Array.isArray(wl.swing_candidates) ? wl.swing_candidates : [];
      if (swing.map((s) => s.toUpperCase()).includes(symbol)) {
        setNotice(`${symbol} is already on your watchlist.`);
        return;
      }
      await tradingProfileApi.update({
        watchlist: { ...wl, swing_candidates: [...swing, symbol] },
      });
      setNotice(`Added ${symbol} to your watchlist.`);
    } catch {
      setNotice(`Could not add ${symbol} to the watchlist.`);
    }
  }

  function insertToken(token: string) {
    setCriteria((c) => (c.length && !c.endsWith(" ") ? `${c} ${token}` : `${c}${token}`));
  }

  const matchColumns = useMemo(() => {
    const keys = new Set<string>();
    (latestRun?.matched ?? []).forEach((m) =>
      Object.keys(m.values).forEach((k) => keys.add(k)),
    );
    return [...keys].sort();
  }, [latestRun]);

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-neutral-100">Discovery</h1>
          <p className="text-xs text-neutral-500">
            Screen symbols with a deterministic criterion over supported indicators.
          </p>
        </div>
        <button
          onClick={resetForm}
          className="rounded bg-neutral-800 px-3 py-1.5 text-sm font-semibold text-neutral-100 hover:bg-neutral-700"
        >
          + New scan
        </button>
      </header>

      <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
        {/* saved scans */}
        <aside className="space-y-1">
          <div className="text-[11px] uppercase tracking-wider text-neutral-500">
            Saved scans
          </div>
          {definitions.length === 0 && (
            <div className="text-xs text-neutral-600">No saved scans yet.</div>
          )}
          {definitions.map((d) => (
            <button
              key={d.id}
              onClick={() => selectDefinition(d)}
              className={[
                "block w-full truncate rounded px-2 py-1.5 text-left text-sm",
                d.id === selectedId
                  ? "bg-neutral-800 text-neutral-100"
                  : "text-neutral-400 hover:bg-neutral-900",
              ].join(" ")}
            >
              {d.name}
            </button>
          ))}
        </aside>

        {/* editor + results */}
        <section className="space-y-4">
          <div className="space-y-3 rounded border border-neutral-800 bg-neutral-900 p-3">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="scan name"
              className="w-full rounded bg-neutral-800 p-2 text-sm text-white"
            />

            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-1">
                <span className="mr-1 text-xs text-neutral-500">Common criteria:</span>
                {CRITERIA_PRESETS.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    title={p.expr}
                    onClick={() => {
                      setCriteria(p.expr);
                      if (!name.trim()) setName(p.name);
                      setFormError(null);
                    }}
                    className="rounded border border-neutral-700 bg-neutral-800 px-2 py-0.5 text-xs text-neutral-200 hover:border-blue-600 hover:bg-neutral-700"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <textarea
                value={criteria}
                onChange={(e) => setCriteria(e.target.value)}
                placeholder="e.g. RSI14 < 35 and ATR14 / close > 0.02"
                rows={2}
                className="w-full rounded bg-neutral-800 p-2 font-mono text-sm text-white"
              />
              <div className="flex flex-wrap gap-1">
                {OPERATOR_CHIPS.map((op) => (
                  <button
                    key={op}
                    onClick={() => insertToken(op)}
                    className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-xs text-neutral-300 hover:bg-neutral-700"
                  >
                    {op}
                  </button>
                ))}
                {(vocab?.indicators ?? []).map((n) => (
                  <button
                    key={n}
                    onClick={() => insertToken(n)}
                    className="rounded bg-blue-950/60 px-1.5 py-0.5 font-mono text-xs text-blue-200 hover:bg-blue-900/60"
                  >
                    {n}
                  </button>
                ))}
                {(vocab?.fields ?? []).map((n) => (
                  <button
                    key={n}
                    onClick={() => insertToken(n)}
                    className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-xs text-neutral-400 hover:bg-neutral-700"
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                value={universeKind}
                onChange={(e) => setUniverseKind(e.target.value as UniverseKind)}
                className="rounded bg-neutral-800 p-2 text-sm text-white"
              >
                {(Object.keys(UNIVERSE_LABELS) as UniverseKind[]).map((k) => (
                  <option key={k} value={k}>
                    {UNIVERSE_LABELS[k]}
                  </option>
                ))}
              </select>
              {universeKind === "symbols" && (
                <input
                  value={symbolsText}
                  onChange={(e) => setSymbolsText(e.target.value)}
                  placeholder="AAPL, MSFT, NVDA"
                  className="flex-1 rounded bg-neutral-800 p-2 text-sm text-white"
                />
              )}
            </div>

            <label className="flex items-center gap-2 text-xs text-neutral-400">
              <input
                type="checkbox"
                checked={scheduled}
                onChange={(e) => setScheduled(e.target.checked)}
              />
              Run automatically pre-market (default 7:30 ET — set the time in
              Trading Profile). Scheduled matches appear in Opportunities.
            </label>

            {formError && (
              <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200">
                {formError}
              </div>
            )}

            <div className="flex items-center gap-2">
              <button
                onClick={handleSave}
                disabled={saving || !name.trim() || !criteria.trim()}
                className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700"
              >
                {selectedId === null ? "Create scan" : "Save scan"}
              </button>
              {selectedId !== null && (
                <>
                  <button
                    onClick={handleRun}
                    disabled={running}
                    className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-600 disabled:bg-neutral-700"
                  >
                    {running ? "Running…" : "Run scan"}
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={saving}
                    className="ml-auto rounded px-3 py-1.5 text-sm text-red-300 hover:bg-red-950/40"
                  >
                    Delete
                  </button>
                </>
              )}
            </div>
            {(!name.trim() || !criteria.trim()) && (
              <div className="text-xs text-neutral-500">
                {!name.trim() && !criteria.trim()
                  ? "Enter a scan name and a criterion"
                  : !name.trim()
                    ? "Enter a scan name"
                    : "Enter a criterion"}{" "}
                to enable {selectedId === null ? "Create" : "Save"} scan — e.g.{" "}
                <code className="rounded bg-neutral-800 px-1">RELVOL20 &gt; 2 and close &gt; 5</code>.
              </div>
            )}
            {notice && <div className="text-xs text-emerald-300">{notice}</div>}
          </div>

          {runError && (
            <div className="rounded border border-red-700 bg-red-950/40 p-2 text-sm text-red-200">
              {runError}
            </div>
          )}

          {latestRun && (
            <div className="space-y-2 rounded border border-neutral-800 bg-neutral-900 p-3">
              <div className="text-sm text-neutral-300">
                {latestRun.matched_count} matched of {latestRun.universe_size}{" "}
                ({latestRun.evaluated_count} evaluated, {latestRun.skipped_count}{" "}
                skipped)
              </div>
              {latestRun.matched.length === 0 ? (
                <div className="text-xs text-neutral-500">No symbols matched.</div>
              ) : (
                <div className="overflow-hidden rounded border border-neutral-800">
                  <table className="w-full text-sm">
                    <thead className="bg-neutral-950 text-[11px] uppercase tracking-wider text-neutral-500">
                      <tr>
                        <th className="px-3 py-2 text-left">Symbol</th>
                        {matchColumns.map((c) => (
                          <th key={c} className="px-3 py-2 text-right font-mono">
                            {c}
                          </th>
                        ))}
                        <th className="px-3 py-2" />
                      </tr>
                    </thead>
                    <tbody>
                      {latestRun.matched.map((m) => (
                        <tr key={m.symbol} className="border-t border-neutral-800">
                          <td className="px-3 py-1.5 font-semibold text-neutral-100">
                            {m.symbol}
                          </td>
                          {matchColumns.map((c) => (
                            <td
                              key={c}
                              className="px-3 py-1.5 text-right font-mono text-neutral-300"
                            >
                              {m.values[c] !== undefined
                                ? m.values[c].toFixed(2)
                                : "—"}
                            </td>
                          ))}
                          <td className="px-3 py-1.5 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => addToWatchlist(m.symbol)}
                                className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300 hover:bg-neutral-700"
                              >
                                + watchlist
                              </button>
                              {applied[m.symbol]?.status === "done" ? (
                                <Link
                                  to={`/strategies/${(applied[m.symbol] as { id: number }).id}`}
                                  className="rounded bg-emerald-900/60 px-2 py-0.5 text-xs text-emerald-200"
                                >
                                  ✓ view
                                </Link>
                              ) : (
                                <button
                                  onClick={() => applyTemplate(m.symbol)}
                                  disabled={applied[m.symbol]?.status === "applying"}
                                  title="Apply the range-trading template to this symbol"
                                  className="rounded bg-blue-900/60 px-2 py-0.5 text-xs text-blue-200 hover:bg-blue-800/60 disabled:opacity-50"
                                >
                                  {applied[m.symbol]?.status === "applying"
                                    ? "applying…"
                                    : "apply template"}
                                </button>
                              )}
                            </div>
                            {applied[m.symbol]?.status === "error" && (
                              <div className="text-[10px] text-rose-300">apply failed</div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {runs.length > 0 && (
            <div className="space-y-1 rounded border border-neutral-800 bg-neutral-900 p-3">
              <div className="text-[11px] uppercase tracking-wider text-neutral-500">
                Recent runs
              </div>
              {runs.map((r) => (
                <button
                  key={r.id}
                  onClick={() =>
                    scannerApi.getRun(r.id).then(setLatestRun).catch(() => undefined)
                  }
                  className="block w-full text-left text-xs text-neutral-400 hover:text-neutral-200"
                >
                  {new Date(r.run_at).toLocaleString()} — {r.matched_count} matched,{" "}
                  {r.skipped_count} skipped
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
