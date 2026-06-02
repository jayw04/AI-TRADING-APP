/**
 * P6 §2a — the proposal-cadence dropdown on the Trading Profile envelope editor:
 * renders the 5 options, saves to agent_envelope.proposal_cadence, and warns
 * when the user has no Agent API Key.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TradingProfile from "../TradingProfile";
import { tradingProfileApi } from "@/api/tradingProfile";
import type { TradingProfile as Profile } from "@/api/tradingProfile";
import { credentialsApi } from "@/api/credentials";

vi.mock("@/api/tradingProfile");
vi.mock("@/api/credentials");

const mocked = vi.mocked(tradingProfileApi, true);
const mockedCreds = vi.mocked(credentialsApi, true);

function emptyProfile(over: Partial<Profile> = {}): Profile {
  return {
    user_id: 1, watchlist: {}, bias_criteria: {}, bias_thresholds: {},
    session_preferences: {}, risk_preferences: {}, agent_envelope: {}, ...over,
  };
}

function credMeta(has_value: boolean) {
  return [
    {
      kind: "agent_api_key", has_value,
      created_at: null, updated_at: null, last_used_at: null, revoked_at: null,
    },
  ];
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TradingProfile />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mocked.get.mockResolvedValue(emptyProfile());
  mocked.update.mockImplementation((c) => Promise.resolve(emptyProfile(c as Partial<Profile>)));
  mockedCreds.list.mockResolvedValue(credMeta(true));
});

describe("Trading Profile — proposal cadence", () => {
  it("renders the cadence dropdown with all 5 options", async () => {
    renderPage();
    const select = (await screen.findByLabelText(/Proposal cadence/i)) as HTMLSelectElement;
    expect(select.querySelectorAll("option")).toHaveLength(5);
    expect(screen.getByRole("option", { name: /Off/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /market open/i })).toBeInTheDocument();
  });

  it("saves the selected cadence to agent_envelope.proposal_cadence", async () => {
    renderPage();
    const select = await screen.findByLabelText(/Proposal cadence/i);
    fireEvent.change(select, { target: { value: "daily" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(mocked.update).toHaveBeenCalledTimes(1));
    expect(mocked.update).toHaveBeenCalledWith({
      agent_envelope: { proposal_cadence: "daily" },
    });
  });

  it("warns when the user has no Agent API Key", async () => {
    mockedCreds.list.mockResolvedValue(credMeta(false));
    renderPage();
    expect(await screen.findByText(/haven't set an Agent API Key/i)).toBeInTheDocument();
  });

  it("does not warn when the Agent API Key exists", async () => {
    mockedCreds.list.mockResolvedValue(credMeta(true));
    renderPage();
    await screen.findByLabelText(/Proposal cadence/i);
    expect(screen.queryByText(/haven't set an Agent API Key/i)).not.toBeInTheDocument();
  });
});
