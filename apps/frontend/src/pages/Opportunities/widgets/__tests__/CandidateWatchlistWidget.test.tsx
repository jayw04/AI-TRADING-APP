import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CandidateWatchlistWidget } from "../CandidateWatchlistWidget";
import type { OppCandidateWatchlistWidget, OppWatchlistItem } from "@/api/types";

function item(over: Partial<OppWatchlistItem> = {}): OppWatchlistItem {
  return {
    symbol: "NVDA",
    family_ids: ["OVERSOLD"],
    horizon: "1–10d",
    status: "Watch",
    name: "NVIDIA",
    sector: "Technology",
    chips: [
      { key: "rsi14", value: "24" },
      { key: "ret_5d", value: "-11.2%" },
    ],
    why: "quality-eligible name stretched to RSI<30 while the 200-day trend is intact",
    tradability: "not measured (Phase 1)",
    price_source: "sharadar.sep",
    close: 120.5,
    market_cap: 3e12,
    adv20: 4e9,
    ...over,
  };
}

function sample(): OppCandidateWatchlistWidget {
  const oversold = item();
  const gap = item({
    symbol: "XYZ",
    family_ids: ["GAP"],
    horizon: "hours–1d",
    status: "Backtest Pending",
  });
  const core = item({
    symbol: "JNJ",
    family_ids: ["MOM-CORE"],
    horizon: "weeks–months",
    status: "Source: MOM-001 · Pattern validated",
  });
  return {
    as_of: new Date().toISOString(),
    as_of_session: "2026-08-18",
    universe_id: "SEP-liquid-v0",
    screen_id: "DISC-001-WATCHLIST",
    screen_version: "v0.3.0",
    subtitle: "Watch, not a signal",
    vix: 18.4,
    families: {
      OVERSOLD: {
        family_id: "OVERSOLD",
        operator_name: "Oversold pullback",
        horizon: "1–10d",
        available: true,
        unavailable_reason: null,
        count: 1,
        items: [oversold],
      },
      GAP: {
        family_id: "GAP",
        operator_name: "Gap",
        horizon: "hours–1d",
        available: true,
        unavailable_reason: null,
        count: 1,
        items: [gap],
      },
      "MOM-CORE": {
        family_id: "MOM-CORE",
        operator_name: "Governed momentum",
        horizon: "weeks–months",
        available: true,
        unavailable_reason: null,
        count: 1,
        items: [core],
      },
    },
    all_items: [oversold, gap, core],
    all_count: 3,
    stale: false,
  };
}

describe("CandidateWatchlistWidget", () => {
  it("lists only pattern-validated names", () => {
    render(<CandidateWatchlistWidget watchlist={sample()} />);
    expect(screen.getByText("Candidate Watchlist")).toBeTruthy();
    expect(screen.getByText(/Watch, not a signal/)).toBeTruthy();
    expect(screen.getByText("JNJ")).toBeTruthy();
    expect(screen.queryByText("NVDA")).toBeNull();
    expect(screen.queryByText("XYZ")).toBeNull();
    expect(
      screen.getByText(/Watch and Backtest Pending names are not listed/),
    ).toBeTruthy();
  });

  it("does not list Oversold Watch names on the Oversold tab", () => {
    render(<CandidateWatchlistWidget watchlist={sample()} />);
    fireEvent.click(screen.getByRole("button", { name: /Oversold/i }));
    expect(screen.queryByText("NVDA")).toBeNull();
    expect(
      screen.getByText(/Oversold is Watch only — not listed until backtested/),
    ).toBeTruthy();
  });

  it("shows fail-closed copy when a family is unavailable", () => {
    const wl = sample();
    wl.families.OVERSOLD = {
      family_id: "OVERSOLD",
      operator_name: "Oversold pullback",
      horizon: "1–10d",
      available: false,
      unavailable_reason: "SEP as-of 2026-08-15, expected 2026-08-18",
      count: 0,
      items: [],
    };
    render(<CandidateWatchlistWidget watchlist={wl} />);
    fireEvent.click(screen.getByRole("button", { name: /Oversold/i }));
    expect(screen.getByText(/Oversold pullback unavailable/)).toBeTruthy();
  });

  it("has no apply-to-strategy control", () => {
    render(<CandidateWatchlistWidget watchlist={sample()} />);
    expect(screen.queryByRole("button", { name: /apply/i })).toBeNull();
  });
});
