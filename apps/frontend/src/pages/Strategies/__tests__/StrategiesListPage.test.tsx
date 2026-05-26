import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import StrategiesListPage from "../index";
import { strategiesApi } from "@/api/strategies";
import { signalsApi } from "@/api/signals";
import type { Strategy } from "@/api/types";

vi.mock("@/api/strategies");
vi.mock("@/api/signals");
vi.mock("@/hooks/useWorkbenchSocket", () => ({
  useWorkbenchSocket: () => {},
}));

const mockedStrategiesApi = vi.mocked(strategiesApi);
const mockedSignalsApi = vi.mocked(signalsApi);

const _strategy = (over: Partial<Strategy> = {}): Strategy => ({
  id: 1,
  name: "rsi-test",
  version: "0.1.0",
  type: "python",
  status: "idle",
  code_path: "examples/rsi_meanreversion.py",
  params: {},
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
  vi.spyOn(window, "confirm").mockReturnValue(true);
  mockedSignalsApi.list.mockResolvedValue({ items: [], count: 0 });
});

describe("StrategiesListPage", () => {
  it("renders strategies with status badges", async () => {
    mockedStrategiesApi.list.mockResolvedValue({
      items: [_strategy({ id: 1, name: "rsi-1" }), _strategy({ id: 2, name: "rsi-2", status: "paper" })],
      count: 2,
    });
    render(<MemoryRouter><StrategiesListPage /></MemoryRouter>);
    expect(await screen.findByText("rsi-1")).toBeInTheDocument();
    expect(await screen.findByText("rsi-2")).toBeInTheDocument();
    expect(await screen.findByText("PAPER")).toBeInTheDocument();
    expect(await screen.findAllByText("IDLE")).toHaveLength(1);
  });

  it("Start button calls strategiesApi.start", async () => {
    mockedStrategiesApi.list.mockResolvedValue({
      items: [_strategy({ id: 1, name: "rsi-1", status: "idle" })],
      count: 1,
    });
    mockedStrategiesApi.start.mockResolvedValue({
      strategy_id: 1, action: "start", new_status: "paper", run_id: 99,
    });
    render(<MemoryRouter><StrategiesListPage /></MemoryRouter>);
    await screen.findByText("rsi-1");
    fireEvent.click(screen.getByText("Start"));
    await waitFor(() => expect(mockedStrategiesApi.start).toHaveBeenCalledWith(1));
  });

  it("Stop button calls strategiesApi.stop on PAPER strategy", async () => {
    mockedStrategiesApi.list.mockResolvedValue({
      items: [_strategy({ id: 1, name: "rsi-running", status: "paper" })],
      count: 1,
    });
    mockedStrategiesApi.stop.mockResolvedValue({
      strategy_id: 1, action: "stop", new_status: "idle", run_id: null,
    });
    render(<MemoryRouter><StrategiesListPage /></MemoryRouter>);
    await screen.findByText("rsi-running");
    fireEvent.click(screen.getByText("Stop"));
    await waitFor(() => expect(mockedStrategiesApi.stop).toHaveBeenCalledWith(1));
  });

  it("ERROR status disables Start button with explanatory label", async () => {
    mockedStrategiesApi.list.mockResolvedValue({
      items: [_strategy({ id: 1, name: "broken", status: "error", error_text: "loader failed" })],
      count: 1,
    });
    render(<MemoryRouter><StrategiesListPage /></MemoryRouter>);
    const btn = await screen.findByText("Errored") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
