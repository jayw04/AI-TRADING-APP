import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
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
