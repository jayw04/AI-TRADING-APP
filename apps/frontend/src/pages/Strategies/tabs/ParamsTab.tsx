import { useState } from "react";
import { strategiesApi } from "@/api/strategies";
import type { Strategy } from "@/api/types";
import { ApiError } from "@/api/client";
import { ParamForm } from "@/components/strategies/ParamForm";

interface Props {
  strategy: Strategy;
  onSaved: () => void;
}

export function ParamsTab({ strategy, onSaved }: Props) {
  const editable = strategy.status === "idle";
  const [symbols, setSymbols] = useState(strategy.symbols.join(", "));
  const [schedule, setSchedule] = useState(strategy.schedule);
  const [savingMeta, setSavingMeta] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [paramsError, setParamsError] = useState<string | null>(null);

  // Fallback (no schema): text-editable JSON, same as the original tab.
  const [paramsText, setParamsText] = useState(
    JSON.stringify(strategy.params, null, 2),
  );

  async function handleSaveMeta() {
    setMetaError(null);
    const symList = symbols
      .split(/[,\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    setSavingMeta(true);
    try {
      await strategiesApi.update(strategy.id, { symbols: symList, schedule });
      onSaved();
    } catch (e) {
      if (e instanceof ApiError) {
        setMetaError(`${JSON.stringify(e.body)} (status ${e.status})`);
      } else {
        setMetaError(String(e));
      }
    } finally {
      setSavingMeta(false);
    }
  }

  async function handleSaveParamsForm(values: Record<string, unknown>) {
    setParamsError(null);
    try {
      await strategiesApi.update(strategy.id, { params: values });
      onSaved();
    } catch (e) {
      if (e instanceof ApiError) {
        setParamsError(`${JSON.stringify(e.body)} (status ${e.status})`);
      } else {
        setParamsError(String(e));
      }
      // Re-throw so ParamForm keeps its "Unsaved changes" indicator.
      throw e;
    }
  }

  async function handleSaveParamsJson() {
    setParamsError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch (e) {
      setParamsError(`Params not valid JSON: ${e}`);
      return;
    }
    try {
      await strategiesApi.update(strategy.id, { params: parsed });
      onSaved();
    } catch (e) {
      if (e instanceof ApiError) {
        setParamsError(`${JSON.stringify(e.body)} (status ${e.status})`);
      } else {
        setParamsError(String(e));
      }
    }
  }

  const hasSchema = Boolean(
    strategy.params_schema && Object.keys(strategy.params_schema).length > 0,
  );

  return (
    <div className="space-y-6 max-w-2xl">
      {!editable && (
        <div className="rounded border border-amber-700 bg-amber-900/30 p-3 text-sm text-amber-100">
          Strategy is <span className="font-semibold">{strategy.status}</span> — stop it before editing.
        </div>
      )}

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-gray-300">Universe & schedule</h3>
        <label className="block">
          <span className="text-xs text-gray-400">
            Symbols (comma or space separated)
          </span>
          <input
            type="text"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            disabled={!editable}
            className="mt-1 w-full rounded bg-gray-800 px-2 py-1 text-white disabled:opacity-50"
          />
        </label>
        <label className="block">
          <span className="text-xs text-gray-400">
            Schedule (cron or &quot;event&quot;)
          </span>
          <input
            type="text"
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            disabled={!editable}
            className="mt-1 w-full rounded bg-gray-800 px-2 py-1 font-mono text-white disabled:opacity-50"
          />
        </label>
        {metaError && (
          <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
            {metaError}
          </div>
        )}
        <div className="flex justify-end">
          <button
            onClick={handleSaveMeta}
            disabled={!editable || savingMeta}
            className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700"
          >
            {savingMeta ? "Saving…" : "Save universe & schedule"}
          </button>
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-gray-300">Parameters</h3>
        {paramsError && (
          <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
            {paramsError}
          </div>
        )}

        {hasSchema && strategy.params_schema ? (
          <>
            <div className="text-xs text-gray-500">
              Typed form derived from the strategy&apos;s declared
              <code className="mx-1 text-gray-400">params_schema</code>.
            </div>
            <ParamForm
              schema={strategy.params_schema}
              initialValues={strategy.params}
              onSubmit={handleSaveParamsForm}
              disabled={!editable}
            />
          </>
        ) : (
          <>
            <div className="text-xs text-gray-500">
              This strategy didn&apos;t declare a <code>params_schema</code> — edit as raw JSON.
            </div>
            <textarea
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              disabled={!editable}
              rows={12}
              className="w-full rounded bg-gray-800 p-2 font-mono text-xs text-white disabled:opacity-50"
            />
            <div className="flex justify-end">
              <button
                onClick={handleSaveParamsJson}
                disabled={!editable}
                className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700"
              >
                Save params
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
