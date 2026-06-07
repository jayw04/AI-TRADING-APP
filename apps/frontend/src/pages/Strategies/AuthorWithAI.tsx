import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import {
  strategyAuthoringApi,
  type AuthorResult,
} from "@/api/strategyAuthoring";

/**
 * P7 §4 — "Author with AI". Describe a strategy in plain English; the platform
 * generates a Python strategy, backtests it, and shows the code + metrics +
 * assumptions. Save registers it as a normal IDLE strategy (standard lifecycle).
 * Read-only display (inline editing is §7). Zero-dep (no syntax highlighter).
 */
export default function AuthorWithAI() {
  const navigate = useNavigate();
  const [description, setDescription] = useState("");
  const [generatedFrom, setGeneratedFrom] = useState("");
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<AuthorResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    setResult(null);
    try {
      const desc = description.trim();
      setResult(await strategyAuthoringApi.author(desc));
      setGeneratedFrom(desc);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        setError("Daily AI budget reached — try again later or raise the cap.");
      } else if (e instanceof ApiError && e.status === 400) {
        setError("No Anthropic API key configured (Settings → Credentials).");
      } else {
        setError("Generation failed — please try again.");
      }
    } finally {
      setGenerating(false);
    }
  }

  async function handleSave() {
    if (!result) return;
    setSaving(true);
    setSaveError(null);
    try {
      // P7 §5: persist the authoring conversation (single-shot = one turn; §6
      // appends refinement turns) as the saved strategy's read-only history.
      const history = [
        {
          kind: "generation" as const,
          user_message: generatedFrom,
          assumptions: result.assumptions,
          explanation: result.explanation,
          code: result.code,
          backtest: result.backtest,
          cost_usd: result.cost_usd,
        },
      ];
      const saved = await strategyAuthoringApi.saveAuthored(result.code, name.trim(), history);
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
    setResult(null);
    setName("");
    setSaveError(null);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-xl font-semibold text-white">Author with AI</h1>
      <p className="text-xs text-neutral-400">
        Describe a strategy in plain English. The AI writes the Python, backtests it on
        cached data, and lists what it assumed. Saving registers it as a normal strategy —
        it still goes through backtest, paper, and the activation cooldown before it can
        trade live.
      </p>

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
        disabled={generating || !description.trim()}
        className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700"
      >
        {generating ? "Generating…" : "Generate"}
      </button>
      {error && (
        <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <BacktestPanel result={result} />

          <section>
            <div className="mb-1 text-sm font-semibold text-neutral-100">Generated code</div>
            <pre className="max-h-96 overflow-auto rounded bg-neutral-950 p-3 text-xs text-neutral-200">
              <code>{result.code}</code>
            </pre>
          </section>

          {result.assumptions.length > 0 && (
            <section>
              <div className="mb-1 text-sm font-semibold text-neutral-100">What the AI assumed</div>
              <ul className="list-disc space-y-0.5 pl-5 text-xs text-neutral-300">
                {result.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <div className="mb-1 text-sm font-semibold text-neutral-100">Explanation</div>
            <p className="text-xs text-neutral-300">{result.explanation}</p>
            <p className="mt-1 text-[10px] text-neutral-500">
              {result.model} · ${result.cost_usd.toFixed(4)}
            </p>
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
        </div>
      )}
    </div>
  );
}

function BacktestPanel({ result }: { result: AuthorResult }) {
  const bt = result.backtest;
  if (bt.status === "ok" || bt.status === "no_trades") {
    const m = bt.metrics;
    return (
      <section className="rounded border border-neutral-800 bg-neutral-900 p-3">
        <div className="text-sm font-semibold text-neutral-100">
          Backtest {bt.status === "no_trades" ? "(no trades)" : ""}
        </div>
        {m && (
          <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-neutral-300 sm:grid-cols-3">
            <Metric label="Total return" value={`${(m.total_return * 100).toFixed(2)}%`} />
            <Metric label="Sharpe" value={m.sharpe_ratio.toFixed(2)} />
            <Metric label="Max drawdown" value={`${(m.max_drawdown * 100).toFixed(2)}%`} />
            <Metric label="Win rate" value={`${(m.win_rate * 100).toFixed(1)}%`} />
            <Metric label="Trades" value={String(m.trade_count)} />
            <Metric label="Profit factor" value={m.profit_factor.toFixed(2)} />
          </div>
        )}
      </section>
    );
  }
  const msg =
    bt.status === "unavailable"
      ? "Backtest data isn't available in this environment."
      : `Backtest failed (${bt.status})${bt.error ? `: ${bt.error}` : ""}`;
  return (
    <section className="rounded border border-amber-800 bg-amber-950/30 p-3 text-xs text-amber-200">
      {msg} — review the code below before saving.
    </section>
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
