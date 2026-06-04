import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { strategiesApi } from "@/api/strategies";
import type { Strategy } from "@/api/types";
import { ACTIVE_STRATEGY_STATUSES } from "@/api/types";
import { StatusBadge } from "@/components/strategies/StatusBadge";
import { OverviewTab } from "./tabs/OverviewTab";
import { SignalsTab } from "./tabs/SignalsTab";
import { OrdersTab } from "./tabs/OrdersTab";
import { BacktestsTab } from "./tabs/BacktestsTab";
import { ParamsTab } from "./tabs/ParamsTab";
import { CooldownIndicator } from "@/components/strategies/CooldownIndicator";
import { DriftCard } from "@/components/strategies/DriftCard";
import { VariantCard } from "@/components/strategies/VariantCard";
import { ActivationWizard } from "@/components/activation/ActivationWizard";
import { ActivationCountdown } from "@/components/activation/ActivationCountdown";
import { DeactivationModal } from "@/components/activation/DeactivationModal";

type Tab = "overview" | "signals" | "orders" | "backtests" | "params";

const TAB_LABELS: Record<Tab, string> = {
  overview: "Overview",
  signals: "Signals",
  orders: "Orders",
  backtests: "Backtests",
  params: "Params",
};

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const sid = id ? parseInt(id, 10) : NaN;
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [deactivateOpen, setDeactivateOpen] = useState(false);

  const load = useCallback(async () => {
    if (Number.isNaN(sid)) return;
    try {
      const s = await strategiesApi.get(sid);
      setStrategy(s);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [sid]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  async function handleStart() {
    if (!strategy) return;
    if (!confirm(`Start "${strategy.name}" on paper?`)) return;
    try {
      await strategiesApi.start(strategy.id);
      await load();
    } catch (e) { alert(`Start failed: ${e}`); }
  }

  async function handleStop() {
    if (!strategy) return;
    if (!confirm(`Stop "${strategy.name}"?`)) return;
    try {
      await strategiesApi.stop(strategy.id);
      await load();
    } catch (e) { alert(`Stop failed: ${e}`); }
  }

  async function handleReload() {
    if (!strategy) return;
    if (!confirm(`Reload "${strategy.name}" from disk? Running code will be replaced with the new version.`)) return;
    setReloading(true);
    try {
      await strategiesApi.reload(strategy.id);
      await load();
    } catch (e) {
      alert(`Reload failed: ${e}`);
    } finally {
      setReloading(false);
    }
  }

  if (Number.isNaN(sid)) {
    return <div className="p-4 text-red-400">Invalid strategy id</div>;
  }

  if (error) {
    return (
      <div className="p-4 text-red-400">
        Could not load strategy: {error}{" "}
        <Link to="/strategies" className="ml-2 underline text-blue-400">Back</Link>
      </div>
    );
  }

  if (!strategy) {
    return <div className="p-4 text-gray-400">Loading…</div>;
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-start justify-between">
        <div>
          <Link to="/strategies" className="text-xs text-blue-400 hover:underline">
            ← All strategies
          </Link>
          <h1 className="mt-1 text-xl font-semibold text-white">
            {strategy.name} <span className="text-sm text-gray-400">v{strategy.version}</span>
          </h1>
          <div className="mt-1 flex items-center gap-3 text-sm text-gray-300">
            <StatusBadge status={strategy.status} />
            <span className="font-mono text-xs text-gray-500">{strategy.code_path}</span>
            <span>Symbols: {strategy.symbols.join(", ")}</span>
          </div>
          {strategy.status === "error" && strategy.error_text && (
            <div className="mt-2 rounded border border-rose-700 bg-rose-900/30 p-2 text-sm text-rose-200">
              <span className="font-semibold">Error:</span> {strategy.error_text}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* P5 §7: live activation / deactivation controls. */}
          {(strategy.status === "idle" || strategy.status === "paper") && (
            <button onClick={() => setWizardOpen(true)}
                    className="rounded border border-red-700 px-3 py-1.5 text-sm font-semibold text-red-100 hover:bg-red-900/30">
              Activate for live…
            </button>
          )}
          {(strategy.status === "live" || strategy.status === "halted") && (
            <button onClick={() => setDeactivateOpen(true)}
                    className="rounded bg-amber-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-600">
              Deactivate
            </button>
          )}
          {ACTIVE_STRATEGY_STATUSES.includes(strategy.status) ? (
            <button onClick={handleStop}
                    className="rounded bg-red-800 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-700">
              Stop
            </button>
          ) : (
            <button onClick={handleStart}
                    disabled={strategy.status === "error"}
                    className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-600 disabled:bg-gray-700">
              Start (paper)
            </button>
          )}
        </div>
      </div>

      {strategy.status === "pending_live" && (
        <ActivationCountdown strategyId={strategy.id} />
      )}
      <CooldownIndicator strategyId={strategy.id} />
      {ACTIVE_STRATEGY_STATUSES.includes(strategy.status) && (
        <DriftCard strategyId={strategy.id} />
      )}
      {ACTIVE_STRATEGY_STATUSES.includes(strategy.status) && (
        <VariantCard strategy={strategy} />
      )}

      {wizardOpen && (
        <ActivationWizard
          strategyId={strategy.id}
          strategyName={strategy.name}
          symbols={strategy.symbols}
          onClose={() => setWizardOpen(false)}
          onActivated={() => {
            setWizardOpen(false);
            window.location.reload();
          }}
        />
      )}
      {deactivateOpen && (
        <DeactivationModal
          strategyId={strategy.id}
          strategyName={strategy.name}
          onClose={() => setDeactivateOpen(false)}
          onDeactivated={() => {
            setDeactivateOpen(false);
            window.location.reload();
          }}
        />
      )}

      {strategy.has_pending_reload && (
        <div
          data-testid="pending-reload-banner"
          className="flex items-center justify-between rounded border border-amber-600 bg-amber-900/30 p-3 text-sm text-amber-100"
        >
          <div>
            <div className="font-semibold">The strategy file has changed</div>
            <div className="mt-0.5 text-xs text-amber-200">
              The running code is still the old version. Click Reload to apply.
              {strategy.pending_reload_at && (
                <span className="ml-1 text-amber-300/70">
                  (detected {new Date(strategy.pending_reload_at).toLocaleString()})
                </span>
              )}
            </div>
          </div>
          <button
            onClick={handleReload}
            disabled={reloading}
            className="rounded bg-amber-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-600 disabled:bg-gray-700"
          >
            {reloading ? "Reloading…" : "Reload"}
          </button>
        </div>
      )}

      <div className="flex gap-1 border-b border-gray-800">
        {(Object.keys(TAB_LABELS) as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded-t px-3 py-1.5 text-sm ${
              tab === t ? "bg-gray-900 text-white" : "text-gray-400 hover:bg-gray-900/50"
            }`}>
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      <div>
        {tab === "overview" && <OverviewTab strategy={strategy} />}
        {tab === "signals" && <SignalsTab strategyId={strategy.id} />}
        {tab === "orders" && <OrdersTab strategyId={strategy.id} />}
        {tab === "backtests" && <BacktestsTab strategy={strategy} />}
        {tab === "params" && <ParamsTab strategy={strategy} onSaved={load} />}
      </div>
    </div>
  );
}
