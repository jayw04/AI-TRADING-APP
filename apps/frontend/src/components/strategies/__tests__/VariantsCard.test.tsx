import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VariantsCard } from "../VariantsCard";
import { variantsApi, type InFlightVariant } from "@/api/variants";

vi.mock("@/api/variants");
const mocked = vi.mocked(variantsApi, true);

function renderCard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <VariantsCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function variant(over: Partial<InFlightVariant> = {}): InFlightVariant {
  return {
    variant_strategy_id: 2,
    parent_strategy_id: 1,
    parent_strategy_name: "Momentum",
    parent_strategy_status: "live",
    spawn_proposal_id: 5,
    spawned_at: "2026-06-14T00:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("VariantsCard", () => {
  it("renders nothing when there are no in-flight variants", async () => {
    mocked.listInFlight.mockResolvedValue({ items: [] });
    const { container } = renderCard();
    await waitFor(() => expect(mocked.listInFlight).toHaveBeenCalled());
    expect(container.querySelector("section")).toBeNull();
  });

  it("renders one entry per in-flight variant with a link to the parent", async () => {
    mocked.listInFlight.mockResolvedValue({
      items: [
        variant(),
        variant({
          variant_strategy_id: 4,
          parent_strategy_id: 3,
          parent_strategy_name: "Reversion",
        }),
      ],
    });
    renderCard();
    expect(await screen.findByText(/Active validations \(2\)/i)).toBeInTheDocument();
    const momentum = screen.getByText("Momentum").closest("a");
    expect(momentum).toHaveAttribute("href", "/strategies/1");
    const reversion = screen.getByText("Reversion").closest("a");
    expect(reversion).toHaveAttribute("href", "/strategies/3");
  });
});
