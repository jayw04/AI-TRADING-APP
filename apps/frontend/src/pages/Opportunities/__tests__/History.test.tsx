import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import OpportunityHistoryPage from "../History";
import { opportunitiesApi } from "@/api/opportunities";
import type { OppHistoryOccurrence, OppHistoryResponse } from "@/api/types";

vi.mock("@/api/opportunities");

const mocked = vi.mocked(opportunitiesApi);

function occurrence(
  over: Partial<OppHistoryOccurrence> = {},
): OppHistoryOccurrence {
  return {
    symbol: "NVDA",
    family: "OVERSOLD",
    candidate_date: "2026-08-19",
    horizon: "1–10d",
    status_at_proposal: "Watch",
    proposal_price: 120.5,
    proposal_price_source: "sharadar.sep",
    adjustment_basis: "sharadar.sep",
    reason: { chips: [{ key: "rsi14", value: "24" }], why: "stretched" },
    screen_id: "DISC-001-WATCHLIST",
    screen_version: "v0.3.0",
    snapshot_sha256: "aa",
    snapshot_generated_at: "2026-08-20T20:20:00Z",
    first_seen: "2026-08-14",
    last_seen: "2026-08-19",
    occurrence_count: 2,
    current_price: 130,
    current_price_as_of: "2026-08-20",
    current_price_source: "sharadar.sep",
    change_pct: 130 / 120.5 - 1,
    ...over,
  };
}

function summary(): OppHistoryResponse {
  return {
    view: "summary",
    count: 1,
    items: [occurrence()],
    as_of: new Date().toISOString(),
  };
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("OpportunityHistoryPage", () => {
  it("renders the last-occurrence table", async () => {
    mocked.history.mockResolvedValue(summary());
    render(
      <MemoryRouter>
        <OpportunityHistoryPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Opportunity History")).toBeTruthy();
    expect(screen.getByText("NVDA")).toBeTruthy();
    expect(screen.getByText("OVERSOLD")).toBeTruthy();
    expect(screen.getByText("$120.50")).toBeTruthy();
    expect(screen.getByText("$130.00")).toBeTruthy();
  });

  it("loads a symbol timeline when a row is clicked", async () => {
    mocked.history.mockImplementation(async (params) => {
      if (params?.symbol === "NVDA") {
        return {
          view: "timeline",
          count: 2,
          items: [
            occurrence({ candidate_date: "2026-08-14", proposal_price: 100 }),
            occurrence(),
          ],
          as_of: new Date().toISOString(),
        };
      }
      return summary();
    });
    render(
      <MemoryRouter>
        <OpportunityHistoryPage />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "NVDA" }));
    await waitFor(() => {
      expect(screen.getByText("NVDA timeline")).toBeTruthy();
      expect(screen.getByText("2026-08-14")).toBeTruthy();
    });
  });

  it("has no apply-to-strategy control", async () => {
    mocked.history.mockResolvedValue(summary());
    render(
      <MemoryRouter>
        <OpportunityHistoryPage />
      </MemoryRouter>,
    );
    await screen.findByText("NVDA");
    expect(screen.queryByRole("button", { name: /apply/i })).toBeNull();
  });
});
