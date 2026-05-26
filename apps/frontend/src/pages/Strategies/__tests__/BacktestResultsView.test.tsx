import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BacktestResultsView } from "../BacktestResultsView";
import type { BacktestResult } from "@/api/types";

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
    expect(screen.getByText("$15.00")).toBeInTheDocument();
  });
});
