import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient } from "@tanstack/react-query";
import App from "@/App";
import { MARKETS, parseMarketId } from "@/markets/registry";
import { formatInstant, formatMoney } from "@/markets/format";
import { marketQueryKey } from "@/api/markets";

const HEAD = {
  market: "cn_ashare",
  label: "中国 A股",
  currency: "CNY",
  currency_label: "RMB",
  timezone: "Asia/Shanghai",
  research_only: true,
  scope: "SSE and SZSE main-board A-shares (CNY); daily bars only",
};

const DATA_STATUS = {
  ...HEAD,
  store: "PRESENT",
  providers: [
    {
      source_id: "baostock",
      name: "Baostock",
      access: "FREE_NO_ACCOUNT",
      storage: "UNKNOWN",
      presentation: "UNKNOWN",
      basis: "x",
      credential: "NOT_REQUIRED",
      last_update_utc: "2026-10-13T02:35:00Z",
      datasets: [
        { provider: "baostock", dataset: "daily", sample_label: "PLUMBING_SAMPLE_NOT_SURVIVORSHIP_SAFE", ingests: 20, rows: 4834, last_fetch_utc: "2026-10-13T02:35:00Z", symbols: 20, first_date: "2024-01-02", last_date: "2024-12-31" },
      ],
    },
  ],
  calendar: [{ provider: "baostock", exchange: "SSE", open_days: 242, first_day: "2024-01-01", last_day: "2024-12-31", last_open_day: "2024-12-31" }],
  crosscheck: null,
  issues: [{ severity: "BLOCKER", kind: "CROSSCHECK_PRICE_MISMATCH", detail: "3 unexplained PRICE_MISMATCH" }],
};

const RESULTS = {
  ...HEAD,
  store: "PRESENT",
  runs: [
    {
      run_id: "cnrun-1",
      created_at_utc: "2026-10-13T02:35:00Z",
      candidate_id: "CN-MOM-20D",
      sample_label: "SYNTHETIC_FIXTURE_NOT_MARKET_DATA",
      labels: ["NON_INFERENTIAL_DESCRIPTIVE", "SYNTHETIC_FIXTURE_NOT_MARKET_DATA"],
      market_context: { market: "CN_ASHARE", provider: "cn_synthetic:baostock_shape", price_basis: "HFQ" },
      period: { start: "2024-01-02", end: "2024-12-31" },
      universe: { symbols_with_data: 20, eligible: 19, excluded: {} },
      capital_cny: 1_000_000,
      commission_assumption: { rate: 0.00025, minimum_cny: 5 },
      result: {
        end_equity_cny: 1_050_000,
        net_return: 0.05,
        gross_return_before_fees: 0.056,
        fees_cny: 6000,
        cost_drag: 0.006,
        costs_cny: { commission: 2000, stamp_duty: 3000, transfer_fee: 200, handling_fee: 300, regulatory_fee: 500, total: 6000 },
        risk: { max_drawdown: -0.1, volatility_annualized: 0.2, worst_day: -0.03, best_day: 0.04, trading_days: 242 },
        turnover: 4.2,
        max_drawdown: -0.1,
        fills: 60,
        refusals: { LIMIT_UP_NO_BUY: 1 },
        unexecutable_delisting_exits: {},
      },
      limitations: { not_modelled: ["intraday sequence"], accounting: ["dividend tax not modelled"], rules: [] },
    },
  ],
};

const STRATEGIES = {
  ...HEAD,
  candidates: [
    { candidate_id: "CN-MOM-20D", name: "20-day momentum, monthly", hypothesis: "h", signal: "s", lookback_days: 20, direction: "high", top_k: 5, rebalance: "monthly", status: "CANDIDATE", run_count: 0, last_run: null },
  ],
};

let calls: string[] = [];
let cnOverride: Record<string, unknown> = {};

beforeEach(() => {
  calls = [];
  cnOverride = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      calls.push(url);
      const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200 }));
      for (const [view, body] of Object.entries({ "data-status": DATA_STATUS, strategies: STRATEGIES, results: RESULTS })) {
        if (url === `/api/v1/markets/cn_ashare/${view}`) return json(cnOverride[view] ?? body);
      }
      if (url.includes("/api/v1/account")) return json({ mode: "paper", status: "ACTIVE" });
      return new Promise(() => {});
    }),
  );
  class FakeWebSocket {
    readyState = 0;
    addEventListener() {}
    removeEventListener() {}
    close() {}
    send() {}
  }
  vi.stubGlobal("WebSocket", FakeWebSocket);
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

function Where() {
  const l = useLocation();
  return <div data-testid="where">{`${l.pathname}${l.search}`}</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App makeQueryClient={() => new QueryClient({ defaultOptions: { queries: { retry: false } } })} />
      <Where />
    </MemoryRouter>,
  );
}

const where = () => screen.getByTestId("where").textContent;
const usCalls = () => calls.filter((u) => !u.startsWith("/api/v1/markets/"));

describe("market registry and formatting", () => {
  it("matches market ids exactly", () => {
    expect(parseMarketId("cn")).toBe("cn");
    for (const bad of ["", "CN", "cn_ashare", "jp", undefined, null]) expect(parseMarketId(bad)).toBeNull();
  });

  it("formats RMB and Asia/Shanghai for A-shares", () => {
    expect(formatMoney(1234567, MARKETS.cn)).toContain("¥");
    expect(formatMoney(1234567, MARKETS.us)).toContain("$");
    expect(formatInstant("2026-10-13T02:35:00Z", MARKETS.cn)).toBe("2026-10-13 10:35 Asia/Shanghai");
    expect(formatInstant("2026-10-13T02:35:00Z", MARKETS.us)).toBe("2026-10-12 22:35 America/New_York");
  });

  it("puts the market in every scoped cache key", () => {
    expect(marketQueryKey(MARKETS.cn, "results")).toEqual(["market", "cn_ashare", "results"]);
  });
});

describe("routes", () => {
  it("loads US pages by direct link", async () => {
    renderAt("/us/orders");
    expect(await screen.findByRole("heading", { name: "Orders" })).toBeInTheDocument();
    expect(screen.getByLabelText("Market")).toHaveValue("us");
    expect(screen.getByLabelText("Market currency and time")).toHaveTextContent("USD · America/New_York");
  });

  it.each([
    ["/orders", "/us/orders"],
    ["/strategies/42", "/us/strategies/42"],
    ["/charts?symbol=AAPL", "/us/charts?symbol=AAPL"],
    ["/settings/risk-limits", "/us/settings/risk-limits"],
  ])("redirects legacy US link %s to %s", async (from, to) => {
    renderAt(from);
    await waitFor(() => expect(where()).toBe(to));
  });

  it("loads A-share pages by direct link without touching US endpoints", async () => {
    renderAt("/cn/results");
    expect(await screen.findByText("CN-MOM-20D")).toBeInTheDocument();
    expect(screen.getByLabelText("Market")).toHaveValue("cn");
    expect(screen.getByLabelText("Market currency and time")).toHaveTextContent("RMB · Asia/Shanghai");
    expect(screen.getByLabelText("Research mode")).toHaveTextContent("RESEARCH ONLY");
    expect(screen.getByText("¥1,050,000")).toBeInTheDocument();
    expect(screen.getByText("Stamp duty")).toBeInTheDocument();
    expect(screen.getByText(/LIMIT_UP_NO_BUY 1/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Trading mode")).not.toBeInTheDocument();
    expect(usCalls()).toEqual([]);
  });

  it("sends /cn to the data status page", async () => {
    renderAt("/cn");
    await waitFor(() => expect(where()).toBe("/cn/data"));
    expect(await screen.findByText("CROSSCHECK_PRICE_MISMATCH")).toBeInTheDocument();
    expect(screen.getByText("PLUMBING_SAMPLE_NOT_SURVIVORSHIP_SAFE")).toBeInTheDocument();
    expect(screen.getByText(/2026-10-13 10:35 Asia\/Shanghai/)).toBeInTheDocument();
    expect(screen.getByText(/242 open days/)).toBeInTheDocument();
  });

  it("has no order or broker pages under the A-share market", async () => {
    renderAt("/cn/orders");
    expect(await screen.findByText(/No 中国 A股 page at/)).toBeInTheDocument();
    for (const name of ["Orders", "Positions", "Settings"]) {
      expect(screen.queryByRole("link", { name })).not.toBeInTheDocument();
    }
    expect(calls).toEqual([]);
  });

  it.each(["/jp/data", "/US/orders", "/cn_ashare/results", "/unknown"])(
    "refuses unsupported market %s without loading data",
    async (path) => {
      renderAt(path);
      expect(await screen.findByRole("heading", { name: "Unsupported market" })).toBeInTheDocument();
      expect(calls).toEqual([]);
    },
  );

  it("reports a missing page inside a market", async () => {
    renderAt("/us/nope");
    expect(await screen.findByText(/No US Equities page at/)).toBeInTheDocument();
  });
});

describe("market isolation", () => {
  it("switching markets never shows the other market's data", async () => {
    renderAt("/cn/results");
    expect(await screen.findByText("CN-MOM-20D")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Market"), { target: { value: "us" } });
    await waitFor(() => expect(where()).toBe("/us"));
    expect(screen.queryByText("CN-MOM-20D")).not.toBeInTheDocument();
    expect(screen.queryByText(/RESEARCH ONLY/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Orders" })).toBeInTheDocument();

    const cnCallsBefore = calls.filter((u) => u.startsWith("/api/v1/markets/")).length;
    fireEvent.change(screen.getByLabelText("Market"), { target: { value: "cn" } });
    await waitFor(() => expect(where()).toBe("/cn/data"));
    expect(screen.queryByRole("link", { name: "Orders" })).not.toBeInTheDocument();
    expect(await screen.findByText("CROSSCHECK_PRICE_MISMATCH")).toBeInTheDocument();
    // Only A-share endpoints are requested on A-share pages.
    expect(calls.filter((u) => u.startsWith("/api/v1/markets/")).slice(cnCallsBefore)).toEqual([
      "/api/v1/markets/cn_ashare/data-status",
    ]);
  });

  it("rejects a response labelled with another market", async () => {
    cnOverride = { results: { ...RESULTS, market: "us_equity", currency: "USD" } };
    renderAt("/cn/results");
    expect(await screen.findByRole("alert")).toHaveTextContent("Expected cn_ashare data, received us_equity");
    expect(screen.queryByText("CN-MOM-20D")).not.toBeInTheDocument();
  });

  it("shows strategy candidates with their status and no activation control", async () => {
    renderAt("/cn/strategies");
    expect(await screen.findByText("CANDIDATE")).toBeInTheDocument();
    expect(screen.getByText("Not run yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /activate|order|buy|sell/i })).not.toBeInTheDocument();
  });
});
