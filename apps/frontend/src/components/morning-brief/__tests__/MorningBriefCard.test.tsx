import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MorningBriefCard from "../MorningBriefCard";
import { morningBriefApi } from "@/api/morningBrief";
import type { MorningBrief } from "@/api/morningBrief";
import { driftApi } from "@/api/drift";

vi.mock("@/api/morningBrief");
vi.mock("@/api/drift");

const mocked = vi.mocked(morningBriefApi, true);
const mockedDrift = vi.mocked(driftApi, true);

function brief(over: Partial<MorningBrief> = {}): MorningBrief {
  return {
    user_id: 1,
    brief_date: "2026-06-02",
    symbols: [
      { symbol: "AAPL", bias: "bullish", key_level: 175.5, watch_for: "RSI 60", indicators: { rsi: 60 } },
      { symbol: "MSFT", bias: "bearish", key_level: 410, watch_for: "RSI 40", indicators: { rsi: 40 } },
    ],
    overall_note: "",
    agent_used: false,
    trigger: "manual",
    generated_at: new Date().toISOString(),
    ...over,
  };
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MorningBriefCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mocked.today.mockResolvedValue(brief());
  mocked.recent.mockResolvedValue([brief(), brief({ symbols: [{ symbol: "AAPL", bias: "neutral", key_level: null, watch_for: "", indicators: {} }] })]);
  mocked.generate.mockResolvedValue(brief());
  mockedDrift.findings.mockResolvedValue({ items: [] });
});

describe("MorningBriefCard", () => {
  it("renders bias counts", async () => {
    renderCard();
    expect(await screen.findByText("1 bullish")).toBeInTheDocument();
    expect(screen.getByText("1 bearish")).toBeInTheDocument();
    expect(screen.getByText("0 neutral")).toBeInTheDocument();
  });

  it("regenerate button calls the API", async () => {
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: /regenerate/i }));
    await waitFor(() => expect(mocked.generate).toHaveBeenCalledTimes(1));
  });

  it("compare-to-yesterday toggle fetches recent briefs", async () => {
    renderCard();
    await screen.findByText("1 bullish");
    expect(mocked.recent).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText(/compare to yesterday/i));
    await waitFor(() => expect(mocked.recent).toHaveBeenCalled());
  });

  it("expanding a symbol reveals its indicators", async () => {
    renderCard();
    fireEvent.click(await screen.findByText("AAPL"));
    expect(await screen.findByText(/"rsi": 60/)).toBeInTheDocument();
  });

  it("shows an empty state when there is no brief", async () => {
    mocked.today.mockResolvedValue(null);
    renderCard();
    expect(await screen.findByText(/No brief yet for today/i)).toBeInTheDocument();
  });

  it("renders the drift section when findings exist", async () => {
    mockedDrift.findings.mockResolvedValue({
      items: [
        {
          strategy_id: 7, detected_at: "2026-06-03T00:00:00Z", breached: ["win_rate"],
          win_rate: {}, avg_return_per_trade: {}, trade_count: 25, audit_id: 1,
        },
      ],
    });
    renderCard();
    expect(await screen.findByText(/Strategy drift detected/i)).toBeInTheDocument();
    expect(screen.getByText(/Strategy #7/)).toBeInTheDocument();
  });

  it("renders no drift section when there are no findings", async () => {
    renderCard();
    await screen.findByText("1 bullish");
    expect(screen.queryByText(/Strategy drift detected/i)).not.toBeInTheDocument();
  });
});
