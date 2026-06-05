/**
 * P6b §5 (ADR 0006 v2 §5) — LLMOptInCard. Renders the four states and runs the
 * typed-ack + TOTP opt-in flow. The API module is mocked.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { LLMOptInCard } from "../LLMOptInCard";
import { llmOptInApi, RISK_ACK_PHRASE } from "@/api/llmOptIn";
import type { Strategy } from "@/api/types";

vi.mock("@/api/llmOptIn", async (orig) => {
  const actual = await orig<typeof import("@/api/llmOptIn")>();
  return { ...actual, llmOptInApi: { status: vi.fn(), optIn: vi.fn(), optOut: vi.fn() } };
});

const mocked = vi.mocked(llmOptInApi, true);
const strategy = { id: 1, status: "live" } as unknown as Strategy;

const verdict = (eligible: boolean) => ({
  eligible, b_trade_count: eligible ? 60 : 30, window_days: eligible ? 40 : 18,
  min_trades: 50, min_days: 30, harness_active: true, reasons: [],
});

describe("LLMOptInCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the §4 progress when ineligible", async () => {
    mocked.status.mockResolvedValue({
      status: "none", strategy_id: 1, eligibility: verdict(false),
    });
    render(<LLMOptInCard strategy={strategy} />);
    expect(await screen.findByText(/30\/50 Mode-B trades, 18\/30 days/i)).toBeTruthy();
  });

  it("shows the cap on the active state", async () => {
    mocked.status.mockResolvedValue({
      status: "active", strategy_id: 1, daily_cap_cents: 500,
      spend_today_cents: 123, eligibility: verdict(true),
    });
    render(<LLMOptInCard strategy={strategy} />);
    expect(await screen.findByText(/\$1\.23 \/ \$5\.00 today/i)).toBeTruthy();
  });

  it("runs the typed-ack + TOTP opt-in flow when eligible", async () => {
    mocked.status.mockResolvedValue({
      status: "none", strategy_id: 1, eligibility: verdict(true),
    });
    mocked.optIn.mockResolvedValue({ status: "pending", opt_in_id: 1, activates_at: "" });
    render(<LLMOptInCard strategy={strategy} />);
    fireEvent.click(await screen.findByRole("button", { name: /Opt in to LLM-driven trading/i }));
    const confirm = screen.getByRole("button", { name: /^Opt in$/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true); // ack + totp empty
    fireEvent.change(screen.getByPlaceholderText(/type the acknowledgment phrase/i), {
      target: { value: RISK_ACK_PHRASE },
    });
    fireEvent.change(screen.getByPlaceholderText(/TOTP code/i), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: /^Opt in$/i }));
    await waitFor(() => expect(mocked.optIn).toHaveBeenCalledWith(1, RISK_ACK_PHRASE, "123456"));
  });
});
