/**
 * TradingProfile (Settings) — renders the five sections, sends only changed
 * sections on save, and round-trips the JSON power-user mode. The API module is
 * mocked; we drive the form via React Testing Library.
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
    user_id: 1,
    watchlist: {},
    bias_criteria: {},
    bias_thresholds: {},
    session_preferences: {},
    risk_preferences: {},
    agent_envelope: {},
    ...over,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
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
  mocked.update.mockImplementation((changes) =>
    Promise.resolve(emptyProfile(changes as Partial<Profile>)),
  );
  mockedCreds.list.mockResolvedValue([
    {
      kind: "agent_api_key", has_value: true,
      created_at: null, updated_at: null, last_used_at: null, revoked_at: null,
    },
  ]);
});

describe("TradingProfile settings page", () => {
  it("renders all six sections including the agent envelope", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Watchlist")).toBeInTheDocument();
      expect(screen.getByText("Bias Criteria")).toBeInTheDocument();
      expect(screen.getByText("Bias Thresholds")).toBeInTheDocument();
      expect(screen.getByText("Session Preferences")).toBeInTheDocument();
      expect(screen.getByText("Risk Preferences")).toBeInTheDocument();
      expect(screen.getByText("Agent Envelope")).toBeInTheDocument();
    });
  });

  it("envelope save sends agent_envelope with parsed prohibitions", async () => {
    renderPage();
    const prohibitions = await screen.findByLabelText(/Prohibitions/i);
    fireEvent.change(prohibitions, {
      target: { value: "never propose options\nnever increase size" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(mocked.update).toHaveBeenCalledTimes(1));
    expect(mocked.update).toHaveBeenCalledWith({
      agent_envelope: {
        prohibitions: ["never propose options", "never increase size"],
      },
    });
  });

  it("loads and displays an existing watchlist value", async () => {
    mocked.get.mockResolvedValue(
      emptyProfile({ watchlist: { core: ["AAPL", "MSFT"] } }),
    );
    renderPage();
    expect(await screen.findByDisplayValue("AAPL, MSFT")).toBeInTheDocument();
  });

  it("save sends only the changed section", async () => {
    renderPage();
    const coreInput = await screen.findByLabelText(/Core/i);
    fireEvent.change(coreInput, { target: { value: "aapl" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(mocked.update).toHaveBeenCalledTimes(1));
    expect(mocked.update).toHaveBeenCalledWith({ watchlist: { core: ["AAPL"] } });
  });

  it("no-op save sends an empty payload (no sections changed)", async () => {
    renderPage();
    await screen.findByText("Watchlist");
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(mocked.update).toHaveBeenCalledTimes(1));
    expect(mocked.update).toHaveBeenCalledWith({});
  });

  it("JSON-edit mode round-trips data without corruption", async () => {
    mocked.get.mockResolvedValue(
      emptyProfile({ bias_thresholds: { bullish: { rsi_min: 55 } } }),
    );
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /edit as json/i }));
    const textarea = screen.getByRole("textbox");
    expect((textarea as HTMLTextAreaElement).value).toContain('"rsi_min": 55');
    // Apply unchanged JSON, then save → no sections changed.
    fireEvent.click(screen.getByRole("button", { name: /apply json/i }));
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(mocked.update).toHaveBeenCalledTimes(1));
    expect(mocked.update).toHaveBeenCalledWith({});
  });
});
