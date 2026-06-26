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
    ...over,
  };
}

const RANKED: RangeCandidate[] = [
  cand({ symbol: "AMD", atr20_pct: 0.066, classification: "range_bound", rank: 1, suitable: true }),
  cand({ symbol: "NVDA", atr20_pct: 0.04, classification: "range_bound", rank: 2, suitable: true }),
  cand({ symbol: "TSLA", atr20_pct: 0.046, classification: "trending", rank: 3, suitable: false }),
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
    // first data row is the top-ranked AMD
    const rows = screen.getAllByRole("row");
    expect(rows[1]).toHaveTextContent("AMD");
  });

  it("applies the range template on Use and fires onApplied", async () => {
    mockedTmpl.applyRange.mockResolvedValue({ strategy_id: 9 } as never);
    const onApplied = vi.fn();
    render(<RangeCandidatesPanel onApplied={onApplied} />);
    await waitFor(() => expect(screen.getByText("AMD")).toBeInTheDocument());
    const useButtons = screen.getAllByRole("button", { name: /use/i });
    fireEvent.click(useButtons[0]); // AMD
    await waitFor(() => expect(mockedTmpl.applyRange).toHaveBeenCalledWith("AMD"));
    expect(onApplied).toHaveBeenCalledWith("AMD");
  });

  it("shows an error when the fetch fails", async () => {
    mocked.candidates.mockRejectedValue(new Error("boom"));
    render(<RangeCandidatesPanel />);
    await waitFor(() => expect(screen.getByText(/boom/)).toBeInTheDocument());
  });
});
