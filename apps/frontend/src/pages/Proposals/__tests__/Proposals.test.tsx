/**
 * Proposals page — renders proposals with state + confidence badges, hides
 * low-confidence proposals when the envelope opts in, and wires the Accept
 * action. The API modules are mocked.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Proposals from "../index";
import { proposalsApi, type Proposal } from "@/api/proposals";
import { tradingProfileApi } from "@/api/tradingProfile";
import { apiFetch } from "@/api/client";

vi.mock("@/api/proposals");
vi.mock("@/api/tradingProfile");
vi.mock("@/api/client");

const mockedProposals = vi.mocked(proposalsApi, true);
const mockedProfile = vi.mocked(tradingProfileApi, true);
const mockedFetch = vi.mocked(apiFetch);

function proposal(over: Partial<Proposal> = {}): Proposal {
  return {
    id: 1,
    strategy_id: 1,
    user_id: 1,
    state: "REVIEWING",
    proposal_payload: { confidence: "HIGH", summary: "Tune RSI", changes: [] },
    evidence_bundle: {},
    evaluation_results: {},
    generated_at: "2026-06-02T09:00:00Z",
    transitioned_at: "2026-06-02T09:00:00Z",
    ...over,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Proposals />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mockedFetch.mockResolvedValue({ items: [] } as never);
  mockedProfile.get.mockResolvedValue({
    user_id: 1, watchlist: {}, bias_criteria: {}, bias_thresholds: {},
    session_preferences: {}, risk_preferences: {}, agent_envelope: {},
  });
});

describe("Proposals page", () => {
  it("renders proposals with state and confidence badges", async () => {
    mockedProposals.list.mockResolvedValue({ items: [proposal()] });
    renderPage();
    expect(await screen.findByText("Tune RSI")).toBeInTheDocument();
    expect(screen.getByText("REVIEWING")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });

  it("hides low-confidence proposals when the envelope opts in", async () => {
    mockedProfile.get.mockResolvedValue({
      user_id: 1, watchlist: {}, bias_criteria: {}, bias_thresholds: {},
      session_preferences: {}, risk_preferences: {},
      agent_envelope: { hide_low_confidence_proposals: true },
    });
    mockedProposals.list.mockResolvedValue({
      items: [
        proposal({ id: 1, proposal_payload: { confidence: "LOW", summary: "low one", changes: [] } }),
        proposal({ id: 2, proposal_payload: { confidence: "HIGH", summary: "high one", changes: [] } }),
      ],
    });
    renderPage();
    expect(await screen.findByText("high one")).toBeInTheDocument();
    expect(screen.queryByText("low one")).not.toBeInTheDocument();
  });

  it("accept button calls the API", async () => {
    mockedProposals.list.mockResolvedValue({ items: [proposal()] });
    mockedProposals.accept.mockResolvedValue(proposal({ state: "ACCEPTED" }));
    renderPage();
    fireEvent.click(await screen.findByText("Tune RSI"));
    fireEvent.click(await screen.findByRole("button", { name: /^accept$/i }));
    await waitFor(() => expect(mockedProposals.accept).toHaveBeenCalledWith(1));
  });
});
