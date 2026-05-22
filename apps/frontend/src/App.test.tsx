import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { NAV_ITEMS } from "./routes";

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
  daytrade_count: 0,
  pattern_day_trader: false,
  trading_blocked: false,
  account_blocked: false,
  updated_at: new Date().toISOString(),
};

beforeEach(() => {
  // Resolve account fetches with a paper account so ModeBanner renders its
  // amber state; resolve every other GET with a minimal payload so the
  // dashboard / pages don't blow up.
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (typeof url === "string" && url.includes("/api/v1/account")) {
        return Promise.resolve(
          new Response(JSON.stringify(PAPER_ACCOUNT), { status: 200 }),
        );
      }
      return new Promise(() => {}); // hang every other request
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

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App shell", () => {
  it("renders every sidebar nav item", () => {
    renderApp();
    for (const item of NAV_ITEMS) {
      expect(
        screen.getByRole("link", { name: item.label }),
        `expected nav link "${item.label}"`,
      ).toBeInTheDocument();
    }
  });

  it("renders the mode banner with the paper-mode copy once account loads", async () => {
    renderApp();
    await waitFor(() => {
      expect(screen.getByLabelText("Trading mode")).toHaveTextContent(/paper/i);
    });
  });
});
