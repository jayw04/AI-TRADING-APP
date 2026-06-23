import { useCallback, useEffect, useState } from "react";
import { opportunitiesApi } from "@/api/opportunities";
import type { OpportunitiesResponse } from "@/api/types";
import { useWorkbenchSocket } from "@/hooks/useWorkbenchSocket";
import { LiveSignalsWidget } from "./widgets/LiveSignalsWidget";
import { PineAlertsWidget } from "./widgets/PineAlertsWidget";
import { DiscoveryMatchesWidget } from "./widgets/DiscoveryMatchesWidget";
import { StrategyErrorsWidget } from "./widgets/StrategyErrorsWidget";
import { OpenOrdersExpiringWidget } from "./widgets/OpenOrdersExpiringWidget";
import { RiskRejectionsWidget } from "./widgets/RiskRejectionsWidget";
import { RecentFillsWidget } from "./widgets/RecentFillsWidget";
import { PremarketGappersWidget } from "./widgets/PremarketGappersWidget";

const POLL_INTERVAL_MS = 10_000;
const WS_TOPICS = ["signals", "strategies", "orders", "fills", "system"];

export default function OpportunitiesPage() {
  const [data, setData] = useState<OpportunitiesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await opportunitiesApi.get();
      setData(resp);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [load]);

  useWorkbenchSocket(WS_TOPICS, () => {
    void load();
  });

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-neutral-100">
            Opportunities
          </h2>
          <p className="text-xs text-neutral-500">
            What needs attention across the workbench. Auto-refreshes every
            10s.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {data?.as_of && (
            <span className="text-xs text-neutral-500">
              Updated {new Date(data.as_of).toLocaleTimeString()}
            </span>
          )}
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <LiveSignalsWidget
          items={data?.live_signals.items ?? []}
          count={data?.live_signals.count ?? 0}
          asOf={data?.live_signals.as_of ?? ""}
        />
        <PineAlertsWidget
          items={data?.pine_alerts.items ?? []}
          count={data?.pine_alerts.count ?? 0}
          asOf={data?.pine_alerts.as_of ?? ""}
        />
        <DiscoveryMatchesWidget
          items={data?.discovery_matches.items ?? []}
          count={data?.discovery_matches.count ?? 0}
          asOf={data?.discovery_matches.as_of ?? ""}
        />
        <StrategyErrorsWidget
          items={data?.strategy_errors.items ?? []}
          count={data?.strategy_errors.count ?? 0}
          asOf={data?.strategy_errors.as_of ?? ""}
        />
        <OpenOrdersExpiringWidget
          items={data?.open_orders_expiring.items ?? []}
          count={data?.open_orders_expiring.count ?? 0}
          asOf={data?.open_orders_expiring.as_of ?? ""}
        />
        <RiskRejectionsWidget
          items={data?.risk_rejections.items ?? []}
          count={data?.risk_rejections.count ?? 0}
          asOf={data?.risk_rejections.as_of ?? ""}
        />
        <RecentFillsWidget
          items={data?.recent_fills.items ?? []}
          count={data?.recent_fills.count ?? 0}
          asOf={data?.recent_fills.as_of ?? ""}
        />
        <PremarketGappersWidget
          items={data?.premarket_gappers.items ?? []}
          count={data?.premarket_gappers.count ?? 0}
          asOf={data?.premarket_gappers.as_of ?? ""}
          scannedAt={data?.premarket_gappers.scanned_at ?? null}
          date={data?.premarket_gappers.date ?? null}
          stale={data?.premarket_gappers.stale ?? true}
        />
      </div>
    </div>
  );
}
