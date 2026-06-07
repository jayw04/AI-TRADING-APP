/**
 * P7 §4 — "Author with AI" page. Describe → generate → review (code + backtest +
 * assumptions) → save. The API module + router navigation are mocked.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AuthorWithAI from "../AuthorWithAI";
import { strategyAuthoringApi, type AuthorResult } from "@/api/strategyAuthoring";

const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigate };
});
vi.mock("@/api/strategyAuthoring");

const mocked = vi.mocked(strategyAuthoringApi, true);

const RESULT: AuthorResult = {
  code: "class Gen(Strategy):\n    pass",
  assumptions: ["RSI period 14 (you didn't specify)"],
  explanation: "Buys oversold, sells overbought.",
  cost_usd: 0.0321,
  model: "claude-sonnet-4-6",
  prompt_version: "v1",
  backtest: {
    status: "ok",
    trade_count: 12,
    error: null,
    metrics: {
      total_return: 0.15, annualized_return: 0.3, sharpe_ratio: 1.4,
      max_drawdown: -0.08, win_rate: 0.55, profit_factor: 1.8,
      trade_count: 12, starting_equity: 100000, ending_equity: 115000,
    },
  },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthorWithAI />
    </MemoryRouter>,
  );
}

describe("AuthorWithAI", () => {
  beforeEach(() => vi.clearAllMocks());

  it("generates and shows code + backtest + assumptions", async () => {
    mocked.author.mockResolvedValue(RESULT);
    renderPage();
    fireEvent.change(screen.getByPlaceholderText(/Buy SPY when/i), {
      target: { value: "rsi mean reversion" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Generate$/i }));
    await waitFor(() => expect(mocked.author).toHaveBeenCalledWith("rsi mean reversion"));
    expect(await screen.findByText(/class Gen/)).toBeTruthy();
    expect(screen.getByText(/RSI period 14/)).toBeTruthy();
    expect(screen.getByText(/Sharpe/)).toBeTruthy();
    expect(screen.getByText("1.40")).toBeTruthy(); // sharpe formatted
  });

  it("saves and navigates to the new strategy", async () => {
    mocked.author.mockResolvedValue(RESULT);
    mocked.saveAuthored.mockResolvedValue({
      id: 7, name: "My Strat", status: "idle", code_path: "my_strat.py",
      authoring_method: "nl_generation",
    });
    renderPage();
    fireEvent.change(screen.getByPlaceholderText(/Buy SPY when/i), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: /^Generate$/i }));
    await screen.findByText(/class Gen/);
    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), { target: { value: "My Strat" } });
    fireEvent.click(screen.getByRole("button", { name: /Save strategy/i }));
    await waitFor(() =>
      expect(mocked.saveAuthored).toHaveBeenCalledWith(
        RESULT.code,
        "My Strat",
        expect.arrayContaining([
          expect.objectContaining({ kind: "generation", user_message: "x", code: RESULT.code }),
        ]),
      ),
    );
    expect(navigate).toHaveBeenCalledWith("/strategies/7");
  });

  it("surfaces a budget (429) error", async () => {
    const { ApiError } = await import("@/api/client");
    mocked.author.mockRejectedValue(new ApiError(429, "over budget"));
    renderPage();
    fireEvent.change(screen.getByPlaceholderText(/Buy SPY when/i), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: /^Generate$/i }));
    expect(await screen.findByText(/Daily AI budget reached/i)).toBeTruthy();
  });
});
