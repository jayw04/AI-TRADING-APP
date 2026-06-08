import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DiscoveryMatchesWidget } from "../DiscoveryMatchesWidget";
import type { OppDiscoveryMatchItem } from "@/api/types";
import { strategyTemplatesApi } from "@/api/strategyTemplates";

const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigate };
});
vi.mock("@/api/strategyTemplates", () => ({
  strategyTemplatesApi: { applyRange: vi.fn() },
}));
const mockedTmpl = vi.mocked(strategyTemplatesApi, true);

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
  beforeEach(() => vi.clearAllMocks());

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

  it("applies the range template and navigates", async () => {
    mockedTmpl.applyRange.mockResolvedValue({
      id: 5,
      name: "Range Trader AAPL",
      status: "idle",
      code_path: "templates/range_trader.py",
      authoring_method: "template",
      symbol: "AAPL",
      prefilled_from_range_insight: true,
    });
    renderWidget([ITEM]);
    fireEvent.click(screen.getByRole("button", { name: /^apply/i }));
    await waitFor(() => expect(mockedTmpl.applyRange).toHaveBeenCalledWith("AAPL"));
    expect(navigate).toHaveBeenCalledWith("/strategies/5");
  });
});
