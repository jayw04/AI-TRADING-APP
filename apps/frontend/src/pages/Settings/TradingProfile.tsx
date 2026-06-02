import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { tradingProfileApi } from "@/api/tradingProfile";
import type {
  TradingProfile as Profile,
  TradingProfileUpdate,
} from "@/api/tradingProfile";
import { credentialsApi } from "@/api/credentials";

// P6 §2a: opt-in scheduled proposal generation.
const CADENCE_OPTIONS: { value: string; label: string }[] = [
  { value: "off", label: "Off (no scheduled generation)" },
  { value: "weekday_market_open", label: "Weekdays 9:30 AM ET (market open)" },
  { value: "daily", label: "Daily 9:30 AM ET" },
  { value: "weekly", label: "Mondays 9:30 AM ET" },
  { value: "monthly_first", label: "First of month 9:30 AM ET" },
];

type Section =
  | "watchlist"
  | "bias_criteria"
  | "bias_thresholds"
  | "session_preferences"
  | "risk_preferences"
  | "agent_envelope";

const SECTIONS: Section[] = [
  "watchlist",
  "bias_criteria",
  "bias_thresholds",
  "session_preferences",
  "risk_preferences",
  "agent_envelope",
];

type Draft = Record<Section, Record<string, unknown>>;

function toDraft(p: Profile): Draft {
  return {
    watchlist: p.watchlist ?? {},
    bias_criteria: p.bias_criteria ?? {},
    bias_thresholds: p.bias_thresholds ?? {},
    session_preferences: p.session_preferences ?? {},
    risk_preferences: p.risk_preferences ?? {},
    agent_envelope: p.agent_envelope ?? {},
  };
}

function linesToList(v: string): string[] {
  return v.split(/\n/).map((s) => s.trim()).filter(Boolean);
}
function listToLines(v: unknown): string {
  return Array.isArray(v) ? v.join("\n") : "";
}

// Send only the sections that actually changed (the backend audit-logs a diff;
// unchanged sections shouldn't appear in the payload).
function changedSections(draft: Draft, original: Draft): TradingProfileUpdate {
  const out: TradingProfileUpdate = {};
  for (const s of SECTIONS) {
    if (JSON.stringify(draft[s]) !== JSON.stringify(original[s])) {
      out[s] = draft[s];
    }
  }
  return out;
}

// --- small field helpers ----------------------------------------------------

function csvToList(v: string): string[] {
  return v
    .split(/[\n,]/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
}
function listToCsv(v: unknown): string {
  return Array.isArray(v) ? v.join(", ") : "";
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block text-xs text-neutral-400">
      {label}
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 text-sm text-white"
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: unknown;
  onChange: (v: number | undefined) => void;
}) {
  return (
    <label className="block text-xs text-neutral-400">
      {label}
      <input
        type="number"
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) =>
          onChange(e.target.value === "" ? undefined : Number(e.target.value))
        }
        className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 text-sm text-white"
      />
    </label>
  );
}

function CheckField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: unknown;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-xs text-neutral-300">
      <input
        type="checkbox"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  );
}

function Card({
  title,
  help,
  children,
}: {
  title: string;
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="text-sm font-medium text-neutral-100">{title}</div>
      {help && <p className="mt-1 text-xs text-neutral-500">{help}</p>}
      <div className="mt-3 space-y-3">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------

export default function TradingProfile() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["trading-profile"],
    queryFn: tradingProfileApi.get,
  });
  // P6 §2a: cadence needs an Agent API Key to invoke the propose endpoint.
  const credentials = useQuery({
    queryKey: ["credentials"],
    queryFn: credentialsApi.list,
  });
  const hasAgentApiKey = (credentials.data ?? []).some(
    (c) => c.kind === "agent_api_key" && c.has_value,
  );

  const original = useMemo<Draft | null>(
    () => (query.data ? toDraft(query.data) : null),
    [query.data],
  );

  const [draft, setDraft] = useState<Draft | null>(null);
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);

  useEffect(() => {
    if (original) setDraft(structuredClone(original));
  }, [original]);

  const save = useMutation({
    mutationFn: (changes: TradingProfileUpdate) =>
      tradingProfileApi.update(changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trading-profile"] }),
  });

  if (query.isLoading || !draft || !original) {
    return <div className="text-sm text-neutral-400">Loading…</div>;
  }

  const setField = (s: Section, key: string, value: unknown) =>
    setDraft((d) => (d ? { ...d, [s]: { ...d[s], [key]: value } } : d));

  const enterJsonMode = () => {
    setJsonText(JSON.stringify(draft, null, 2));
    setJsonError(null);
    setJsonMode(true);
  };
  const applyJson = () => {
    try {
      const parsed = JSON.parse(jsonText) as Draft;
      setDraft(parsed);
      setJsonError(null);
      setJsonMode(false);
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : "Invalid JSON");
    }
  };

  const onSave = () => save.mutate(changedSections(draft, original));

  const wl = draft.watchlist;
  const bc = draft.bias_criteria;
  const bt = draft.bias_thresholds;
  const bull = (bt.bullish as Record<string, unknown>) ?? {};
  const bear = (bt.bearish as Record<string, unknown>) ?? {};
  const sp = draft.session_preferences;
  const rp = draft.risk_preferences;
  const ae = draft.agent_envelope;

  const setThreshold = (side: "bullish" | "bearish", key: string, value: unknown) => {
    const cur = (bt[side] as Record<string, unknown>) ?? {};
    const next = { ...cur };
    if (value === undefined || value === "") delete next[key];
    else next[key] = value;
    setField("bias_thresholds", side, next);
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-neutral-100">Trading Profile</h1>
        <button
          type="button"
          onClick={() => (jsonMode ? setJsonMode(false) : enterJsonMode())}
          className="rounded bg-neutral-800 px-3 py-1 text-xs text-neutral-200 hover:bg-neutral-700"
        >
          {jsonMode ? "Form view" : "Edit as JSON"}
        </button>
      </div>
      <p className="mt-1 text-xs text-neutral-400">
        Your soft preferences — watchlist, how you read bias, session and risk
        preferences. These are <span className="font-medium">judgment, not
        enforcement</span>: they inform the morning brief and the agent, but do
        not change your risk gates. For hard limits use{" "}
        <a href="/settings/risk-limits" className="text-blue-400 hover:underline">
          Settings → Risk Limits
        </a>
        . Edits are audit-logged.
      </p>

      {jsonMode ? (
        <div className="mt-6">
          <textarea
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            spellCheck={false}
            rows={24}
            className="w-full rounded bg-neutral-950 p-3 font-mono text-xs text-neutral-200"
          />
          {jsonError && <div className="mt-2 text-xs text-red-300">{jsonError}</div>}
          <div className="mt-2 flex justify-end">
            <button
              type="button"
              onClick={applyJson}
              className="rounded bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600"
            >
              Apply JSON
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          <Card title="Watchlist" help="Symbols to consider in scans and the morning brief.">
            <TextField
              label="Core (comma or newline separated)"
              value={listToCsv(wl.core)}
              onChange={(v) => setField("watchlist", "core", csvToList(v))}
              placeholder="AAPL, MSFT, GOOG"
            />
            <TextField
              label="Swing candidates"
              value={listToCsv(wl.swing_candidates)}
              onChange={(v) => setField("watchlist", "swing_candidates", csvToList(v))}
              placeholder="NVDA, TSLA"
            />
            <TextField
              label="Do not trade"
              value={listToCsv(wl.do_not_trade)}
              onChange={(v) => setField("watchlist", "do_not_trade", csvToList(v))}
              placeholder="GME, AMC"
            />
          </Card>

          <Card
            title="Bias Criteria"
            help="Free-form descriptions of your mental model. NOT used for automatic labeling — see Bias Thresholds below. For future agent reference."
          >
            {(["bullish", "bearish", "neutral"] as const).map((k) => (
              <label key={k} className="block text-xs capitalize text-neutral-400">
                {k}
                <textarea
                  rows={2}
                  value={typeof bc[k] === "string" ? (bc[k] as string) : ""}
                  onChange={(e) => setField("bias_criteria", k, e.target.value)}
                  className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 text-sm text-white"
                />
              </label>
            ))}
          </Card>

          <Card
            title="Bias Thresholds"
            help="The morning brief reads these to label each watchlist symbol. Leave a field blank to ignore it."
          >
            <div className="text-xs font-medium uppercase text-green-400">Bullish</div>
            <div className="grid grid-cols-3 gap-3">
              <NumberField
                label="RSI minimum"
                value={bull.rsi_min}
                onChange={(v) => setThreshold("bullish", "rsi_min", v)}
              />
              <TextField
                label="EMA relationship"
                value={typeof bull.ema_relationship === "string" ? (bull.ema_relationship as string) : ""}
                onChange={(v) => setThreshold("bullish", "ema_relationship", v)}
                placeholder="20>50"
              />
              <TextField
                label="Price vs VWAP"
                value={typeof bull.price_vs_vwap === "string" ? (bull.price_vs_vwap as string) : ""}
                onChange={(v) => setThreshold("bullish", "price_vs_vwap", v)}
                placeholder="above | below | any"
              />
            </div>
            <div className="text-xs font-medium uppercase text-red-400">Bearish</div>
            <div className="grid grid-cols-3 gap-3">
              <NumberField
                label="RSI maximum"
                value={bear.rsi_max}
                onChange={(v) => setThreshold("bearish", "rsi_max", v)}
              />
              <TextField
                label="EMA relationship"
                value={typeof bear.ema_relationship === "string" ? (bear.ema_relationship as string) : ""}
                onChange={(v) => setThreshold("bearish", "ema_relationship", v)}
                placeholder="20<50"
              />
              <TextField
                label="Price vs VWAP"
                value={typeof bear.price_vs_vwap === "string" ? (bear.price_vs_vwap as string) : ""}
                onChange={(v) => setThreshold("bearish", "price_vs_vwap", v)}
                placeholder="above | below | any"
              />
            </div>
          </Card>

          <Card title="Session Preferences">
            <CheckField
              label="Avoid overnight holds"
              value={sp.avoid_overnight_holds}
              onChange={(v) => setField("session_preferences", "avoid_overnight_holds", v)}
            />
            <TextField
              label="Preferred session hours"
              value={listToCsv(sp.preferred_hours)}
              onChange={(v) =>
                setField(
                  "session_preferences",
                  "preferred_hours",
                  v.split(",").map((s) => s.trim()).filter(Boolean),
                )
              }
              placeholder="09:30-11:00, 14:00-16:00"
            />
            <NumberField
              label="Max correlated positions"
              value={sp.max_correlated_positions}
              onChange={(v) => setField("session_preferences", "max_correlated_positions", v)}
            />
          </Card>

          <Card
            title="Risk Preferences"
            help="Preferences, not enforcement. For hard limits use Settings → Risk Limits."
          >
            <NumberField
              label="Preferred position size (% of equity)"
              value={rp.preferred_position_size_pct_equity}
              onChange={(v) =>
                setField("risk_preferences", "preferred_position_size_pct_equity", v)
              }
            />
            <NumberField
              label="Max simultaneous strategies"
              value={rp.max_strategies_simultaneously}
              onChange={(v) =>
                setField("risk_preferences", "max_strategies_simultaneously", v)
              }
            />
            <CheckField
              label="Prefer paper validation before going live"
              value={rp.prefer_paper_validation}
              onChange={(v) => setField("risk_preferences", "prefer_paper_validation", v)}
            />
          </Card>

          <Card
            title="Agent Envelope"
            help="How the P6 agent should behave when proposing strategy changes. Hard prohibitions, a free-form prompt note, and an optional per-day cost cap. Structured preferences can be edited via 'Edit as JSON'."
          >
            <label className="block text-xs text-neutral-400">
              Prohibitions (one per line)
              <textarea
                rows={3}
                value={listToLines(ae.prohibitions)}
                onChange={(e) =>
                  setField("agent_envelope", "prohibitions", linesToList(e.target.value))
                }
                placeholder={"never propose options\nnever increase position size"}
                className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 text-sm text-white"
              />
            </label>
            <label className="block text-xs text-neutral-400">
              Prompt augmentations (free-form note added to the agent's prompt)
              <textarea
                rows={2}
                value={typeof ae.prompt_augmentations === "string" ? (ae.prompt_augmentations as string) : ""}
                onChange={(e) => setField("agent_envelope", "prompt_augmentations", e.target.value)}
                placeholder="weight earnings season heavily for tech names"
                className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 text-sm text-white"
              />
            </label>
            <NumberField
              label="Cost envelope (cents per day; blank = default 200 = $2.00)"
              value={ae.cost_envelope_cents}
              onChange={(v) => setField("agent_envelope", "cost_envelope_cents", v)}
            />
            <CheckField
              label="Hide low-confidence proposals in the Proposals list"
              value={ae.hide_low_confidence_proposals}
              onChange={(v) => setField("agent_envelope", "hide_low_confidence_proposals", v)}
            />
            <label className="block text-xs text-neutral-400">
              Proposal cadence
              <select
                value={typeof ae.proposal_cadence === "string" ? (ae.proposal_cadence as string) : "off"}
                onChange={(e) => setField("agent_envelope", "proposal_cadence", e.target.value)}
                className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 text-sm text-white"
              >
                {CADENCE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <span className="mt-1 block text-neutral-500">
                Scheduled proposal generation. Each fire uses your cost envelope
                budget.
              </span>
              {!hasAgentApiKey && (
                <span className="mt-1 block text-amber-400">
                  ⚠ You haven't set an Agent API Key — scheduled cadence won't fire.
                  Add one under Settings → Credentials.
                </span>
              )}
            </label>
          </Card>
        </div>
      )}

      <div className="mt-6 flex items-center justify-end gap-2">
        {save.isError && <span className="text-xs text-red-300">Save failed.</span>}
        {save.isSuccess && <span className="text-xs text-green-300">Saved.</span>}
        <button
          type="button"
          onClick={onSave}
          disabled={save.isPending || jsonMode}
          title={jsonMode ? "Apply JSON first" : undefined}
          className="rounded bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
