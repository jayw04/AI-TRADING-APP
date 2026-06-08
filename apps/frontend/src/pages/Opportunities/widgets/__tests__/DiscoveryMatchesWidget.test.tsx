import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DiscoveryMatchesWidget } from "../DiscoveryMatchesWidget";
import type { OppDiscoveryMatchItem } from "@/api/types";

const ITEM: OppDiscoveryMatchItem = {
  symbol: "AAPL",
  scan_name: "Oversold",
  definition_id: 1,
  run_id: 9,
  values: { RSI14: 30.12 },
  run_at: "2026-06-07T12:00:00Z",
};

function renderWidget(items: OppDiscoveryMatchItem[]) {
  return render(
    <MemoryRouter>
      <DiscoveryMatchesWidget items={items} count={items.length} asOf="" />
    </MemoryRouter>,
  );
}

describe("DiscoveryMatchesWidget", () => {
  it("renders matched symbols + values", () => {
    renderWidget([ITEM]);
    expect(screen.getByText("AAPL")).toBeTruthy();
    expect(screen.getByText("Oversold")).toBeTruthy();
    expect(screen.getByText(/RSI14 30\.12/)).toBeTruthy();
  });

  it("shows an empty state with no matches", () => {
    renderWidget([]);
    expect(screen.getByText(/No scheduled-scan matches/i)).toBeTruthy();
  });
});
