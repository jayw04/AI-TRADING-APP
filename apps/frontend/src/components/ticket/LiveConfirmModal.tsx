import { useEffect, useState } from "react";
import type { OrderSide, OrderType } from "@/api/types";

interface Props {
  symbol: string;
  side: OrderSide;
  qty: string;
  type: OrderType;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function LiveConfirmModal({
  symbol,
  side,
  qty,
  type,
  onConfirm,
  onCancel,
}: Props) {
  const [understandLive, setUnderstandLive] = useState(false);
  const [understandUnsendable, setUnderstandUnsendable] = useState(false);
  const [typed, setTyped] = useState("");
  const ready =
    understandLive &&
    understandUnsendable &&
    typed.trim().toUpperCase() === symbol.toUpperCase();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="live-confirm-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
    >
      <div className="w-full max-w-md rounded-lg border-2 border-rose-600 bg-neutral-950 p-6 shadow-2xl">
        <h2
          id="live-confirm-title"
          className="text-base font-bold text-rose-400 uppercase tracking-wide"
        >
          ⚠ Confirm live order
        </h2>
        <p className="mt-2 text-sm text-neutral-300">
          You are about to place a{" "}
          <span className="font-bold text-rose-300">REAL</span> order against
          Alpaca's <span className="font-bold text-rose-300">live</span> account.
        </p>

        <div className="mt-4 rounded border border-rose-800/60 bg-rose-950/30 p-3 text-sm">
          <span
            className={`font-semibold ${
              side === "buy" ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {side.toUpperCase()}
          </span>{" "}
          <span className="font-mono text-neutral-100">{qty}</span>{" "}
          <span className="font-bold text-neutral-100">{symbol}</span>{" "}
          <span className="text-neutral-400">({type.replace("_", "-")})</span>
        </div>

        <div className="mt-4 space-y-3 text-sm text-neutral-300">
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={understandLive}
              onChange={(e) => setUnderstandLive(e.target.checked)}
              className="mt-0.5 size-4"
            />
            <span>I understand this is a live order.</span>
          </label>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={understandUnsendable}
              onChange={(e) => setUnderstandUnsendable(e.target.checked)}
              className="mt-0.5 size-4"
            />
            <span>I understand orders cannot be un-sent once accepted.</span>
          </label>
          <label className="grid gap-1.5">
            <span>
              Type{" "}
              <span className="font-mono text-neutral-100">{symbol}</span> to
              confirm:
            </span>
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoCapitalize="characters"
              spellCheck={false}
              className="w-full rounded border border-neutral-800 bg-neutral-900 px-3 py-2 font-mono text-sm text-neutral-100 focus:outline-none focus:border-neutral-600"
            />
          </label>
        </div>

        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded bg-neutral-800 py-2 text-sm font-semibold text-neutral-200 hover:bg-neutral-700"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!ready}
            className="flex-1 rounded bg-rose-700 py-2 text-sm font-semibold text-white hover:bg-rose-600 disabled:bg-neutral-800 disabled:text-neutral-500"
          >
            Submit live order
          </button>
        </div>
      </div>
    </div>
  );
}
