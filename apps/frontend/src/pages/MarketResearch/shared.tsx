import type { ReactNode } from "react";
import { useMarket } from "@/markets/MarketContext";

export function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="rounded-lg bg-neutral-900 border border-neutral-800 p-5">
      <h3 className="text-base font-semibold text-neutral-100">{title}</h3>
      {subtitle && <p className="text-xs text-neutral-400 mt-0.5">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function Pill({ text, tone = "neutral" }: { text: string; tone?: "neutral" | "amber" | "sky" | "red" | "green" }) {
  const cls = {
    neutral: "bg-neutral-800 text-neutral-300",
    amber: "bg-amber-900 text-amber-300",
    sky: "bg-sky-900 text-sky-300",
    red: "bg-red-900 text-red-300",
    green: "bg-emerald-900 text-emerald-300",
  }[tone];
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>{text}</span>;
}

export function LabelPill({ text }: { text: string }) {
  return <Pill text={text} tone={text.startsWith("SYNTHETIC") ? "sky" : "amber"} />;
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  const market = useMarket();
  return (
    <div className="rounded-lg bg-neutral-900 border border-neutral-800 p-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">{title}</h2>
        <Pill text={market.label} />
        {market.researchOnly && <Pill text="RESEARCH ONLY" tone="sky" />}
      </div>
      <p className="text-xs text-neutral-500 mt-1">
        Amounts in {market.currencyLabel} · times in {market.timezone}
      </p>
      {children}
    </div>
  );
}

export function QueryState({ loading, error, what }: { loading: boolean; error: unknown; what: string }) {
  if (loading) return <p className="text-sm text-neutral-400">Loading {what}…</p>;
  if (error) {
    const msg = error instanceof Error ? error.message : "request failed";
    return (
      <p role="alert" className="text-sm text-red-400">
        Could not load {what}: {msg}
      </p>
    );
  }
  return null;
}
