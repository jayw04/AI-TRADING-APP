import { useState } from "react";
import { strategiesApi } from "@/api/strategies";
import { ApiError } from "@/api/client";
import type { StrategyType } from "@/api/types";

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

const KNOWN_REFERENCE_PATHS = [
  "examples/rsi_meanreversion.py",
];

export function NewStrategyModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState("rsi-mean-reversion");
  const [codePath, setCodePath] = useState("examples/rsi_meanreversion.py");
  const [symbolsText, setSymbolsText] = useState("AAPL");
  const [paramsText, setParamsText] = useState('{"entry_threshold": 30, "exit_threshold": 55}');
  const [schedule, setSchedule] = useState("*/1 * * * *");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    setError(null);
    let parsedParams: Record<string, unknown>;
    try {
      parsedParams = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch (e) {
      setError(`Params is not valid JSON: ${e}`);
      return;
    }
    const symbols = symbolsText
      .split(/[,\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (!codePath.trim()) {
      setError("Code path is required");
      return;
    }
    setSubmitting(true);
    try {
      await strategiesApi.create({
        name: name.trim(),
        code_path: codePath.trim(),
        type: "python" as StrategyType,
        params: parsedParams,
        symbols,
        schedule,
      });
      onCreated();
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`${JSON.stringify(e.body)} (status ${e.status})`);
      } else {
        setError(String(e));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70">
      <div className="w-[32rem] max-h-[90vh] overflow-y-auto rounded-lg border border-gray-700 bg-gray-950 p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Register a new strategy</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div className="space-y-3 text-sm text-gray-300">
          <label className="block">
            <span className="text-xs text-gray-400">Name</span>
            <input
              type="text" value={name} onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white"
            />
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Code path (under strategies_user/)</span>
            <input
              type="text" value={codePath} onChange={(e) => setCodePath(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-white"
              placeholder="examples/rsi_meanreversion.py"
              list="known-paths"
            />
            <datalist id="known-paths">
              {KNOWN_REFERENCE_PATHS.map((p) => <option key={p} value={p} />)}
            </datalist>
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Symbols (comma or space separated)</span>
            <input
              type="text" value={symbolsText} onChange={(e) => setSymbolsText(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white"
              placeholder="AAPL MSFT SPY"
            />
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Params (JSON)</span>
            <textarea
              value={paramsText} onChange={(e) => setParamsText(e.target.value)}
              rows={6}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-xs text-white"
            />
          </label>

          <label className="block">
            <span className="text-xs text-gray-400">Schedule (cron, or &quot;event&quot;)</span>
            <input
              type="text" value={schedule} onChange={(e) => setSchedule(e.target.value)}
              className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-white"
            />
          </label>

          {error && (
            <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
              {error}
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose}
                  className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200">
            Cancel
          </button>
          <button onClick={handleCreate} disabled={submitting}
                  className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700">
            {submitting ? "Creating…" : "Register"}
          </button>
        </div>
      </div>
    </div>
  );
}
