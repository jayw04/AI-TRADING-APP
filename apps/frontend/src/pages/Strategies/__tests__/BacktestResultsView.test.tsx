import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { BacktestResultsView } from "../BacktestResultsView";
import {
  computeDrawdown,
  computeTradeMarkers,
  computeTradeStats,
  transformEquityForChart,
} from "../backtestHelpers";
import type { BacktestResult, BacktestTradeT } from "@/api/types";

const result: BacktestResult = {
  id: 1,
  strategy_id: 1,
  label: "test",
  params: {},
  metrics: {
    total_return: 0.0523,
    annualized_return: 0.21,
    sharpe_ratio: 1.42,
    max_drawdown: -0.087,
    win_rate: 0.6,
    profit_factor: 1.85,
    trade_count: 25,
    avg_win: 120.5,
    avg_loss: -65.3,
    avg_trade_duration_seconds: 1820,
    starting_equity: 100000,
    ending_equity: 105230,
  },
  equity_curve: [
    { t: "2025-11-03T14:30:00Z", equity: 100000 },
    { t: "2025-11-04T16:00:00Z", equity: 102000 },
    { t: "2025-11-05T16:00:00Z", equity: 105230 },
  ],
  trades: [
    {
      symbol: "AAPL",
      side: "long",
      entry_ts: "2025-11-03T15:00:00Z",
      entry_price: 190.0,
      exit_ts: "2025-11-03T15:30:00Z",
      exit_price: 191.5,
      qty: 10,
      pnl: 15.0,
      duration_seconds: 1800,
      exit_reason: "rsi_exit",
    },
  ],
  range_start: "2025-11-03T00:00:00Z",
  range_end: "2025-11-06T00:00:00Z",
  created_at: "2025-11-06T00:00:00Z",
};

describe("BacktestResultsView", () => {
  it("renders metric values formatted correctly", () => {
    render(<BacktestResultsView result={result} onClose={() => {}} />);
    expect(screen.getByText("5.23%")).toBeInTheDocument();    // total return
    expect(screen.getByText("21.00%")).toBeInTheDocument();   // annualized
    expect(screen.getByText("1.42")).toBeInTheDocument();     // sharpe
    expect(screen.getByText("-8.70%")).toBeInTheDocument();   // max dd
    expect(screen.getByText("60.00%")).toBeInTheDocument();   // win rate
    expect(screen.getByText("25")).toBeInTheDocument();       // trade count
  });

  it("renders trade list with PnL color coding", () => {
    render(<BacktestResultsView result={result} onClose={() => {}} />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("rsi_exit")).toBeInTheDocument();
    // $15.00 now appears in both the trade table (trade's PnL) and the
    // Trade stats panel (best/median across the single-trade fixture).
    expect(screen.getAllByText("$15.00").length).toBeGreaterThanOrEqual(1);
  });
});

// ---------- P4 §6: helper unit tests ----------

describe("computeDrawdown", () => {
  it("returns [] for empty input", () => {
    expect(computeDrawdown([])).toEqual([]);
  });

  it("computes drawdown as a negative fraction from the running peak", () => {
    const dd = computeDrawdown([
      { t: "2025-11-03T00:00:00Z", equity: 100000 },
      { t: "2025-11-03T01:00:00Z", equity: 105000 }, // new peak
      { t: "2025-11-03T02:00:00Z", equity: 102000 }, // 3000 below peak
      { t: "2025-11-03T03:00:00Z", equity: 110000 }, // new peak
    ]);
    expect(dd[0].drawdown_pct).toBe(0);
    expect(dd[1].drawdown_pct).toBe(0);
    expect(dd[2].drawdown_pct).toBeCloseTo(-3000 / 105000, 5);
    expect(dd[3].drawdown_pct).toBe(0);
    // peak is monotonically non-decreasing
    expect(dd[3].peak).toBe(110000);
  });
});

describe("transformEquityForChart", () => {
  it("equity mode passes values through unchanged", () => {
    const out = transformEquityForChart(
      [
        { t: "2025-11-03T00:00:00Z", equity: 100000 },
        { t: "2025-11-03T01:00:00Z", equity: 105000 },
      ],
      "equity",
      100000,
    );
    expect(out[0].value).toBe(100000);
    expect(out[1].value).toBe(105000);
  });

  it("returns mode converts to percent from starting equity", () => {
    const out = transformEquityForChart(
      [
        { t: "2025-11-03T00:00:00Z", equity: 100000 },
        { t: "2025-11-03T01:00:00Z", equity: 110000 },
        { t: "2025-11-03T02:00:00Z", equity: 95000 },
      ],
      "returns",
      100000,
    );
    expect(out[0].value).toBeCloseTo(0, 5);
    expect(out[1].value).toBeCloseTo(10, 5);
    expect(out[2].value).toBeCloseTo(-5, 5);
  });

  it("returns mode falls back to first equity point when starting is 0", () => {
    const out = transformEquityForChart(
      [{ t: "2025-11-03T00:00:00Z", equity: 100 }],
      "returns",
      0,
    );
    // First point becomes the base → it lands at 0% by definition.
    expect(out[0].value).toBeCloseTo(0, 5);
  });
});

describe("computeTradeStats", () => {
  it("returns empty stats for no closed trades", () => {
    const s = computeTradeStats([]);
    expect(s.count).toBe(0);
    expect(s.best_pnl).toBe(0);
    expect(s.longest_win_streak).toBe(0);
  });

  it("computes streaks across consecutive wins", () => {
    const trades: BacktestTradeT[] = [
      {
        symbol: "X",
        side: "long",
        entry_ts: "2025-01-01T10:00:00Z",
        entry_price: 100,
        exit_ts: "2025-01-01T11:00:00Z",
        exit_price: 110,
        qty: 1,
        pnl: 10,
        duration_seconds: 3600,
        exit_reason: "x",
      },
      {
        symbol: "X",
        side: "long",
        entry_ts: "2025-01-02T10:00:00Z",
        entry_price: 100,
        exit_ts: "2025-01-02T11:00:00Z",
        exit_price: 105,
        qty: 1,
        pnl: 5,
        duration_seconds: 3600,
        exit_reason: "x",
      },
      {
        symbol: "X",
        side: "long",
        entry_ts: "2025-01-03T10:00:00Z",
        entry_price: 100,
        exit_ts: "2025-01-03T11:00:00Z",
        exit_price: 102,
        qty: 1,
        pnl: 2,
        duration_seconds: 3600,
        exit_reason: "x",
      },
      {
        symbol: "X",
        side: "long",
        entry_ts: "2025-01-04T10:00:00Z",
        entry_price: 100,
        exit_ts: "2025-01-04T11:00:00Z",
        exit_price: 95,
        qty: 1,
        pnl: -5,
        duration_seconds: 3600,
        exit_reason: "x",
      },
    ];
    const s = computeTradeStats(trades);
    expect(s.count).toBe(4);
    expect(s.wins).toBe(3);
    expect(s.losses).toBe(1);
    expect(s.longest_win_streak).toBe(3);
    expect(s.longest_loss_streak).toBe(1);
    expect(s.best_pnl).toBe(10);
    expect(s.worst_pnl).toBe(-5);
    expect(s.median_pnl).toBeCloseTo((5 + 2) / 2, 5);
  });

  it("excludes open trades (null exit_ts) from stats", () => {
    const trades: BacktestTradeT[] = [
      {
        symbol: "Y",
        side: "long",
        entry_ts: "2025-01-01T10:00:00Z",
        entry_price: 100,
        exit_ts: null,
        exit_price: null,
        qty: 1,
        pnl: null,
        duration_seconds: null,
        exit_reason: null,
      },
    ];
    const s = computeTradeStats(trades);
    expect(s.count).toBe(0);
  });
});

describe("computeTradeMarkers", () => {
  const curve = [
    { t: "2025-11-03T14:30:00Z", equity: 100000 },
    { t: "2025-11-03T16:00:00Z", equity: 101500 },
    { t: "2025-11-04T14:30:00Z", equity: 102000 },
  ];

  it("produces entry+exit markers per closed trade", () => {
    const trades: BacktestTradeT[] = [
      {
        symbol: "AAPL",
        side: "long",
        entry_ts: "2025-11-03T15:00:00Z",
        entry_price: 190,
        exit_ts: "2025-11-03T15:30:00Z",
        exit_price: 192,
        qty: 10,
        pnl: 20,
        duration_seconds: 1800,
        exit_reason: "x",
      },
    ];
    const markers = computeTradeMarkers(trades, curve, "equity", 100000);
    expect(markers).toHaveLength(2);
    expect(markers[0].kind).toBe("entry");
    expect(markers[1].kind).toBe("exit");
  });

  it("produces only an entry marker for open trades", () => {
    const open: BacktestTradeT = {
      symbol: "AAPL",
      side: "long",
      entry_ts: "2025-11-03T15:00:00Z",
      entry_price: 190,
      exit_ts: null,
      exit_price: null,
      qty: 10,
      pnl: null,
      duration_seconds: null,
      exit_reason: null,
    };
    const markers = computeTradeMarkers([open], curve, "equity", 100000);
    expect(markers).toHaveLength(1);
    expect(markers[0].kind).toBe("entry");
  });

  it("returns [] when there are no trades or the curve is empty", () => {
    expect(computeTradeMarkers([], curve, "equity", 100000)).toEqual([]);
    expect(computeTradeMarkers([], [], "equity", 100000)).toEqual([]);
  });
});

// ---------- P4 §6: component-level smoke ----------

describe("BacktestResultsView — P4 §6", () => {
  it("renders Drawdown section heading", () => {
    render(<BacktestResultsView result={result} onClose={() => {}} />);
    expect(screen.getByText("Drawdown (%)")).toBeInTheDocument();
  });

  it("renders Trade stats section with wins/losses count", () => {
    render(<BacktestResultsView result={result} onClose={() => {}} />);
    expect(screen.getByText("Trade stats")).toBeInTheDocument();
    // Single-trade fixture: 1 win (+$15.00), 0 losses.
    expect(screen.getByText("1 / 0")).toBeInTheDocument();
  });

  it("renders both mode toggle buttons", () => {
    render(<BacktestResultsView result={result} onClose={() => {}} />);
    expect(
      screen.getByRole("button", { name: "Equity ($)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Returns (%)" }),
    ).toBeInTheDocument();
  });

  it("clicking Returns (%) switches the chart header label", () => {
    render(<BacktestResultsView result={result} onClose={() => {}} />);
    // Before click: chart header reads "Equity ($)" (1 occurrence outside
    // of the toggle button label).
    fireEvent.click(screen.getByRole("button", { name: "Returns (%)" }));
    // After click: chart header reads "Returns (%)" — appears at least
    // twice (the toggle button label + the chart-section heading).
    expect(screen.getAllByText("Returns (%)").length).toBeGreaterThanOrEqual(2);
  });

  it("shows 'No closed trades' empty state in stats panel when trades list is empty", () => {
    const empty: BacktestResult = {
      ...result,
      trades: [],
      metrics: { ...result.metrics, trade_count: 0 },
    };
    render(<BacktestResultsView result={empty} onClose={() => {}} />);
    // Both the stats panel and the trade table render "No closed trades".
    expect(screen.getAllByText("No closed trades").length).toBeGreaterThanOrEqual(1);
  });
});
