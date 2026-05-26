import { useState } from "react";
import { strategiesApi } from "@/api/strategies";
import type { Strategy } from "@/api/types";
import { ApiError } from "@/api/client";

interface Props {
  strategy: Strategy;
  onSaved: () => void;
}

export function ParamsTab({ strategy, onSaved }: Props) {
  const editable = strategy.status === "idle";
  const [text, setText] = useState(JSON.stringify(strategy.params, null, 2));
  const [symbols, setSymbols] = useState(strategy.symbols.join(", "));
  const [schedule, setSchedule] = useState(strategy.schedule);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setError(`Params not valid JSON: ${e}`);
      return;
    }
    const symList = symbols.split(/[,\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
    setSaving(true);
    try {
      await strategiesApi.update(strategy.id, {
        params: parsed,
        symbols: symList,
        schedule,
      });
      onSaved();
    } catch (e) {
      if (e instanceof ApiError) setError(`${JSON.stringify(e.body)} (status ${e.status})`);
      else setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 max-w-2xl">
      {!editable && (
        <div className="rounded border border-amber-700 bg-amber-900/30 p-3 text-sm text-amber-100">
          Strategy is <span className="font-semibold">{strategy.status}</span> — stop it before editing.
        </div>
      )}

      <label className="block">
        <span className="text-xs text-gray-400">Symbols (comma or space separated)</span>
        <input
          type="text" value={symbols} onChange={(e) => setSymbols(e.target.value)}
          disabled={!editable}
          className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white disabled:opacity-50"
        />
      </label>

      <label className="block">
        <span className="text-xs text-gray-400">Schedule (cron or &quot;event&quot;)</span>
        <input
          type="text" value={schedule} onChange={(e) => setSchedule(e.target.value)}
          disabled={!editable}
          className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-white disabled:opacity-50"
        />
      </label>

      <label className="block">
        <span className="text-xs text-gray-400">Params (JSON)</span>
        <textarea
          value={text} onChange={(e) => setText(e.target.value)}
          disabled={!editable}
          rows={16}
          className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-xs text-white disabled:opacity-50"
        />
      </label>

      {error && (
        <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
          {error}
        </div>
      )}

      <div>
        <button onClick={handleSave} disabled={!editable || saving}
          className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700">
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
