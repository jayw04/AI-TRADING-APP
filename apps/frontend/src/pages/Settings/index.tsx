import { Link } from "react-router-dom";

export default function Settings() {
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-lg font-semibold text-neutral-100">Settings</h1>
      <div className="mt-6 space-y-3">
        <Link
          to="/settings/credentials"
          className="block rounded-lg border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700"
        >
          <div className="text-sm font-medium text-neutral-100">Credentials</div>
          <div className="mt-1 text-xs text-neutral-400">
            Manage broker keys, the Anthropic API key, and your TradingView Pine
            webhook secret. Encrypted at rest.
          </div>
        </Link>
        <Link
          to="/settings/risk-limits"
          className="block rounded-lg border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700"
        >
          <div className="text-sm font-medium text-neutral-100">Risk Limits</div>
          <div className="mt-1 text-xs text-neutral-400">
            Per-mode position, exposure, daily-loss, and order-rate caps. Live
            circuit-breaker state + reset. Edits are audit-logged.
          </div>
        </Link>
        <Link
          to="/settings/trading-profile"
          className="block rounded-lg border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700"
        >
          <div className="text-sm font-medium text-neutral-100">Trading Profile</div>
          <div className="mt-1 text-xs text-neutral-400">
            Your watchlist, bias criteria and thresholds, and session/risk
            preferences. Soft judgment that informs the morning brief and agent —
            not enforcement. Edits are audit-logged.
          </div>
        </Link>
        <Link
          to="/settings/accounts"
          className="block rounded-lg border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700"
        >
          <div className="text-sm font-medium text-neutral-100">Accounts</div>
          <div className="mt-1 text-xs text-neutral-400">
            Broker accounts. Create a LIVE account (TOTP-gated) to open the live
            trading path.
          </div>
        </Link>
        <Link
          to="/settings/live-trading"
          className="block rounded-lg border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700"
        >
          <div className="text-sm font-medium text-neutral-100">Live Trading</div>
          <div className="mt-1 text-xs text-neutral-400">
            The global live auto-dispatch master switch (default OFF). Lets LIVE
            strategies place real-money orders automatically. TOTP-gated; audit-logged.
          </div>
        </Link>
      </div>
    </div>
  );
}
