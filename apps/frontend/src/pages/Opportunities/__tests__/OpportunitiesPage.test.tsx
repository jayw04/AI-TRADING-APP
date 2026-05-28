import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import OpportunitiesPage from "../index";
import { opportunitiesApi } from "@/api/opportunities";
import type {
  OppFillItem,
  OppOpenOrderItem,
  OppRiskRejectItem,
  OppSignalItem,
  OppStrategyErrorItem,
  OpportunitiesResponse,
} from "@/api/types";

vi.mock("@/api/opportunities");
vi.mock("@/hooks/useWorkbenchSocket", () => ({
  useWorkbenchSocket: () => {},
}));

const mocked = vi.mocked(opportunitiesApi);

function emptyResponse(): OpportunitiesResponse {
  const now = new Date().toISOString();
  return {
    live_signals: { items: [], count: 0, as_of: now },
    pine_alerts: { items: [], count: 0, as_of: now },
    strategy_errors: { items: [], count: 0, as_of: now },
    open_orders_expiring: { items: [], count: 0, as_of: now },
    risk_rejections: { items: [], count: 0, as_of: now },
    recent_fills: { items: [], count: 0, as_of: now },
    as_of: now,
  };
}

function liveSignal(over: Partial<OppSignalItem> = {}): OppSignalItem {
  return {
    id: 1,
    strategy_id: 5,
    strategy_name: "rsi-bot",
    symbol: "AAPL",
    type: "entry",
    received_at: new Date().toISOString(),
    reason: "rsi_oversold",
    side: "buy",
    ...over,
  };
}

function strategyError(
  over: Partial<OppStrategyErrorItem> = {},
): OppStrategyErrorItem {
  return {
    id: 7,
    name: "broken",
    version: "0.1.0",
    error_text: "loader failed: import broken_dep",
    error_first_seen: new Date().toISOString(),
    ...over,
  };
}

function openOrder(over: Partial<OppOpenOrderItem> = {}): OppOpenOrderItem {
  return {
    id: 1,
    symbol: "AAPL",
    side: "buy",
    type: "limit",
    tif: "gtc",
    qty: "10",
    limit_price: "190.0",
    status: "submitted",
    created_at: new Date().toISOString(),
    expiry_reason: "GTC age 8 days",
    ...over,
  };
}

function riskReject(over: Partial<OppRiskRejectItem> = {}): OppRiskRejectItem {
  return {
    id: 1,
    order_id: 99,
    symbol: "AAPL",
    decision: "reject",
    reason_codes: ["POSITION_CAP_NOTIONAL", "DAILY_LOSS"],
    evaluated_at: new Date().toISOString(),
    ...over,
  };
}

function fill(over: Partial<OppFillItem> = {}): OppFillItem {
  return {
    id: 1,
    order_id: 1,
    symbol: "AAPL",
    side: "buy",
    qty: "3",
    price: "190.00",
    filled_at: new Date().toISOString(),
    strategy_id: 42,
    strategy_name: "rsi-bot",
    ...over,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("OpportunitiesPage", () => {
  it("renders all six widget titles", async () => {
    mocked.get.mockResolvedValue(emptyResponse());
    render(
      <MemoryRouter>
        <OpportunitiesPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Live signals")).toBeInTheDocument();
      expect(screen.getByText("Pine alerts")).toBeInTheDocument();
      expect(screen.getByText("Strategies in error")).toBeInTheDocument();
      expect(screen.getByText("Orders nearing expiry")).toBeInTheDocument();
      expect(screen.getByText("Risk rejections")).toBeInTheDocument();
      expect(screen.getByText("Recent fills")).toBeInTheDocument();
    });
  });

  it("renders empty states when no items", async () => {
    mocked.get.mockResolvedValue(emptyResponse());
    render(
      <MemoryRouter>
        <OpportunitiesPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText(/No signals in the last 30 minutes/),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/All strategies are healthy/),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/No orders nearing expiry/),
    ).toBeInTheDocument();
  });

  it("renders signal rows with strategy name and reason", async () => {
    const r = emptyResponse();
    r.live_signals = {
      items: [liveSignal()],
      count: 1,
      as_of: new Date().toISOString(),
    };
    mocked.get.mockResolvedValue(r);
    render(
      <MemoryRouter>
        <OpportunitiesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(await screen.findByText(/via rsi-bot/)).toBeInTheDocument();
    expect(await screen.findByText(/— rsi_oversold/)).toBeInTheDocument();
  });

  it("renders strategy errors with error text snippet", async () => {
    const r = emptyResponse();
    r.strategy_errors = {
      items: [strategyError()],
      count: 1,
      as_of: new Date().toISOString(),
    };
    mocked.get.mockResolvedValue(r);
    render(
      <MemoryRouter>
        <OpportunitiesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("broken")).toBeInTheDocument();
    expect(await screen.findByText(/loader failed/)).toBeInTheDocument();
  });

  it("renders order rows with expiry reason", async () => {
    const r = emptyResponse();
    r.open_orders_expiring = {
      items: [openOrder()],
      count: 1,
      as_of: new Date().toISOString(),
    };
    mocked.get.mockResolvedValue(r);
    render(
      <MemoryRouter>
        <OpportunitiesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(await screen.findByText("GTC age 8 days")).toBeInTheDocument();
  });

  it("renders risk rejection rows with reason codes joined", async () => {
    const r = emptyResponse();
    r.risk_rejections = {
      items: [riskReject()],
      count: 1,
      as_of: new Date().toISOString(),
    };
    mocked.get.mockResolvedValue(r);
    render(
      <MemoryRouter>
        <OpportunitiesPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText("POSITION_CAP_NOTIONAL, DAILY_LOSS"),
    ).toBeInTheDocument();
  });

  it("renders fill rows with formatted price and strategy name", async () => {
    const r = emptyResponse();
    r.recent_fills = {
      items: [fill()],
      count: 1,
      as_of: new Date().toISOString(),
    };
    mocked.get.mockResolvedValue(r);
    render(
      <MemoryRouter>
        <OpportunitiesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/×3 @ \$190\.00/)).toBeInTheDocument();
    expect(await screen.findByText(/via rsi-bot/)).toBeInTheDocument();
  });

  it("shows error state on API failure", async () => {
    mocked.get.mockRejectedValue(new Error("backend offline"));
    render(
      <MemoryRouter>
        <OpportunitiesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/backend offline/)).toBeInTheDocument();
  });
});
