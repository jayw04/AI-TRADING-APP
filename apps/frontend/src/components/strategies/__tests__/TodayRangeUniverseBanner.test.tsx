import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import {
  TodayRangeUniverseBanner,
  autoSelectN,
} from "../TodayRangeUniverseBanner";
import type { Strategy } from "@/api/types";

function strat(over: Partial<Strategy>): Strategy {
  return {
    id: 1, name: "Range", symbols: [], params: {}, type: "python", status: "paper",
    code_path: "templates/range_trader.py", updated_at: "2026-06-26T13:00:00Z",
    ...over,
  } as unknown as Strategy;
}

function renderBanner(strategies: Strategy[]) {
  return render(
    <MemoryRouter>
      <TodayRangeUniverseBanner strategies={strategies} />
    </MemoryRouter>,
  );
}

describe("autoSelectN", () => {
  it("reads auto_select_top_n from params, 0 when absent/invalid", () => {
    expect(autoSelectN(strat({ params: { auto_select_top_n: 5 } }))).toBe(5);
    expect(autoSelectN(strat({ params: {} }))).toBe(0);
    expect(autoSelectN(strat({ params: { auto_select_top_n: 0 } }))).toBe(0);
    expect(autoSelectN(strat({ params: { auto_select_top_n: "nope" } }))).toBe(0);
  });
});

describe("TodayRangeUniverseBanner", () => {
  it("lists today's auto-selected symbols for an auto-select strategy", () => {
    renderBanner([
      strat({ id: 7, name: "Range Top-5", params: { auto_select_top_n: 5 },
              symbols: ["AMD", "TSLA", "PLTR", "MU", "F"] }),
    ]);
    expect(screen.getByText("Today's range universe")).toBeInTheDocument();
    expect(screen.getByText("Range Top-5")).toBeInTheDocument();
    expect(screen.getByText("Top 5")).toBeInTheDocument();
    for (const sym of ["AMD", "TSLA", "PLTR", "MU", "F"]) {
      expect(screen.getByText(sym)).toBeInTheDocument();
    }
  });

  it("renders nothing when no strategy auto-selects", () => {
    const { container } = renderBanner([
      strat({ params: {}, symbols: ["NVDA"] }),
    ]);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a placeholder when an auto-select strategy has no symbols yet", () => {
    renderBanner([strat({ params: { auto_select_top_n: 5 }, symbols: [] })]);
    expect(screen.getByText(/not selected yet/i)).toBeInTheDocument();
  });
});
