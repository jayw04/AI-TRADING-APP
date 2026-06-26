/**
 * P8 §5a — Range Candidates panel. Mocks the api; covers ranked render + the "Use"
 * (applyRange) flow + onApplied callback.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import RangeCandidatesPanel from "../RangeCandidatesPanel";
import { rangeInsightApi, type RangeCandidate } from "@/api/rangeInsight";
import { strategyTemplatesApi } from "@/api/strategyTemplates";

vi.mock("@/api/rangeInsight", () => ({
  rangeInsightApi: { candidates: vi.fn() },
}));
vi.mock("@/api/strategyTemplates", () => ({
  strategyTemplatesApi: { applyRange: vi.fn() },
}));
const mocked = vi.mocked(rangeInsightApi, true);
const mockedTmpl = vi.mocked(strategyTemplatesApi, true);

function cand(over: Partial<RangeCandidate>): RangeCandidate {
  return {
    symbol: "X", status: "ok", atr20: 5, atr20_pct: 0.04, intraday_range: 4,
    classification: "range_bound", last_close: 100, efficiency_ratio: 0.1, oscillation: 0.9,
    suitable: true, score: 0.04, rank: 1,
    win_rate: null, sharpe: null, n_trades: null, backtested: false,
    ...over,
  };
}

const RANKED: RangeCandidate[] = [
  // AAPL is backtested (62% win rate) → server ranks it first, ahead of structurally-good AMD.
  cand({
    symbol: "AAPL", atr20_pct: 0.03, classification: "range_bound", rank: 1, suitable: true,
    win_rate: 0.62, sharpe: 0.46, n_trades: 24, backtested: true,
  }),
  cand({ symbol: "AMD", atr20_pct: 0.066, classification: "range_bound", rank: 2, suitable: true }),
  cand({ symbol: "NVDA", atr20_pct: 0.04, classification: "range_bound", rank: 3, suitable: true }),
  cand({ symbol: "TSLA", atr20_pct: 0.046, classification: "trending", rank: 4, suitable: false }),
];

beforeEach(() => {
  vi.clearAllMocks();
  mocked.candidates.mockResolvedValue({ as_of: "2026-06-26T00:00:00Z", candidates: RANKED });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(window, "alert").mockImplementation(() => {});
});

describe("RangeCandidatesPanel", () => {
  it("renders candidates in ranked order with ATR% and behavior", async () => {
    render(<RangeCandidatesPanel />);
    await waitFor(() => expect(screen.getByText("AMD")).toBeInTheDocument());
    expect(screen.getByText("6.6%")).toBeInTheDocument();
    expect(screen.getByText("Trending")).toBeInTheDocument();
    // first data row is the top-ranked AAPL (backtested, ranks above structural AMD)
    const rows = screen.getAllByRole("row");
    expect(rows[1]).toHaveTextContent("AAPL");
  });

  it("surfaces realized backtest evidence (win rate + Sharpe + BT badge) on the top row", async () => {
    render(<RangeCandidatesPanel />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());
    const rows = screen.getAllByRole("row");
    expect(rows[1]).toHaveTextContent("AAPL");
    expect(rows[1]).toHaveTextContent("62.0%"); // realized win rate
    expect(rows[1]).toHaveTextContent("0.46"); // realized Sharpe
    expect(rows[1]).toHaveTextContent("BT"); // backtested badge
  });

  it("applies the range template on Use and fires onApplied", async () => {
    mockedTmpl.applyRange.mockResolvedValue({ strategy_id: 9 } as never);
    const onApplied = vi.fn();
    render(<RangeCandidatesPanel onApplied={onApplied} />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());
    const useButtons = screen.getAllByRole("button", { name: /use/i });
    fireEvent.click(useButtons[0]); // top row = AAPL
    await waitFor(() => expect(mockedTmpl.applyRange).toHaveBeenCalledWith("AAPL"));
    expect(onApplied).toHaveBeenCalledWith("AAPL");
  });

  it("shows an error when the fetch fails", async () => {
    mocked.candidates.mockRejectedValue(new Error("boom"));
    render(<RangeCandidatesPanel />);
    await waitFor(() => expect(screen.getByText(/boom/)).toBeInTheDocument());
  });
});
