import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DriftCard } from "../DriftCard";
import { driftApi } from "@/api/drift";

vi.mock("@/api/drift");

const mocked = vi.mocked(driftApi, true);

beforeEach(() => {
  vi.resetAllMocks();
});

describe("DriftCard", () => {
  it("renders the no-drift state", async () => {
    mocked.status.mockResolvedValue({
      status: "no_recent_drift", strategy_id: 1, lookback_days: 7,
    });
    render(<DriftCard strategyId={1} />);
    expect(await screen.findByText(/No drift detected/i)).toBeInTheDocument();
  });

  it("renders drift status with breach detail", async () => {
    mocked.status.mockResolvedValue({
      status: "drift_detected", strategy_id: 1, lookback_days: 7,
      detected_at: "2026-06-03T00:00:00Z",
      payload: {
        strategy_id: 1, breached: ["win_rate"],
        win_rate: { live: 0.42, baseline: 0.6, delta_pp: -18.0 },
        avg_return_per_trade: { live: 0, baseline: 0, delta_pct: 0 },
        trade_count: 25, detected_at: "2026-06-03T00:00:00Z",
      },
    });
    render(<DriftCard strategyId={1} />);
    expect(await screen.findByText(/Drift detected/i)).toBeInTheDocument();
    expect(screen.getByText(/live trades over the window/i)).toBeInTheDocument();
  });

  it("'Re-check now' calls the check API and refreshes", async () => {
    mocked.status.mockResolvedValue({
      status: "no_recent_drift", strategy_id: 1, lookback_days: 7,
    });
    mocked.check.mockResolvedValue({ kind: "within_thresholds", strategy_id: 1 });
    render(<DriftCard strategyId={1} />);
    fireEvent.click(await screen.findByRole("button", { name: /re-check now/i }));
    await waitFor(() => expect(mocked.check).toHaveBeenCalledWith(1));
  });
});
