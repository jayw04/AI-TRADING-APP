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
          to="/settings/accounts"
          className="block rounded-lg border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700"
        >
          <div className="text-sm font-medium text-neutral-100">Accounts</div>
          <div className="mt-1 text-xs text-neutral-400">
            Broker accounts. Create a LIVE account (TOTP-gated) to open the live
            trading path.
          </div>
        </Link>
      </div>
    </div>
  );
}
