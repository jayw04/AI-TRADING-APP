import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CostMeter } from "../CostMeter";

describe("CostMeter", () => {
  it("renders green at <50%", () => {
    render(
      <CostMeter
        budget={{
          spent_usd: "0.40",
          budget_usd: "2.0",
          remaining_usd: "1.60",
          pct_used: 20,
        }}
      />,
    );
    const txt = screen.getByText(/\$0\.40 \/ \$2\.00 today/);
    expect(txt.className).toContain("emerald");
  });

  it("renders amber at 50–80%", () => {
    render(
      <CostMeter
        budget={{
          spent_usd: "1.20",
          budget_usd: "2.0",
          remaining_usd: "0.80",
          pct_used: 60,
        }}
      />,
    );
    const txt = screen.getByText(/\$1\.20 \/ \$2\.00 today/);
    expect(txt.className).toContain("amber");
  });

  it("renders rose at >=80%", () => {
    render(
      <CostMeter
        budget={{
          spent_usd: "1.80",
          budget_usd: "2.0",
          remaining_usd: "0.20",
          pct_used: 90,
        }}
      />,
    );
    const txt = screen.getByText(/\$1\.80 \/ \$2\.00 today/);
    expect(txt.className).toContain("rose");
  });
});
