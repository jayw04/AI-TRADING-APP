/**
 * OrderTicket — three highest-value flows: happy path, risk rejection,
 * live-mode confirmation. We mock the three API modules and drive the
 * component through React-Testing-Library; no MSW because we don't care
 * about transport here.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import OrderTicket from "../OrderTicket";
import { ordersApi } from "@/api/orders";
import { quotesApi } from "@/api/quotes";
import { accountApi } from "@/api/account";

vi.mock("@/api/orders");
vi.mock("@/api/quotes");
vi.mock("@/api/account");

const mockedOrdersApi = vi.mocked(ordersApi, true);
const mockedQuotesApi = vi.mocked(quotesApi, true);
const mockedAccountApi = vi.mocked(accountApi, true);

function paperAccount(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    account_id: 1,
    mode: "paper",
    status: "ACTIVE",
    cash: "100000",
    equity: "100000",
    last_equity: "100000",
    buying_power: "100000",
    portfolio_value: "100000",
    day_change: "0",
    day_change_pct: "0",
    daytrade_count: 0,
    pattern_day_trader: false,
    trading_blocked: false,
    account_blocked: false,
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

function quoteFor(symbol: string) {
  return {
    symbol,
    bid: "190.50",
    ask: "190.52",
    last: "190.51",
    bid_size: 100,
    ask_size: 100,
    ts: new Date().toISOString(),
    source: "alpaca-iex",
  };
}

function renderTicket() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <OrderTicket />
    </QueryClientProvider>,
  );
}

describe("OrderTicket", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedQuotesApi.get.mockImplementation((symbol: string) =>
      Promise.resolve(quoteFor(symbol)),
    );
    mockedAccountApi.get.mockResolvedValue(paperAccount() as never);
  });

  it("submits a paper order and renders the success banner", async () => {
    mockedOrdersApi.create.mockResolvedValue({
      id: 42,
      broker_order_id: "alp-42",
      client_order_id: "twb-42",
      symbol: "AAPL",
      side: "buy",
      qty: "1",
      type: "market",
      limit_price: null,
      stop_price: null,
      tif: "day",
      extended_hours: false,
      status: "submitted",
      rejection_reason: null,
      source_type: "manual",
      source_id: null,
      created_at: new Date().toISOString(),
      submitted_at: new Date().toISOString(),
      terminal_at: null,
      updated_at: new Date().toISOString(),
      fills: [],
      risk_check: null,
    });

    renderTicket();

    // Wait for the paper-mode pill to appear (proves accountApi resolved).
    await screen.findAllByText(/paper/i);

    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "AAPL" } });

    const submit = screen.getByRole("button", { name: /buy aapl/i });
    fireEvent.click(submit);

    await waitFor(() => {
      expect(mockedOrdersApi.create).toHaveBeenCalledTimes(1);
    });
    expect(mockedOrdersApi.create).toHaveBeenCalledWith(
      expect.objectContaining({ symbol: "AAPL", side: "buy", qty: "1", type: "market" }),
    );
    expect(await screen.findByText(/^Submitted$/i)).toBeInTheDocument();
  });

  it("renders the risk-rejection banner with plain-English reasons", async () => {
    mockedOrdersApi.create.mockResolvedValue({
      id: 43,
      broker_order_id: null,
      client_order_id: "twb-43",
      symbol: "AAPL",
      side: "buy",
      qty: "99999",
      type: "market",
      limit_price: null,
      stop_price: null,
      tif: "day",
      extended_hours: false,
      status: "rejected",
      rejection_reason: "POSITION_CAP_QTY,POSITION_CAP_NOTIONAL",
      source_type: "manual",
      source_id: null,
      created_at: new Date().toISOString(),
      submitted_at: null,
      terminal_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      fills: [],
      risk_check: {
        id: 99,
        decision: "reject",
        reason_codes: ["POSITION_CAP_QTY", "POSITION_CAP_NOTIONAL"],
        evaluated_at: new Date().toISOString(),
      },
    });

    renderTicket();
    await screen.findAllByText(/paper/i);

    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "AAPL" } });
    fireEvent.change(screen.getByLabelText("Qty"), { target: { value: "99999" } });
    fireEvent.click(screen.getByRole("button", { name: /buy aapl/i }));

    expect(await screen.findByText(/rejected by risk engine/i)).toBeInTheDocument();
    // Plain-English copy from RISK_REASON_DESCRIPTIONS:
    const alert = await screen.findByRole("alert");
    expect(alert.textContent ?? "").toMatch(/per-symbol share limit/i);
    expect(alert.textContent ?? "").toMatch(/per-symbol dollar limit/i);
  });

  it("in live mode, submit opens the confirm modal and does not call orders.create", async () => {
    mockedAccountApi.get.mockResolvedValue(paperAccount({ mode: "live" }) as never);
    mockedOrdersApi.create.mockResolvedValue({} as never); // should never be called

    renderTicket();

    // Wait for live pill so we know the mode query resolved.
    await screen.findAllByText(/^Live$/i);

    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByRole("button", { name: /\[live\] buy aapl/i }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/confirm live order/i)).toBeInTheDocument();
    expect(mockedOrdersApi.create).not.toHaveBeenCalled();
  });
});
