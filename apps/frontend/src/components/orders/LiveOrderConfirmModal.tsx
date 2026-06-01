import { useEffect, useState } from "react";

interface Props {
  symbol: string;
  side: "buy" | "sell";
  qty: string;
  limitPrice?: string | null;
  stopPrice?: string | null;
  accountLabel: string;
  onConfirm: (confirmationText: string) => void;
  onCancel: () => void;
  submitting: boolean;
  error: string | null;
}

/**
 * P5 §6 — typed-ticker confirmation for manual LIVE orders. The submit button
 * is disabled until the typed text matches the symbol (case-insensitive,
 * whitespace-stripped — mirrors the server-side check). ESC cancels; Enter
 * submits when matched.
 *
 * Ships ready for the P5 §7 wizard, which lifts the live-submit block in the
 * Order Ticket and gates manual LIVE submits through this modal. The server
 * enforces the same check regardless of the UI (it's the real defense).
 */
export function LiveOrderConfirmModal(props: Props) {
  const [confirmation, setConfirmation] = useState("");

  const symbolUpper = props.symbol.trim().toUpperCase();
  const confirmationUpper = confirmation.trim().toUpperCase();
  const matches = confirmationUpper === symbolUpper && confirmationUpper.length > 0;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") props.onCancel();
      if (e.key === "Enter" && matches && !props.submitting) {
        props.onConfirm(confirmation);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [matches, confirmation, props]);

  const priceLine = props.limitPrice
    ? `LIMIT @ $${props.limitPrice}`
    : props.stopPrice
      ? `STOP @ $${props.stopPrice}`
      : "MARKET";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-[28rem] space-y-3 rounded-lg border-2 border-red-700 bg-neutral-950 p-5">
        <div className="flex items-center gap-2">
          <span className="rounded bg-red-700 px-2 py-0.5 text-[10px] font-bold text-white">
            LIVE
          </span>
          <h2 className="text-lg font-semibold text-red-100">Confirm live order</h2>
        </div>

        <div className="rounded border border-red-800 bg-red-950/40 p-3 text-sm">
          <div className="flex items-baseline gap-2">
            <span className="text-xs text-red-300">Account:</span>
            <span className="font-mono text-red-100">{props.accountLabel}</span>
          </div>
          <div className="mt-2 font-mono text-base text-white">
            {props.side.toUpperCase()} {props.qty} {symbolUpper}
          </div>
          <div className="mt-1 font-mono text-xs text-red-200">{priceLine}</div>
        </div>

        <p className="text-xs text-amber-200">
          This will send a real order to the broker. Type the symbol{" "}
          <code className="rounded bg-neutral-800 px-1 font-mono text-amber-100">
            {symbolUpper}
          </code>{" "}
          to confirm.
        </p>

        <input
          ref={(el) => el?.focus()}
          type="text"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
          placeholder="symbol"
          className="w-full rounded bg-neutral-800 px-2 py-1.5 font-mono text-sm text-white"
          autoComplete="off"
          spellCheck={false}
          disabled={props.submitting}
        />

        {props.error && (
          <div className="rounded border border-red-700 bg-red-950/60 p-2 text-xs text-red-100">
            {props.error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={props.onCancel}
            disabled={props.submitting}
            className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-600"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => props.onConfirm(confirmation)}
            disabled={!matches || props.submitting}
            className="rounded bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-600 disabled:bg-neutral-700"
          >
            {props.submitting ? "Submitting…" : "Submit LIVE order"}
          </button>
        </div>
      </div>
    </div>
  );
}
