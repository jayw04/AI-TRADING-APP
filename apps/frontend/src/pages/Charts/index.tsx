import { useState } from "react";
import TVChart from "@/components/chart/TVChart";

type Interval = "1" | "5" | "15" | "60" | "D";

const SEED_SYMBOLS = [
  "AAPL",
  "MSFT",
  "NVDA",
  "SPY",
  "QQQ",
  "F",
  "TSLA",
  "AMD",
  "GOOGL",
  "AMZN",
  "META",
];

const INTERVALS: { id: Interval; label: string }[] = [
  { id: "1", label: "1m" },
  { id: "5", label: "5m" },
  { id: "15", label: "15m" },
  { id: "60", label: "1h" },
  { id: "D", label: "1D" },
];

export default function ChartsPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [interval, setInterval] = useState<Interval>("5");
  const [input, setInput] = useState("");

  function commitInput() {
    const next = input.trim().toUpperCase();
    if (next) {
      setSymbol(next);
      setInput("");
    }
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitInput();
          }}
          placeholder="Symbol (Enter)"
          aria-label="Chart symbol"
          autoCapitalize="characters"
          spellCheck={false}
          className="w-40 rounded border border-neutral-800 bg-neutral-950 px-3 py-1 text-sm text-neutral-100 placeholder:text-neutral-600 focus:outline-none focus:border-neutral-600"
        />
        <span className="text-[11px] uppercase tracking-wider text-neutral-500">
          Quick
        </span>
        {SEED_SYMBOLS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSymbol(s)}
            className={`rounded px-2 py-1 text-xs transition-colors ${
              symbol === s
                ? "bg-neutral-100 text-neutral-900"
                : "bg-neutral-950 border border-neutral-800 text-neutral-300 hover:text-neutral-100"
            }`}
          >
            {s}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-1 rounded border border-neutral-800 bg-neutral-950 p-1">
          {INTERVALS.map((it) => (
            <button
              key={it.id}
              type="button"
              onClick={() => setInterval(it.id)}
              className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                interval === it.id
                  ? "bg-neutral-800 text-neutral-100"
                  : "text-neutral-400 hover:text-neutral-200"
              }`}
            >
              {it.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-neutral-400">
          Showing <span className="text-neutral-100 font-mono">{symbol}</span>
        </span>
      </div>
      <div className="flex-1 min-h-0 rounded-lg border border-neutral-800 bg-neutral-900 overflow-hidden">
        <TVChart symbol={symbol} interval={interval} />
      </div>
    </div>
  );
}
