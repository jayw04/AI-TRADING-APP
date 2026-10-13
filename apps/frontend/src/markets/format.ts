import type { MarketConfig } from "./registry";

/** Money in the market's own currency (RMB for A-shares, USD for US). */
export function formatMoney(value: number | null | undefined, market: MarketConfig, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(market.locale, {
    style: "currency",
    currency: market.currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** A UTC instant shown in the market's timezone, e.g. "2026-10-13 10:35 Asia/Shanghai". */
export function formatInstant(iso: string | null | undefined, market: MarketConfig): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: market.timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")} ${market.timezone}`;
}

/** The current wall-clock time in the market's timezone, HH:MM. */
export function marketClock(market: MarketConfig, now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: market.timezone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(now);
}
