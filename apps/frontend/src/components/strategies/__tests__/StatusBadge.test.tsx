import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "../StatusBadge";
import type { StrategyStatus } from "@/api/types";

describe("StatusBadge", () => {
  it("renders every status value", () => {
    const statuses: StrategyStatus[] = [
      "idle",
      "backtest",
      "paper",
      "live",
      "halted",
      "error",
    ];
    for (const s of statuses) {
      const { unmount } = render(<StatusBadge status={s} />);
      expect(screen.getByText(s.toUpperCase())).toBeInTheDocument();
      unmount();
    }
  });

  it("PAPER badge uses emerald color", () => {
    render(<StatusBadge status="paper" />);
    expect(screen.getByText("PAPER").className).toContain("emerald");
  });

  it("LIVE badge uses red color", () => {
    render(<StatusBadge status="live" />);
    expect(screen.getByText("LIVE").className).toContain("red");
  });

  it("ERROR badge uses rose color", () => {
    render(<StatusBadge status="error" />);
    expect(screen.getByText("ERROR").className).toContain("rose");
  });
});
