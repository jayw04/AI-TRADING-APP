/**
 * Settings → Risk Limits save feedback.
 *
 * WHY THIS EXISTS. On 2026-08-10 an owner raised max_gross_exposure and could not
 * tell whether Save had worked: on success the page only invalidated the query, so
 * the refetch redisplayed the values just typed and nothing on screen moved. Only
 * the failure path had a message. The owner clicked Save again, producing a second
 * RISK_LIMITS_UPDATED audit entry with an empty diff (changes {old:{},new:{}}).
 *
 * So: success must be stated, and an unchanged form must not be submittable.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import RiskLimits from "../RiskLimits";
import { riskApi } from "@/api/risk";
import { accountsApi } from "@/api/accounts";

vi.mock("@/api/risk");
vi.mock("@/api/accounts");
vi.mock("@/components/risk/RiskStateBanner", () => ({ RiskStateBanner: () => null }));

const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}));

const mockedRisk = vi.mocked(riskApi, true);
const mockedAccounts = vi.mocked(accountsApi, true);

// Decimal columns come back as strings with trailing zeros — the exact shape
// that made a re-save look dirty.
const ROW = {
  id: 7,
  user_id: 5,
  broker_mode: "paper" as const,
  scope_type: "GLOBAL",
  scope_id: null,
  max_position_qty: 1000,
  max_position_notional: "25000.0000",
  max_gross_exposure: "100000.0000",
  max_daily_loss: "5000.0000",
  max_orders_per_minute: 200,
  max_orders_per_day: null,
  allow_short: false,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <RiskLimits />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const grossInput = async () =>
  (await screen.findByLabelText(/Max gross exposure/i)) as HTMLInputElement;
const saveBtn = () => screen.getByRole("button", { name: /^Save$/ }) as HTMLButtonElement;
const saveCloseBtn = () =>
  screen.getByRole("button", { name: /Save & close/i }) as HTMLButtonElement;

describe("Settings → Risk Limits save feedback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Stateful, so a refetch after save returns the NEW value — and returns it
    // in the server's Decimal-string shape, which is what the numeric
    // comparison has to cope with.
    let current = { ...ROW };
    mockedRisk.listLimits.mockImplementation(async () => ({ items: [current], count: 1 }));
    mockedRisk.updateLimits.mockImplementation(async (_id, changes) => {
      const applied: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(changes)) {
        applied[k] = typeof v === "string" && v !== "" ? `${Number(v).toFixed(4)}` : v;
      }
      current = { ...current, ...applied } as typeof ROW;
      return current;
    });
    mockedAccounts.list.mockResolvedValue({ items: [], count: 0 } as never);
  });

  it("states what was saved instead of leaving the page silent", async () => {
    renderPage();
    fireEvent.change(await grossInput(), { target: { value: "110000" } });
    fireEvent.click(saveBtn());

    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("Saved");
    expect(status.textContent).toContain("Max gross exposure 100000 → 110000");
  });

  it("disables both buttons until a value actually changes", async () => {
    renderPage();
    await grossInput();
    expect(saveBtn().disabled).toBe(true);
    expect(saveCloseBtn().disabled).toBe(true);

    fireEvent.change(await grossInput(), { target: { value: "110000" } });
    expect(saveBtn().disabled).toBe(false);
    expect(saveCloseBtn().disabled).toBe(false);
  });

  it("treats '110000' and the server's '110000.0000' as equal, so a re-save is not offered", async () => {
    // The duplicate-audit-entry bug: a numerically identical value must not
    // count as a change, or Save stays live and writes an empty diff.
    renderPage();
    fireEvent.change(await grossInput(), { target: { value: "100000" } });
    expect(saveBtn().disabled).toBe(true);
  });

  it("sends only the changed field", async () => {
    renderPage();
    fireEvent.change(await grossInput(), { target: { value: "110000" } });
    fireEvent.click(saveBtn());
    await waitFor(() =>
      expect(mockedRisk.updateLimits).toHaveBeenCalledWith(7, { max_gross_exposure: "110000" }),
    );
  });

  it("Save & close returns to Settings; plain Save stays put", async () => {
    renderPage();
    fireEvent.change(await grossInput(), { target: { value: "110000" } });
    fireEvent.click(saveCloseBtn());
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/settings"));

    navigate.mockClear();
    await waitFor(async () => expect((await grossInput()).value).toBe("110000.0000"));
    fireEvent.change(await grossInput(), { target: { value: "120000" } });
    fireEvent.click(saveBtn());
    await screen.findByRole("status");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("clears a stale confirmation as soon as the user edits again", async () => {
    renderPage();
    fireEvent.change(await grossInput(), { target: { value: "110000" } });
    fireEvent.click(saveBtn());
    await screen.findByRole("status");

    fireEvent.change(await grossInput(), { target: { value: "120000" } });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("does not claim success when the save failed", async () => {
    mockedRisk.updateLimits.mockRejectedValue(new Error("nope"));
    renderPage();
    fireEvent.change(await grossInput(), { target: { value: "110000" } });
    fireEvent.click(saveBtn());
    expect(await screen.findByText(/Save failed/i)).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
