import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import StrategyDetailPage from "../Detail";
import { strategiesApi } from "@/api/strategies";
import { signalsApi } from "@/api/signals";
import { ordersApi } from "@/api/orders";
import type { Strategy } from "@/api/types";

vi.mock("@/api/strategies");
vi.mock("@/api/signals");
vi.mock("@/api/orders");
vi.mock("@/hooks/useWorkbenchSocket", () => ({
  useWorkbenchSocket: () => {},
}));

const mockedStrategiesApi = vi.mocked(strategiesApi);
const mockedSignalsApi = vi.mocked(signalsApi);
const mockedOrdersApi = vi.mocked(ordersApi);

const baseStrategy = (over: Partial<Strategy> = {}): Strategy => ({
  id: 1,
  name: "rsi-test",
  version: "0.1.0",
  type: "python",
  status: "idle",
  code_path: "examples/rsi_meanreversion.py",
  params: { entry_threshold: 30 },
  symbols: ["AAPL"],
  schedule: "*/1 * * * *",
  risk_limits_id: null,
  error_text: null,
  has_pending_reload: false,
  pending_reload_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...over,
});

beforeEach(() => {
  vi.resetAllMocks();
  mockedStrategiesApi.get.mockResolvedValue(baseStrategy());
  mockedStrategiesApi.listRuns.mockResolvedValue({ items: [], count: 0 });
  mockedStrategiesApi.listSignals.mockResolvedValue({ items: [], count: 0 });
  mockedStrategiesApi.listBacktests.mockResolvedValue({ items: [], count: 0 });
  // P5 §6: the CooldownIndicator on the detail page polls cooldown status.
  mockedStrategiesApi.cooldownStatus.mockResolvedValue({
    strategy_id: 1,
    in_cooldown: false,
    cooldown_until: null,
    seconds_remaining: 0,
  });
  mockedSignalsApi.list.mockResolvedValue({ items: [], count: 0 });
  mockedOrdersApi.list.mockResolvedValue({ items: [], count: 0 });
});

function renderWithRoute() {
  return render(
    <MemoryRouter initialEntries={["/strategies/1"]}>
      <Routes>
        <Route path="/strategies/:id" element={<StrategyDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("StrategyDetailPage", () => {
  it("renders header with name and status", async () => {
    renderWithRoute();
    expect(await screen.findByText("rsi-test")).toBeInTheDocument();
    expect(await screen.findByText("IDLE")).toBeInTheDocument();
  });

  it("switches between tabs", async () => {
    renderWithRoute();
    await screen.findByText("rsi-test");
    expect(await screen.findByText(/Latest run/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Signals" }));
    expect(await screen.findByText(/Filter:/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Backtests" }));
    expect(await screen.findByText(/Run backtest/)).toBeInTheDocument();
  });

  it("Params tab is read-only when status is paper", async () => {
    mockedStrategiesApi.get.mockResolvedValue(
      baseStrategy({ status: "paper", params: { x: 1 } }),
    );
    renderWithRoute();
    await screen.findByText("rsi-test");
    fireEvent.click(screen.getByRole("button", { name: "Params" }));
    const banner = await screen.findByText(/stop it before editing/i);
    expect(banner).toBeInTheDocument();
  });
});

// ---------- P4 §4: reload banner ----------

describe("StrategyDetailPage — reload banner (P4 §4)", () => {
  it("hides the banner when has_pending_reload is false", async () => {
    mockedStrategiesApi.get.mockResolvedValue(baseStrategy());
    renderWithRoute();
    await screen.findByText("rsi-test");
    expect(screen.queryByTestId("pending-reload-banner")).not.toBeInTheDocument();
  });

  it("shows the banner when has_pending_reload is true + Reload button calls the API", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockedStrategiesApi.get.mockResolvedValueOnce(
      baseStrategy({
        has_pending_reload: true,
        pending_reload_at: "2026-05-26T20:00:00Z",
      }),
    );
    mockedStrategiesApi.reload.mockResolvedValue({
      strategy_id: 1,
      action: "reload",
      new_status: "idle",
      run_id: null,
    });
    // After reload, the next get() returns the cleared state.
    mockedStrategiesApi.get.mockResolvedValue(baseStrategy());

    renderWithRoute();
    const banner = await screen.findByTestId("pending-reload-banner");
    expect(banner).toBeInTheDocument();
    expect(banner.textContent).toMatch(/strategy file has changed/i);

    fireEvent.click(screen.getByRole("button", { name: /^Reload$/ }));

    await waitFor(() =>
      expect(mockedStrategiesApi.reload).toHaveBeenCalledWith(1),
    );
  });
});
