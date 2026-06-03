/** P6 §2b-backtest — EvalPanel renders each eval state correctly. */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvalPanel } from "@/components/proposals/EvalPanel";
import type { EvaluationResults } from "@/api/proposals";

function panel(ev: EvaluationResults) {
  return render(<EvalPanel ev={ev} />);
}

describe("EvalPanel", () => {
  it("complete + above_baseline shows the metrics table + verdict", () => {
    panel({
      status: "complete",
      verdict: "above_baseline",
      window_days: 90,
      completed_at: "2026-06-03T12:00:00Z",
      baseline_metrics: { sharpe_ratio: 1.0, max_drawdown: -0.1 },
      variant_metrics: { sharpe_ratio: 1.3, max_drawdown: -0.1 },
      delta_metrics: { sharpe_ratio_delta: 0.3 },
    });
    expect(screen.getByText(/Above baseline/i)).toBeInTheDocument();
    expect(screen.getByText("sharpe_ratio")).toBeInTheDocument();
    expect(screen.getByText("0.300")).toBeInTheDocument(); // delta cell
  });

  it("complete + below_baseline shows the below label", () => {
    panel({ status: "complete", verdict: "below_baseline" });
    expect(screen.getByText(/Below baseline/i)).toBeInTheDocument();
  });

  it("pending shows an in-progress message", () => {
    panel({ status: "pending", window_days: 90 });
    expect(screen.getByText(/Backtest in progress/i)).toBeInTheDocument();
  });

  it("skipped shows the skipped reason", () => {
    panel({ status: "skipped", skipped_reason: "non_python_strategy" });
    expect(screen.getByText(/non_python_strategy/i)).toBeInTheDocument();
  });

  it("failed shows the failure reason", () => {
    panel({ status: "failed", failure_reason: "baseline_failed: boom" });
    expect(screen.getByText(/baseline_failed: boom/i)).toBeInTheDocument();
  });

  it("renders nothing when there is no eval status", () => {
    const { container } = panel({});
    expect(container.firstChild).toBeNull();
  });
});
