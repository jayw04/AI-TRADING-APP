/**
 * Orders "Today" view — flattens the day's fills into a buy/sell history with prices.
 * Covers the pure todaysFills() filter/sort and the rendered table + summary.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import OrdersPage, { todaysFills } from "../index";
import { ordersApi } from "@/api/orders";
import type { Order } from "@/api/types";

vi.mock("@/api/orders", () => ({ ordersApi: { list: vi.fn() } }));
const mocked = vi.mocked(ordersApi, true);

const nowIso = new Date().toISOString();
const earlierTodayIso = new Date(Date.now() - 60_000).toISOString(); // 1 min ago (still today)
const yesterdayIso = new Date(Date.now() - 36 * 3_600_000).toISOString();

function orders(): Order[] {
  return [
    {
      id: 1, symbol: "AAPL", side: "buy", source_type: "strategy", created_at: earlierTodayIso,
      fills: [
        { id: 10, qty: "5", price: "100", filled_at: earlierTodayIso },
        { id: 11, qty: "3", price: "101", filled_at: yesterdayIso }, // not today → excluded
      ],
    },
    {
      id: 2, symbol: "MSFT", side: "sell", source_type: "manual", created_at: nowIso,
      fills: [{ id: 20, qty: "2", price: "200", filled_at: nowIso }],
    },
  ] as unknown as Order[];
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OrdersPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.list.mockResolvedValue({ items: orders(), count: 2 } as never);
});

describe("todaysFills", () => {
  it("keeps only today's fills, flattened and newest-first", () => {
    const rows = todaysFills(orders());
    expect(rows.map((r) => r.symbol)).toEqual(["MSFT", "AAPL"]); // MSFT (now) before AAPL (1 min ago)
    expect(rows.map((r) => r.price)).toEqual(["200", "100"]); // yesterday's 101 excluded
    expect(rows.map((r) => r.side)).toEqual(["sell", "buy"]);
  });

  it("returns nothing when there are no fills today", () => {
    const stale = [
      { id: 9, symbol: "X", side: "buy", source_type: "manual", created_at: yesterdayIso,
        fills: [{ id: 90, qty: "1", price: "10", filled_at: yesterdayIso }] },
    ] as unknown as Order[];
    expect(todaysFills(stale)).toEqual([]);
  });
});

describe("Orders Today view", () => {
  it("defaults to Today and shows the day's fills with prices + a summary", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());
    expect(mocked.list).toHaveBeenCalledWith({ filter: "all", limit: 500 });
    // both executed trades rendered with their actual fill prices
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("$200.00")).toBeInTheDocument(); // MSFT fill price
    expect(screen.getByText("$100.00")).toBeInTheDocument(); // AAPL fill price
    // newest-first ordering: MSFT row precedes AAPL row
    const rows = screen.getAllByRole("row");
    const msft = rows.findIndex((r) => r.textContent?.includes("MSFT"));
    const aapl = rows.findIndex((r) => r.textContent?.includes("AAPL"));
    expect(msft).toBeLessThan(aapl);
    // summary counts both
    expect(screen.getByText("Trades today")).toBeInTheDocument();
  });

  it("shows an empty state when no fills today", async () => {
    mocked.list.mockResolvedValue({ items: [], count: 0 } as never);
    renderPage();
    await waitFor(() => expect(screen.getByText(/No fills yet today/i)).toBeInTheDocument());
  });
});
