import { useEffect, useState } from "react";
import { accountsApi } from "@/api/accounts";
import type { BrokerAccount } from "@/api/types";
import { ApiError } from "@/api/client";

/**
 * P5 §7 — Settings → Accounts. Lists the user's broker accounts and provides a
 * TOTP-gated LIVE account creation flow (the API requires a TOTP code for
 * mode=live).
 */
export default function Accounts() {
  const [accounts, setAccounts] = useState<BrokerAccount[]>([]);
  const [createOpen, setCreateOpen] = useState(false);

  async function refresh() {
    try {
      const r = await accountsApi.list();
      setAccounts(r.items);
    } catch {
      /* silent */
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const hasLive = accounts.some((a) => a.mode === "live");

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-lg font-semibold text-neutral-100">Accounts</h1>
      <p className="mt-1 text-xs text-neutral-400">
        Broker accounts. Creating a LIVE account requires a TOTP code and opens the live
        trading path (subject to the per-strategy activation wizard).
      </p>

      <div className="mt-6 space-y-2">
        {accounts.map((a) => (
          <div
            key={a.id}
            className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900 p-3"
          >
            <div className="text-sm text-neutral-200">
              {a.label ?? `${a.broker} account`}{" "}
              <span className="text-xs text-neutral-500">({a.broker})</span>
            </div>
            <span
              className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${
                a.mode === "live"
                  ? "bg-red-900/60 text-red-200"
                  : "bg-neutral-800 text-neutral-300"
              }`}
            >
              {a.mode}
            </span>
          </div>
        ))}
      </div>

      {!hasLive && (
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="mt-4 rounded border border-red-700 px-3 py-1.5 text-sm font-semibold text-red-100 hover:bg-red-900/30"
        >
          Create LIVE account…
        </button>
      )}

      {createOpen && (
        <CreateLiveAccountModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function CreateLiveAccountModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [label, setLabel] = useState("");
  const [totp, setTotp] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    setSubmitting(true);
    setError(null);
    try {
      await accountsApi.create("alpaca", "live", label, totp);
      onCreated();
    } catch (e) {
      setError(
        e instanceof ApiError && (e.status === 401 || e.status === 400)
          ? "Rejected — check the TOTP code."
          : "Creation failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-96 space-y-3 rounded-lg border-2 border-red-700 bg-neutral-950 p-5">
        <h2 className="text-lg font-semibold text-red-100">Create LIVE account</h2>
        <p className="text-xs text-amber-200">
          This opens the live trading path. A TOTP code is required.
        </p>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="account label"
          className="w-full rounded bg-neutral-800 px-2 py-1.5 text-sm text-white"
        />
        <input
          type="text"
          inputMode="numeric"
          value={totp}
          onChange={(e) => setTotp(e.target.value.replace(/\D/g, ""))}
          placeholder="TOTP code"
          maxLength={8}
          className="w-full rounded bg-neutral-800 px-2 py-1.5 font-mono text-sm text-white"
          autoComplete="one-time-code"
        />
        {error && (
          <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-neutral-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleCreate}
            disabled={submitting || !label || totp.length < 6}
            className="rounded bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-600 disabled:bg-neutral-700"
          >
            {submitting ? "Creating…" : "Create LIVE account"}
          </button>
        </div>
      </div>
    </div>
  );
}
