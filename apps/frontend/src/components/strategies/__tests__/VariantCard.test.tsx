import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { VariantCard } from "../VariantCard";
import { variantsApi, type VariantComparison } from "@/api/variants";
import { proposalsApi } from "@/api/proposals";
import type { Strategy } from "@/api/types";

vi.mock("@/api/variants");
vi.mock("@/api/proposals");

const mockedVariants = vi.mocked(variantsApi, true);
const mockedProposals = vi.mocked(proposalsApi, true);

function strategy(status: Strategy["status"] = "live"): Strategy {
  return {
    id: 1,
    name: "S1",
    version: "0.1.0",
    type: "python",
    status,
    code_path: "s.py",
    params: {},
    symbols: ["AAPL"],
    schedule: "* * * * *",
    risk_limits_id: null,
    error_text: null,
    has_pending_reload: false,
    pending_reload_at: null,
    created_at: "2026-06-10T00:00:00Z",
    updated_at: "2026-06-10T00:00:00Z",
  } as Strategy;
}

function comparison(): VariantComparison {
  const side = {
    trade_count: 3,
    win_rate: 0.5,
    avg_return_per_trade: 0.01,
    sharpe_ratio: 1.2,
    max_drawdown: -0.05,
  };
  return {
    parent_strategy_id: 1,
    variant_strategy_id: 2,
    spawn_proposal_id: 7,
    window_start: "2026-06-12T00:00:00Z",
    window_end: "2026-06-15T00:00:00Z",
    live_metrics: side,
    variant_metrics: { ...side, win_rate: 0.6, sharpe_ratio: 1.5 },
    deltas: {
      sharpe_delta_pct: 25,
      max_drawdown_delta_pct: 0,
      win_rate_delta_pp: 10,
      avg_return_delta_pct: 5,
    },
    live_trade_count: 3,
    variant_trade_count: 3,
    live_equity_curve: [
      { ts: "2026-06-12T20:00:00Z", equity: 100000 },
      { ts: "2026-06-13T20:00:00Z", equity: 100500 },
    ],
    variant_equity_curve: [
      { ts: "2026-06-12T20:00:00Z", equity: 100000 },
      { ts: "2026-06-13T20:00:00Z", equity: 101000 },
    ],
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  mockedProposals.list.mockResolvedValue({ items: [] });
});

describe("VariantCard", () => {
  it("renders the empty state when no variant and no eligible proposal", async () => {
    mockedVariants.comparison.mockResolvedValue({
      status: "no_active_variant",
      strategy_id: 1,
    });
    render(<VariantCard strategy={strategy()} />);
    expect(
      await screen.findByText(/No active validation/i),
    ).toBeInTheDocument();
  });

  it("renders the Validate button when an ACCEPTED proposal exists on a live parent", async () => {
    mockedVariants.comparison.mockResolvedValue({
      status: "no_active_variant",
      strategy_id: 1,
    });
    mockedProposals.list.mockResolvedValue({
      items: [
        {
          id: 9,
          strategy_id: 1,
          user_id: 1,
          state: "ACCEPTED",
          proposal_payload: { summary: "Lower RSI to 40" },
          evidence_bundle: {},
          evaluation_results: {} as never,
          generated_at: "2026-06-14T00:00:00Z",
          transitioned_at: "2026-06-14T00:00:00Z",
        },
      ],
    });
    render(<VariantCard strategy={strategy("live")} />);
    expect(
      await screen.findByText(/Validate this proposal/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Lower RSI to 40/)).toBeInTheDocument();
  });

  it("renders the active state with metrics + Stop button", async () => {
    mockedVariants.comparison.mockResolvedValue({
      status: "variant_active",
      strategy_id: 1,
      variant_strategy_id: 2,
      comparison: comparison(),
    });
    render(<VariantCard strategy={strategy()} />);
    expect(await screen.findByText("Validating")).toBeInTheDocument();
    expect(screen.getByText(/Stop validation/i)).toBeInTheDocument();
    expect(screen.getByText("Sharpe")).toBeInTheDocument();
    expect(screen.getByText("Win rate")).toBeInTheDocument();
  });

  it("clicking Validate calls the API and refreshes", async () => {
    mockedVariants.comparison.mockResolvedValue({
      status: "no_active_variant",
      strategy_id: 1,
    });
    mockedProposals.list.mockResolvedValue({
      items: [
        {
          id: 9,
          strategy_id: 1,
          user_id: 1,
          state: "ACCEPTED",
          proposal_payload: { summary: "x" },
          evidence_bundle: {},
          evaluation_results: {} as never,
          generated_at: "2026-06-14T00:00:00Z",
          transitioned_at: "2026-06-14T00:00:00Z",
        },
      ],
    });
    mockedVariants.validate.mockResolvedValue(undefined);
    render(<VariantCard strategy={strategy("live")} />);
    fireEvent.click(await screen.findByText(/Validate this proposal/i));
    await waitFor(() => expect(mockedVariants.validate).toHaveBeenCalledWith(9));
    // refresh re-fetches the comparison (initial + post-action).
    await waitFor(() =>
      expect(mockedVariants.comparison.mock.calls.length).toBeGreaterThanOrEqual(2),
    );
  });

  it("clicking Stop calls stopValidation with the spawn proposal id", async () => {
    mockedVariants.comparison.mockResolvedValue({
      status: "variant_active",
      strategy_id: 1,
      variant_strategy_id: 2,
      comparison: comparison(),
    });
    mockedVariants.stopValidation.mockResolvedValue(undefined);
    render(<VariantCard strategy={strategy()} />);
    fireEvent.click(await screen.findByText(/Stop validation/i));
    await waitFor(() =>
      expect(mockedVariants.stopValidation).toHaveBeenCalledWith(7),
    );
  });
});
