import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import {
  strategyAuthoringApi,
  type AuthorResult,
} from "@/api/strategyAuthoring";

interface Turn {
  kind: "generation" | "refinement";
  userMessage: string;
  result: AuthorResult;
}

/**
 * P7 §4/§6 — "Author with AI". Describe → generate → backtest → refine in a
 * conversation → save. Each turn shows its code + backtest; the trader can request
 * a change (refinement) or Revert to a prior turn. Hard backtest failures are
 * auto-fixed once by the server (flagged). Read-only display (manual editing is
 * §7). Zero-dep. The conversation is persisted as the saved strategy's history.
 */
export default function AuthorWithAI() {
  const navigate = useNavigate();
  const [description, setDescription] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [change, setChange] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const current = turns.length ? turns[turns.length - 1] : null;

  function describeError(e: unknown): string {
    if (e instanceof ApiError && e.status === 429)
      return "Daily AI budget reached — try again later or raise the cap.";
    if (e instanceof ApiError && e.status === 400)
      return "No Anthropic API key configured (Settings → Credentials).";
    return "Request failed — please try again.";
  }

  async function handleGenerate() {
    setBusy(true);
    setError(null);
    try {
      const desc = description.trim();
      const result = await strategyAuthoringApi.author(desc);
      setTurns([{ kind: "generation", userMessage: desc, result }]);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRefine() {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      const req = change.trim();
      const result = await strategyAuthoringApi.refine(current.result.code, req);
      setTurns((t) => [...t, { kind: "refinement", userMessage: req, result }]);
      setChange("");
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  function revertTo(index: number) {
    setTurns((t) => t.slice(0, index + 1));
  }

  async function handleSave() {
    if (!current) return;
    setSaving(true);
    setSaveError(null);
    try {
      const history = turns.map((t) => ({
        kind: t.kind,
        user_message: t.userMessage,
        assumptions: t.result.assumptions,
        explanation: t.result.explanation,
        code: t.result.code,
        backtest: t.result.backtest,
        cost_usd: t.result.cost_usd,
      }));
      const saved = await strategyAuthoringApi.saveAuthored(current.result.code, name.trim(), history);
      navigate(`/strategies/${saved.id}`);
    } catch (e) {
      setSaveError(
        e instanceof ApiError && e.status === 409
          ? "A strategy by that name already exists — pick another."
          : "Save failed — check the name and try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  function discard() {
    setTurns([]);
    setName("");
    setChange("");
    setSaveError(null);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-xl font-semibold text-white">Author with AI</h1>
      <p className="text-xs text-neutral-400">
        Describe a strategy in plain English, then refine it in conversation. The AI
        writes the Python, backtests it, and lists what it assumed. Saving registers it
        as a normal strategy — it still goes through backtest, paper, and the activation
        cooldown before it can trade live.
      </p>

      {turns.length === 0 && (
        <>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Buy SPY when the 20-period EMA crosses above the 50-period EMA; exit on the reverse cross or a 2x ATR stop."
            rows={4}
            className="w-full rounded bg-neutral-800 p-2 text-sm text-white"
          />
          <button
            type="button"
            onClick={handleGenerate}
            disabled={busy || !description.trim()}
            className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700"
          >
            {busy ? "Generating…" : "Generate"}
          </button>
        </>
      )}

      {error && (
        <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200">
          {error}
        </div>
      )}

      {turns.map((turn, i) => (
        <TurnView
          key={i}
          turn={turn}
          index={i}
          isCurrent={i === turns.length - 1}
          onRevert={() => revertTo(i)}
        />
      ))}

      {current && (
        <>
          <section className="space-y-2 border-t border-neutral-800 pt-3">
            <div className="text-sm font-semibold text-neutral-100">Refine</div>
            <textarea
              value={change}
              onChange={(e) => setChange(e.target.value)}
              placeholder="Request a change — e.g. use a 2x ATR stop instead of the fixed 8%."
              rows={2}
              className="w-full rounded bg-neutral-800 p-2 text-sm text-white"
            />
            <button
              type="button"
              onClick={handleRefine}
              disabled={busy || !change.trim()}
              className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700"
            >
              {busy ? "Refining…" : "Refine"}
            </button>
          </section>

          <section className="flex items-center gap-2 border-t border-neutral-800 pt-3">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="strategy name"
              className="flex-1 rounded bg-neutral-800 px-2 py-1.5 text-sm text-white"
            />
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !name.trim()}
              className="rounded bg-green-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-green-600 disabled:bg-neutral-700"
            >
              {saving ? "Saving…" : "Save strategy"}
            </button>
            <button
              type="button"
              onClick={discard}
              className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-neutral-200"
            >
              Discard
            </button>
          </section>
          {saveError && (
            <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200">
              {saveError}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function TurnView({
  turn,
  index,
  isCurrent,
  onRevert,
}: {
  turn: Turn;
  index: number;
  isCurrent: boolean;
  onRevert: () => void;
}) {
  const r = turn.result;
  return (
    <div
      className={`space-y-3 rounded border p-3 ${
        isCurrent ? "border-neutral-700 bg-neutral-900" : "border-neutral-850 bg-neutral-950"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold uppercase text-neutral-400">
          {turn.kind === "generation" ? "Generation" : `Refinement ${index}`}
          {r.auto_fixed && (
            <span className="ml-2 rounded bg-amber-900/60 px-1.5 py-0.5 text-[10px] text-amber-200">
              auto-fixed
            </span>
          )}
        </div>
        {!isCurrent && (
          <button
            type="button"
            onClick={onRevert}
            className="rounded bg-neutral-700 px-2 py-0.5 text-[11px] text-neutral-200"
          >
            Revert to here
          </button>
        )}
      </div>
      {turn.userMessage && (
        <p className="text-xs italic text-neutral-400">“{turn.userMessage}”</p>
      )}
      <BacktestPanel result={r} />
      <pre className="max-h-80 overflow-auto rounded bg-neutral-950 p-3 text-xs text-neutral-200">
        <code>{r.code}</code>
      </pre>
      {r.assumptions.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold text-neutral-100">What the AI assumed</div>
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-neutral-300">
            {r.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-neutral-300">{r.explanation}</p>
      <p className="text-[10px] text-neutral-500">{r.model} · ${r.cost_usd.toFixed(4)}</p>
    </div>
  );
}

function BacktestPanel({ result }: { result: AuthorResult }) {
  const bt = result.backtest;
  if (bt.status === "ok" || bt.status === "no_trades") {
    const m = bt.metrics;
    return (
      <div className="rounded border border-neutral-800 bg-neutral-900 p-2">
        <div className="text-xs font-semibold text-neutral-100">
          Backtest {bt.status === "no_trades" ? "(no trades)" : ""}
        </div>
        {m && (
          <div className="mt-1 grid grid-cols-2 gap-x-6 gap-y-0.5 text-xs text-neutral-300 sm:grid-cols-3">
            <Metric label="Total return" value={`${(m.total_return * 100).toFixed(2)}%`} />
            <Metric label="Sharpe" value={m.sharpe_ratio.toFixed(2)} />
            <Metric label="Max drawdown" value={`${(m.max_drawdown * 100).toFixed(2)}%`} />
            <Metric label="Win rate" value={`${(m.win_rate * 100).toFixed(1)}%`} />
            <Metric label="Trades" value={String(m.trade_count)} />
            <Metric label="Profit factor" value={m.profit_factor.toFixed(2)} />
          </div>
        )}
      </div>
    );
  }
  const msg =
    bt.status === "unavailable"
      ? "Backtest data isn't available in this environment."
      : `Backtest failed (${bt.status})${bt.error ? `: ${bt.error}` : ""}`;
  return (
    <div className="rounded border border-amber-800 bg-amber-950/30 p-2 text-xs text-amber-200">
      {msg}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-neutral-500">{label}: </span>
      <span className="font-mono text-neutral-100">{value}</span>
    </div>
  );
}
