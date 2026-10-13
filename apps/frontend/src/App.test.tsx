import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient } from "@tanstack/react-query";
import App from "./App";
import { US_NAV_ITEMS } from "./routes";

const PAPER_ACCOUNT = {
  account_id: 1,
  mode: "paper",
  status: "ACTIVE",
  cash: "10000",
  equity: "10000",
  last_equity: "10000",
  buying_power: "20000",
  portfolio_value: "10000",
  day_change: "0",
  day_change_pct: "0",
  day_change_basis: "BROKER_LAST_EQUITY",
  daytrade_count: 0,
  pattern_day_trader: false,
  trading_blocked: false,
  account_blocked: false,
  updated_at: new Date().toISOString(),
};

beforeEach(() => {
  // Resolve account fetches with a paper account so ModeBanner renders its
  // amber state; hang every other request so the pages don't blow up.
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (typeof url === "string" && url.includes("/api/v1/account")) {
        return Promise.resolve(new Response(JSON.stringify(PAPER_ACCOUNT), { status: 200 }));
      }
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
});

function Where() {
  const l = useLocation();
  return <div data-testid="where">{`${l.pathname}${l.search}`}</div>;
}

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App makeQueryClient={() => new QueryClient({ defaultOptions: { queries: { retry: false } } })} />
      <Where />
    </MemoryRouter>,
  );
}

describe("App shell", () => {
  it("sends / to the US subsystem and renders every US nav item", async () => {
    renderApp("/");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(/^\/us$/));
    for (const item of US_NAV_ITEMS) {
      expect(screen.getByRole("link", { name: item.label }), `expected nav link "${item.label}"`).toBeInTheDocument();
    }
  });

  it("renders the mode banner with the paper-mode copy once account loads", async () => {
    renderApp("/us");
    await waitFor(() => {
      expect(screen.getByLabelText("Trading mode")).toHaveTextContent(/paper/i);
    });
  });
});
