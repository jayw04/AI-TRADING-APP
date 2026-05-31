/**
 * ModeBanner — P5 §1 LIVE-account precedence plus the existing paper/unknown
 * states. The banner queries the singular AccountState endpoint (mode of the
 * active account) AND the plural accounts list (does ANY account run live).
 *
 * Mocks are factory-based and driven by mutable holders so each test sets the
 * two endpoints' results independently without mock-reset bleed.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ModeBanner from "../ModeBanner";

let accountResult: unknown;
let accountsResult: unknown; // either a list response, or an Error to reject

vi.mock("@/api/account", () => ({
  accountApi: { get: () => Promise.resolve(accountResult) },
}));

vi.mock("@/api/accounts", () => ({
  accountsApi: {
    list: () =>
      accountsResult instanceof Error
        ? Promise.reject(accountsResult)
        : Promise.resolve(accountsResult),
  },
}));

function paperAccountState() {
  return { account_id: 1, mode: "paper", status: "ACTIVE" };
}

function brokerAccount(id: number, mode: "paper" | "live", broker = "alpaca") {
  return {
    id,
    user_id: 1,
    broker,
    mode,
    label: `${mode}-${id}`,
    broker_mode_locked_at: mode === "live" ? new Date().toISOString() : null,
    created_at: new Date().toISOString(),
  };
}

function renderBanner() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ModeBanner />
    </QueryClientProvider>,
  );
}

describe("ModeBanner", () => {
  beforeEach(() => {
    accountResult = paperAccountState();
    accountsResult = { items: [], count: 0 };
  });

  it("shows the paper banner when no account is live", async () => {
    accountsResult = { items: [brokerAccount(1, "paper")], count: 1 };
    renderBanner();
    await waitFor(() => {
      expect(screen.getByLabelText("Trading mode")).toHaveTextContent(/paper/i);
    });
    expect(screen.getByLabelText("Trading mode")).not.toHaveTextContent(
      /live account/i,
    );
  });

  it("shows the red LIVE banner when one account is live", async () => {
    accountsResult = {
      items: [brokerAccount(1, "paper"), brokerAccount(2, "live")],
      count: 2,
    };
    renderBanner();
    expect(await screen.findByText(/live account —/i)).toBeInTheDocument();
    expect(screen.getByText(/move real money/i)).toBeInTheDocument();
  });

  it("uses the plural form for multiple live accounts", async () => {
    accountsResult = {
      items: [brokerAccount(1, "live", "alpaca"), brokerAccount(2, "live", "ibkr")],
      count: 2,
    };
    renderBanner();
    expect(await screen.findByText(/2 live accounts/i)).toBeInTheDocument();
  });

  it("does not crash if the accounts list errors (best-effort)", async () => {
    accountsResult = new Error("boom");
    renderBanner();
    // Falls back to the singular paper banner.
    await waitFor(() => {
      expect(screen.getByLabelText("Trading mode")).toHaveTextContent(/paper/i);
    });
  });
});
