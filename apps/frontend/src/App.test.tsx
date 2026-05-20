import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { NAV_ITEMS } from "./routes";

// Skip the API/WS network in the unit test: we're verifying the shell.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {}))); // never resolves
  // jsdom doesn't supply WebSocket; provide a noop ctor so StatusBar's useEffect doesn't throw.
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

  it("shows the PAPER mode banner in the header", () => {
    renderApp();
    expect(screen.getByLabelText("Trading mode")).toHaveTextContent(/paper/i);
  });
});
