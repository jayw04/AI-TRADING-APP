/**
 * BacktestRunModal — async-progress flow.
 *
 * Mocks the three I/O surfaces:
 *  - strategiesApi (submitBacktest + getBacktest)
 *  - backtestJobsApi (get + cancel)
 *  - useWorkbenchSocket — captures the registered handler so tests can fire
 *    synthetic WS messages and assert the modal reacts.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { BacktestRunModal } from "../BacktestRunModal";
import { strategiesApi, backtestJobsApi } from "@/api/strategies";
import { useWorkbenchSocket, type WorkbenchMessage } from "@/hooks/useWorkbenchSocket";
import type { Strategy } from "@/api/types";

vi.mock("@/api/strategies");
vi.mock("@/hooks/useWorkbenchSocket");

const mockedStrategiesApi = vi.mocked(strategiesApi, true);
const mockedBacktestJobsApi = vi.mocked(backtestJobsApi, true);
const mockedUseWorkbenchSocket = vi.mocked(useWorkbenchSocket);

const strategy: Strategy = {
  id: 7,
  name: "rsi-mr",
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
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

let capturedHandler: ((msg: WorkbenchMessage) => void) | null = null;

function emit(topic: string, payload: Record<string, unknown>) {
  if (!capturedHandler) throw new Error("WS handler not captured yet");
  act(() => {
    capturedHandler!({
      topic,
      type: topic,
      payload,
      ts: new Date().toISOString(),
    });
  });
}

beforeEach(() => {
  vi.resetAllMocks();
  capturedHandler = null;
  mockedUseWorkbenchSocket.mockImplementation((_topics, handler) => {
    capturedHandler = handler;
  });
  mockedStrategiesApi.submitBacktest.mockResolvedValue({
    job_id: 99,
    strategy_id: 7,
    status: "queued",
    submitted_at: "2026-01-01T00:00:00Z",
  });
  // Polling fallback returns whatever WS hasn't already delivered. Default
  // to a `running` snapshot so the poll loop doesn't accidentally finalize
  // for us during the progress-event test.
  mockedBacktestJobsApi.get.mockResolvedValue({
    id: 99,
    user_id: 1,
    strategy_id: 7,
    result_id: null,
    status: "running",
    label: "default",
    percent_complete: 0,
    current_ts: null,
    submitted_at: "2026-01-01T00:00:00Z",
    started_at: null,
    completed_at: null,
    error_text: null,
  });
});

describe("BacktestRunModal", () => {
  it("renders WS progress events into a moving progress bar", async () => {
    render(<BacktestRunModal strategy={strategy} onClose={() => {}} onCompleted={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    // submit fires immediately; status block appears with `polling` indicator.
    await waitFor(() => expect(screen.getByTestId("bt-status")).toBeInTheDocument());
    expect(mockedStrategiesApi.submitBacktest).toHaveBeenCalledTimes(1);

    // WS started -> running.
    emit("backtest.started", { job_id: 99, strategy_id: 7 });
    expect(screen.getByTestId("bt-status").textContent).toMatch(/running/);
    expect(screen.getByTestId("bt-status").textContent).toMatch(/live/);

    // WS progress -> bar width updates; current_ts surfaces in the status block.
    emit("backtest.progress", {
      job_id: 99,
      strategy_id: 7,
      percent_complete: 0.42,
      current_ts: "2026-01-02T15:30:00Z",
    });
    const bar = screen.getByTestId("bt-progress-bar") as HTMLDivElement;
    expect(bar.style.width).toBe("42%");
    expect(screen.getByTestId("bt-status").textContent).toContain("2026-01-02T15:30:00Z");
  });

  it("ignores WS messages whose job_id doesn't match this modal's submission", async () => {
    render(<BacktestRunModal strategy={strategy} onClose={() => {}} onCompleted={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));
    await waitFor(() => expect(screen.getByTestId("bt-status")).toBeInTheDocument());

    // Some other backtest is firing on the bus — must not move our bar.
    emit("backtest.progress", {
      job_id: 555,
      strategy_id: 7,
      percent_complete: 0.9,
      current_ts: "2026-01-02T15:30:00Z",
    });
    const bar = screen.getByTestId("bt-progress-bar") as HTMLDivElement;
    expect(bar.style.width).toBe("0%");
  });

  it("WS completed event triggers result fetch + onCompleted callback", async () => {
    const completedResult = {
      id: 17,
      strategy_id: 7,
      label: "default",
      params: {},
      metrics: {
        total_return: 0.05,
        annualized_return: 0.2,
        sharpe_ratio: 1.4,
        max_drawdown: -0.08,
        win_rate: 0.6,
        profit_factor: 1.8,
        trade_count: 10,
        avg_win: 100,
        avg_loss: -50,
        avg_trade_duration_seconds: 1000,
        starting_equity: 100000,
        ending_equity: 105000,
      },
      equity_curve: [],
      trades: [],
      range_start: "2026-01-01T00:00:00Z",
      range_end: "2026-01-10T00:00:00Z",
      created_at: "2026-01-10T00:00:00Z",
    };
    mockedStrategiesApi.getBacktest.mockResolvedValue(completedResult);

    const onCompleted = vi.fn();
    render(<BacktestRunModal strategy={strategy} onClose={() => {}} onCompleted={onCompleted} />);
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));
    await waitFor(() => expect(screen.getByTestId("bt-status")).toBeInTheDocument());

    emit("backtest.completed", { job_id: 99, strategy_id: 7, backtest_id: 17 });

    await waitFor(() =>
      expect(mockedStrategiesApi.getBacktest).toHaveBeenCalledWith(7, 17),
    );
    await waitFor(() => expect(onCompleted).toHaveBeenCalledWith(completedResult));
  });

  it("WS failed event surfaces the error_text in the modal", async () => {
    render(<BacktestRunModal strategy={strategy} onClose={() => {}} onCompleted={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));
    await waitFor(() => expect(screen.getByTestId("bt-status")).toBeInTheDocument());

    emit("backtest.failed", {
      job_id: 99,
      strategy_id: 7,
      error_text: "bar cache empty for AAPL",
    });

    await waitFor(() =>
      expect(screen.getByTestId("bt-error").textContent).toMatch(/bar cache empty/),
    );
  });

  it("Cancel button calls the cancel API; backtest.cancelled WS event finalizes", async () => {
    mockedBacktestJobsApi.cancel.mockResolvedValue({
      id: 99,
      user_id: 1,
      strategy_id: 7,
      result_id: null,
      status: "cancelled",
      label: "default",
      percent_complete: 0.2,
      current_ts: null,
      submitted_at: "2026-01-01T00:00:00Z",
      started_at: "2026-01-01T00:00:01Z",
      completed_at: "2026-01-01T00:00:02Z",
      error_text: null,
    });

    render(<BacktestRunModal strategy={strategy} onClose={() => {}} onCompleted={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));
    await waitFor(() => expect(screen.getByTestId("bt-status")).toBeInTheDocument());

    // Started -> Cancel button appears.
    emit("backtest.started", { job_id: 99, strategy_id: 7 });
    const cancelBtn = await screen.findByRole("button", { name: /Cancel backtest/ });
    fireEvent.click(cancelBtn);

    await waitFor(() => expect(mockedBacktestJobsApi.cancel).toHaveBeenCalledWith(99));

    // Backend responds by firing the cancelled topic.
    emit("backtest.cancelled", { job_id: 99, strategy_id: 7, reason: "user_request" });
    await waitFor(() =>
      expect(screen.getByTestId("bt-error").textContent).toMatch(/cancelled/i),
    );
  });
});
