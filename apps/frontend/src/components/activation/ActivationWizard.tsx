import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { activationApi } from "@/api/activation";
import type { ActivationStatus } from "@/api/activation";
import { ApiError } from "@/api/client";

interface Props {
  strategyId: number;
  strategyName: string;
  symbols: string[];
  onClose: () => void;
  onActivated: () => void;
}

type Step = "prerequisites" | "review" | "confirm";

/**
 * P5 §7 — activation wizard. Self-contained 3-step modal (prerequisites →
 * review → confirm-with-TOTP). The server re-verifies the typed name + TOTP +
 * all prerequisites on submit; the modal is convenience, the server is the gate.
 * Plain useEffect (no QueryClientProvider on the strategy detail page).
 */
export function ActivationWizard({
  strategyId,
  strategyName,
  symbols,
  onClose,
  onActivated,
}: Props) {
  const [step, setStep] = useState<Step>("prerequisites");
  const [status, setStatus] = useState<ActivationStatus | null>(null);
  const [confirmName, setConfirmName] = useState("");
  const [totp, setTotp] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    activationApi.status(strategyId).then(setStatus).catch(() => {});
  }, [strategyId]);

  async function handleActivate() {
    setSubmitting(true);
    setError(null);
    try {
      await activationApi.activate(strategyId, {
        confirmation_name: confirmName,
        totp_code: totp,
      });
      onActivated();
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 400
          ? "Activation refused — check the name, TOTP code, and prerequisites."
          : "Activation failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const stepLabel: Record<Step, string> = {
    prerequisites: "1. Prerequisites",
    review: "2. Review",
    confirm: "3. Confirm activation",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-[34rem] space-y-4 rounded-lg border-2 border-red-700 bg-neutral-950 p-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-red-700 px-2 py-0.5 text-[10px] font-bold text-white">
              LIVE
            </span>
            <h2 className="text-lg font-semibold text-red-100">
              Activate <code className="font-mono">{strategyName}</code> for live trading
            </h2>
          </div>
          <div className="mt-2 text-xs text-neutral-400">{stepLabel[step]}</div>
        </div>

        {!status ? (
          <div className="text-sm text-neutral-300">Loading prerequisites…</div>
        ) : step === "prerequisites" ? (
          <div className="space-y-2">
            {status.prerequisites.map((p) => (
              <div key={p.name} className="flex items-start gap-2 text-sm">
                <span className={p.satisfied ? "text-green-400" : "text-red-400"}>
                  {p.satisfied ? "✓" : "✗"}
                </span>
                <div>
                  <div className="text-neutral-200">{p.name}</div>
                  <div className="text-[10px] text-neutral-400">{p.detail}</div>
                </div>
              </div>
            ))}
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={onClose} className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-neutral-200">
                Cancel
              </button>
              <button
                onClick={() => setStep("review")}
                disabled={!status.all_satisfied}
                className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700"
              >
                Next
              </button>
            </div>
          </div>
        ) : step === "review" ? (
          <div className="space-y-2 text-sm text-neutral-300">
            <div>
              Strategy: <span className="font-mono text-neutral-100">{strategyName}</span>
            </div>
            <div>Symbols: {symbols.join(", ") || "—"}</div>
            <p className="text-xs text-amber-200">
              Review the LIVE risk limits before activating:{" "}
              <Link to="/settings/risk-limits" className="underline">
                Settings → Risk Limits
              </Link>
              .
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setStep("prerequisites")} className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-neutral-200">
                Back
              </button>
              <button onClick={() => setStep("confirm")} className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600">
                Next
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-neutral-300">
              Type the strategy name and a current TOTP code to start the 24-hour activation
              cooldown. You can cancel anytime during the cooldown.
            </p>
            <input
              type="text"
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
              placeholder="strategy name"
              className="w-full rounded bg-neutral-800 px-2 py-1.5 font-mono text-sm text-white"
              autoComplete="off"
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
              <button onClick={() => setStep("review")} className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-neutral-200">
                Back
              </button>
              <button
                onClick={handleActivate}
                disabled={submitting || confirmName !== strategyName || totp.length < 6}
                className="rounded bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-600 disabled:bg-neutral-700"
              >
                {submitting ? "Activating…" : "Activate"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
