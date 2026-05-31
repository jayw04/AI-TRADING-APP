import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accountApi } from "@/api/account";
import { ordersApi } from "@/api/orders";
import { quotesApi } from "@/api/quotes";
import type {
  Order,
  OrderCreateRequest,
  OrderSide,
  OrderType,
  TimeInForce,
} from "@/api/types";
import { ApiError } from "@/api/client";
import { describeReasons } from "@/lib/risk-reasons";
import { formatMoney, formatNumber } from "@/lib/format";

interface TicketFormState {
  symbol: string;
  side: OrderSide;
  qty: string;
  type: OrderType;
  limit_price: string;
  stop_price: string;
  tif: TimeInForce;
  extended_hours: boolean;
}

const INITIAL_STATE: TicketFormState = {
  symbol: "",
  side: "buy",
  qty: "1",
  type: "market",
  limit_price: "",
  stop_price: "",
  tif: "day",
  extended_hours: false,
};

type Result =
  | { kind: "idle" }
  | { kind: "risk_rejected"; order: Order }
  | { kind: "broker_rejected"; order: Order }
  | { kind: "accepted"; order: Order }
  | { kind: "error"; message: string };

export default function OrderTicket() {
  const [form, setForm] = useState<TicketFormState>(INITIAL_STATE);
  const [result, setResult] = useState<Result>({ kind: "idle" });
  const queryClient = useQueryClient();

  const symbolNormalized = useMemo(
    () => form.symbol.trim().toUpperCase(),
    [form.symbol],
  );

  const account = useQuery({
    queryKey: ["account"],
    queryFn: accountApi.get,
    refetchInterval: 10_000,
    retry: false,
  });
  const isLive = account.data?.mode === "live";

  const quote = useQuery({
    queryKey: ["quote", symbolNormalized],
    queryFn: () => quotesApi.get(symbolNormalized),
    enabled: symbolNormalized.length > 0,
    refetchInterval: symbolNormalized.length > 0 ? 5_000 : false,
    retry: false,
  });

  const submitMutation = useMutation({
    mutationFn: (body: OrderCreateRequest) => ordersApi.create(body),
    onSuccess: (order) => {
      if (order.status === "rejected" && order.risk_check?.decision === "reject") {
        setResult({ kind: "risk_rejected", order });
      } else if (order.status === "rejected") {
        setResult({ kind: "broker_rejected", order });
      } else {
        setResult({ kind: "accepted", order });
      }
      void queryClient.invalidateQueries({ queryKey: ["orders"] });
      void queryClient.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (err: unknown) => {
      const message =
        err instanceof ApiError
          ? typeof err.body === "object" && err.body && "detail" in err.body
            ? String((err.body as { detail: unknown }).detail)
            : `Request failed (${err.status})`
          : err instanceof Error
            ? err.message
            : "Request failed";
      setResult({ kind: "error", message });
    },
  });

  useEffect(() => {
    if (result.kind === "idle") return;
    if (submitMutation.isPending) return;
    // result auto-clears on next user edit — see handleChange
  }, [result, submitMutation.isPending]);

  function patch(next: Partial<TicketFormState>) {
    setForm((prev) => ({ ...prev, ...next }));
    if (result.kind !== "idle") setResult({ kind: "idle" });
  }

  function assembleBody(): OrderCreateRequest | null {
    const qty = form.qty.trim();
    if (!symbolNormalized) {
      setResult({ kind: "error", message: "Symbol is required" });
      return null;
    }
    if (!qty || Number(qty) <= 0) {
      setResult({ kind: "error", message: "Qty must be greater than zero" });
      return null;
    }
    const needsLimit = form.type === "limit" || form.type === "stop_limit";
    const needsStop = form.type === "stop" || form.type === "stop_limit";
    if (needsLimit && (!form.limit_price || Number(form.limit_price) <= 0)) {
      setResult({ kind: "error", message: "Limit price is required for this order type" });
      return null;
    }
    if (needsStop && (!form.stop_price || Number(form.stop_price) <= 0)) {
      setResult({ kind: "error", message: "Stop price is required for this order type" });
      return null;
    }
    return {
      symbol: symbolNormalized,
      side: form.side,
      qty,
      type: form.type,
      tif: form.tif,
      extended_hours: form.extended_hours,
      limit_price: needsLimit ? form.limit_price : null,
      stop_price: needsStop ? form.stop_price : null,
    };
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // P5 §1: live submission is not yet enabled — the backend OrderRouter
    // refuses every live account (P5 §2 wires the real adapter). The submit
    // button is disabled in live mode; this guard is belt-and-suspenders.
    if (isLive) return;
    const body = assembleBody();
    if (!body) return;
    submitMutation.mutate(body);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg bg-neutral-900 border border-neutral-800 p-5 grid gap-4"
    >
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-300">
          Order Ticket
        </h3>
        <ModePill mode={account.data?.mode} />
      </div>

      {isLive && (
        <div
          role="alert"
          className="rounded border-2 border-rose-700 bg-rose-950/40 p-3"
        >
          <div className="text-sm font-bold text-rose-100">⚠ LIVE ACCOUNT</div>
          <div className="mt-1 text-xs text-rose-200">
            Live trading is not yet enabled in this version (P5 §2 release
            notes). Switch to a paper account or wait for the live release.
          </div>
        </div>
      )}

      <Field label="Symbol">
        <input
          aria-label="Symbol"
          className={inputClass}
          value={form.symbol}
          onChange={(e) => patch({ symbol: e.target.value })}
          placeholder="AAPL"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={16}
        />
      </Field>

      <QuoteStrip
        symbol={symbolNormalized}
        loading={quote.isFetching && !quote.data}
        error={quote.error}
        quote={quote.data}
      />

      <div className="grid grid-cols-2 gap-3">
        <SideToggle value={form.side} onChange={(v) => patch({ side: v })} />
        <Field label="Qty">
          <input
            aria-label="Qty"
            className={inputClass}
            value={form.qty}
            onChange={(e) => patch({ qty: e.target.value })}
            inputMode="decimal"
            placeholder="100"
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Type">
          <select
            aria-label="Order type"
            className={inputClass}
            value={form.type}
            onChange={(e) => patch({ type: e.target.value as OrderType })}
          >
            <option value="market">Market</option>
            <option value="limit">Limit</option>
            <option value="stop">Stop</option>
            <option value="stop_limit">Stop-limit</option>
          </select>
        </Field>
        <Field label="Time-in-force">
          <select
            aria-label="Time in force"
            className={inputClass}
            value={form.tif}
            onChange={(e) => patch({ tif: e.target.value as TimeInForce })}
          >
            <option value="day">Day</option>
            <option value="gtc">GTC</option>
            <option value="ioc">IOC</option>
            <option value="fok">FOK</option>
          </select>
        </Field>
      </div>

      {(form.type === "limit" || form.type === "stop_limit") && (
        <Field label="Limit price">
          <input
            aria-label="Limit price"
            className={inputClass}
            value={form.limit_price}
            onChange={(e) => patch({ limit_price: e.target.value })}
            inputMode="decimal"
            placeholder="0.00"
          />
        </Field>
      )}

      {(form.type === "stop" || form.type === "stop_limit") && (
        <Field label="Stop price">
          <input
            aria-label="Stop price"
            className={inputClass}
            value={form.stop_price}
            onChange={(e) => patch({ stop_price: e.target.value })}
            inputMode="decimal"
            placeholder="0.00"
          />
        </Field>
      )}

      <label className="flex items-center gap-2 text-sm text-neutral-300">
        <input
          type="checkbox"
          checked={form.extended_hours}
          onChange={(e) => patch({ extended_hours: e.target.checked })}
          className="size-4"
        />
        Extended hours (limit/day only)
      </label>

      <button
        type="submit"
        disabled={submitMutation.isPending || isLive}
        className={`rounded px-4 py-2 text-sm font-semibold transition-colors ${
          isLive
            ? "bg-neutral-700 text-neutral-300 cursor-not-allowed"
            : form.side === "buy"
              ? "bg-emerald-600 hover:bg-emerald-500 text-white"
              : "bg-rose-600 hover:bg-rose-500 text-white"
        } disabled:opacity-60`}
      >
        {isLive
          ? "Submit (live disabled)"
          : submitMutation.isPending
            ? "Submitting…"
            : `${form.side === "buy" ? "Buy" : "Sell"} ${symbolNormalized || "—"}`}
      </button>

      <ResultBanner result={result} />
    </form>
  );
}

function ModePill({ mode }: { mode: string | undefined }) {
  if (mode === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
        <span className="size-1.5 rounded-full bg-white animate-pulse" />
        Live
      </span>
    );
  }
  if (mode === "paper") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-950">
        <span className="size-1.5 rounded-full bg-amber-950" />
        Paper
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-neutral-800 px-2 py-0.5 text-[10px] uppercase tracking-wider text-neutral-400">
      <span className="size-1.5 rounded-full bg-neutral-500" />
      Connecting
    </span>
  );
}

const inputClass =
  "w-full bg-neutral-950 border border-neutral-800 rounded px-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-600 focus:outline-none focus:border-neutral-600";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-[11px] uppercase tracking-wider text-neutral-500">{label}</span>
      {children}
    </label>
  );
}

function SideToggle({
  value,
  onChange,
}: {
  value: OrderSide;
  onChange: (v: OrderSide) => void;
}) {
  return (
    <div className="grid gap-1.5">
      <span className="text-[11px] uppercase tracking-wider text-neutral-500">Side</span>
      <div role="radiogroup" aria-label="Side" className="grid grid-cols-2 gap-1 rounded border border-neutral-800 p-1 bg-neutral-950">
        {(["buy", "sell"] as const).map((s) => (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={value === s}
            onClick={() => onChange(s)}
            className={`rounded py-1.5 text-sm font-semibold transition-colors ${
              value === s
                ? s === "buy"
                  ? "bg-emerald-600 text-white"
                  : "bg-rose-600 text-white"
                : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            {s.toUpperCase()}
          </button>
        ))}
      </div>
    </div>
  );
}

function QuoteStrip({
  symbol,
  loading,
  error,
  quote,
}: {
  symbol: string;
  loading: boolean;
  error: unknown;
  quote:
    | {
        bid: string | null;
        ask: string | null;
        last: string | null;
        bid_size: number | null;
        ask_size: number | null;
      }
    | undefined;
}) {
  if (!symbol) {
    return (
      <div className="rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-neutral-500">
        Enter a symbol to see a live quote.
      </div>
    );
  }
  if (loading) {
    return (
      <div className="rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-neutral-400">
        Loading quote for {symbol}…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded border border-amber-800/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
        Quote unavailable (IEX free feed may not cover {symbol}).
      </div>
    );
  }
  if (!quote) return null;
  return (
    <div className="rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs grid grid-cols-3 gap-3">
      <QuoteCell label="Bid" value={quote.bid} size={quote.bid_size} className="text-emerald-400" />
      <QuoteCell label="Last" value={quote.last} className="text-neutral-100" />
      <QuoteCell label="Ask" value={quote.ask} size={quote.ask_size} className="text-rose-400" />
    </div>
  );
}

function QuoteCell({
  label,
  value,
  size,
  className,
}: {
  label: string;
  value: string | null;
  size?: number | null;
  className: string;
}) {
  return (
    <div className="grid gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-neutral-500">{label}</span>
      <span className={`font-mono ${className}`}>{formatMoney(value)}</span>
      {size != null ? (
        <span className="text-[10px] text-neutral-500">x{formatNumber(size, 0)}</span>
      ) : null}
    </div>
  );
}

function ResultBanner({ result }: { result: Result }) {
  if (result.kind === "idle") return null;
  if (result.kind === "risk_rejected") {
    const reasons = result.order.risk_check?.reason_codes ?? [];
    return (
      <div
        role="alert"
        className="rounded border border-amber-700/60 bg-amber-950/40 px-3 py-2 text-sm text-amber-100"
      >
        <div className="font-semibold">Rejected by risk engine</div>
        <div className="text-amber-200/80 text-xs mt-1">{describeReasons(reasons)}</div>
      </div>
    );
  }
  if (result.kind === "broker_rejected") {
    return (
      <div
        role="alert"
        className="rounded border border-rose-700/60 bg-rose-950/40 px-3 py-2 text-sm text-rose-100"
      >
        <div className="font-semibold">Broker rejected</div>
        <div className="text-rose-200/80 text-xs mt-1">
          {result.order.rejection_reason ?? "No reason supplied."}
        </div>
      </div>
    );
  }
  if (result.kind === "accepted") {
    const o = result.order;
    return (
      <div
        role="status"
        className="rounded border border-emerald-700/60 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-100"
      >
        <div className="font-semibold">Submitted</div>
        <div className="text-emerald-200/80 text-xs mt-1">
          {o.symbol} {o.side.toUpperCase()} {o.qty} — status {o.status}
        </div>
      </div>
    );
  }
  return (
    <div
      role="alert"
      className="rounded border border-rose-700/60 bg-rose-950/40 px-3 py-2 text-sm text-rose-100"
    >
      {result.message}
    </div>
  );
}
