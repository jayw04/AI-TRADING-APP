/**
 * P8 §6 — Range Insight panel. The api module is mocked; covers the ok /
 * low-confidence / insufficient-data / 503 paths + the disclaimer + collapse.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import RangeInsightPanel from "../RangeInsightPanel";
import { rangeInsightApi, type RangeInsight } from "@/api/rangeInsight";

vi.mock("@/api/rangeInsight", () => ({
  rangeInsightApi: { get: vi.fn() },
}));
const mocked = vi.mocked(rangeInsightApi, true);

const OK: RangeInsight = {
  symbol: "AAPL",
  status: "ok",
  bars_used: 20,
  low_confidence: false,
  as_of: "2026-06-08T00:00:00Z",
  anchor: 100,
  anchor_source: "last_close",
  last_close: 100,
  atr20: 5.4,
  atr20_pct: 0.021,
  typical_move_up: { mean: 3.2, median: 3.0, p80: 4.1 },
  typical_move_down: { mean: 2.8, median: 2.6, p80: 3.6 },
  support: 254,
  resistance: 268,
  high_band: { low: 263, high: 267 },
  low_band: { low: 256, high: 260 },
  intraday_range: null,
  classification: "range_bound",
  efficiency_ratio: 0.12,
  disclaimer: "Statistical descriptions of recent behavior, not forecasts.",
};

describe("RangeInsightPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the stats, classification, and disclaimer", async () => {
    mocked.get.mockResolvedValue(OK);
    render(<RangeInsightPanel symbol="AAPL" />);
    expect(await screen.findByText("Range-bound")).toBeTruthy();
    expect(screen.getByText(/\$5\.40 \(2\.1%\)/)).toBeTruthy(); // ATR
    expect(screen.getByText("$254.00 / $268.00")).toBeTruthy(); // S/R
    expect(screen.getByText(/\$263\.00–\$267\.00/)).toBeTruthy(); // high band
    expect(screen.getByText(/not forecasts/i)).toBeTruthy(); // disclaimer verbatim
  });

  it("shows the low-confidence note", async () => {
    mocked.get.mockResolvedValue({ ...OK, low_confidence: true, bars_used: 12 });
    render(<RangeInsightPanel symbol="AAPL" />);
    expect(await screen.findByText(/Limited history \(12 days\)/i)).toBeTruthy();
  });

  it("shows an insufficient-data message", async () => {
    mocked.get.mockResolvedValue({
      ...OK,
      status: "insufficient_data",
      bars_used: 4,
      atr20: null,
      support: null,
    });
    render(<RangeInsightPanel symbol="ZZZZ" />);
    expect(await screen.findByText(/Not enough history for ZZZZ \(4 days\)/i)).toBeTruthy();
  });

  it("surfaces a 503 as a market-data message", async () => {
    const { ApiError } = await import("@/api/client");
    mocked.get.mockRejectedValue(new ApiError(503, null));
    render(<RangeInsightPanel symbol="AAPL" />);
    expect(await screen.findByText(/Market data is unavailable/i)).toBeTruthy();
  });

  it("collapses and reopens", async () => {
    mocked.get.mockResolvedValue(OK);
    render(<RangeInsightPanel symbol="AAPL" />);
    await screen.findByText("Range-bound");
    fireEvent.click(screen.getByRole("button", { name: /Collapse Range Insight/i }));
    await waitFor(() => expect(screen.queryByText("Range-bound")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: /Show Range Insight/i }));
    expect(await screen.findByText("Range-bound")).toBeTruthy();
  });
});
