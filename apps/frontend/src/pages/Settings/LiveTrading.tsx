import { useEffect, useState } from "react";
import { liveAutodispatchApi } from "@/api/liveAutodispatch";
import { ApiError } from "@/api/client";

/**
 * P6b §4.5 (ADR 0015) — Settings → Live Trading. The global live-auto-dispatch
 * master switch. Default OFF: while off, LIVE strategies do NOT place automatic
 * real-money orders (manual live orders via the Trade page are unaffected).
 * Flipping it is a TOTP-gated, audit-logged operator action.
 */
export default function LiveTrading() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  async function refresh() {
    try {
      const r = await liveAutodispatchApi.status();
      setEnabled(r.enabled);
    } catch {
      /* silent */
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-lg font-semibold text-neutral-100">Live Trading</h1>
      <p className="mt-1 text-xs text-neutral-400">
        The global <span className="font-semibold">live auto-dispatch</span> master
        switch. While OFF, a LIVE strategy never places automatic real-money orders —
        its signals are suppressed before the broker. Manual live orders (the Trade
        page) are unaffected. Flipping it is TOTP-gated and audit-logged.
      </p>

      <div className="mt-6 flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900 p-4">
        <div>
          <div className="text-sm font-medium text-neutral-100">
            Live strategy auto-dispatch
          </div>
          <div className="mt-1 text-xs text-neutral-400">
            {enabled === null
              ? "Loading…"
              : enabled
                ? "ON — LIVE strategies place real-money orders automatically."
                : "OFF — LIVE strategies do not auto-trade (default)."}
          </div>
        </div>
        <span
          className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${
            enabled
              ? "bg-red-900/60 text-red-200"
              : "bg-neutral-800 text-neutral-300"
          }`}
        >
          {enabled === null ? "—" : enabled ? "ON" : "OFF"}
        </span>
      </div>

      {enabled !== null && (
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className={`mt-4 rounded border px-3 py-1.5 text-sm font-semibold ${
            enabled
              ? "border-neutral-700 text-neutral-200 hover:bg-neutral-800"
              : "border-red-700 text-red-100 hover:bg-red-900/30"
          }`}
        >
          {enabled ? "Disable auto-dispatch…" : "Enable live auto-dispatch…"}
        </button>
      )}

      {modalOpen && enabled !== null && (
        <ConfirmModal
          enabling={!enabled}
          onClose={() => setModalOpen(false)}
          onDone={() => {
            setModalOpen(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function ConfirmModal({
  enabling,
  onClose,
  onDone,
}: {
  enabling: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [totp, setTotp] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setSubmitting(true);
    setError(null);
    try {
      await liveAutodispatchApi.set(enabling, totp);
      onDone();
    } catch (e) {
      setError(
        e instanceof ApiError && (e.status === 401 || e.status === 400)
          ? "Rejected — check the TOTP code."
          : "Update failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div
        className={`w-96 space-y-3 rounded-lg border-2 ${
          enabling ? "border-red-700" : "border-neutral-700"
        } bg-neutral-950 p-5`}
      >
        <h2 className="text-lg font-semibold text-neutral-100">
          {enabling ? "Enable live auto-dispatch" : "Disable live auto-dispatch"}
        </h2>
        <p className="text-xs text-amber-200">
          {enabling
            ? "This lets every LIVE strategy place real-money orders automatically, with no per-order confirmation. A TOTP code is required."
            : "This immediately halts all live auto-dispatch. A TOTP code is required."}
        </p>
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
            onClick={handleConfirm}
            disabled={submitting || totp.length < 6}
            className={`rounded px-3 py-1.5 text-sm font-semibold text-white disabled:bg-neutral-700 ${
              enabling ? "bg-red-700 hover:bg-red-600" : "bg-neutral-600 hover:bg-neutral-500"
            }`}
          >
            {submitting ? "Saving…" : enabling ? "Enable" : "Disable"}
          </button>
        </div>
      </div>
    </div>
  );
}
