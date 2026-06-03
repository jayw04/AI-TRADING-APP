/**
 * ReviewQueue page — renders sampled awaiting-review proposals, wires the
 * thumbs-up/down review actions, and removes an item after review. The API
 * module is mocked.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ReviewQueue from "../ReviewQueue";
import { proposalsApi, type Proposal } from "@/api/proposals";

vi.mock("@/api/proposals");

const mocked = vi.mocked(proposalsApi, true);

function proposal(over: Partial<Proposal> = {}): Proposal {
  return {
    id: 1,
    strategy_id: 1,
    user_id: 1,
    state: "ACCEPTED",
    proposal_payload: { confidence: "HIGH", summary: "Tune RSI", changes: [] },
    evidence_bundle: {},
    evaluation_results: {
      status: "complete",
      verdict: "above_baseline",
      human_review: { sampled_at: "2026-06-02T00:00:00Z", rating: null },
    },
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
        <ReviewQueue />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("ReviewQueue page", () => {
  it("renders sampled awaiting proposals", async () => {
    mocked.listAwaitingReview.mockResolvedValue({ items: [proposal()] });
    renderPage();
    expect(await screen.findByText("Tune RSI")).toBeInTheDocument();
  });

  it("shows a count in the header", async () => {
    mocked.listAwaitingReview.mockResolvedValue({
      items: [proposal({ id: 1 }), proposal({ id: 2 })],
    });
    renderPage();
    expect(await screen.findByText("Review Queue (2)")).toBeInTheDocument();
  });

  it("empty queue shows the all-caught-up message", async () => {
    mocked.listAwaitingReview.mockResolvedValue({ items: [] });
    renderPage();
    expect(await screen.findByText(/all caught up/i)).toBeInTheDocument();
  });

  it("thumbs-up button calls the API with the rating", async () => {
    mocked.listAwaitingReview.mockResolvedValue({ items: [proposal()] });
    mocked.review.mockResolvedValue(proposal());
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "👍 Useful" }));
    await waitFor(() =>
      expect(mocked.review).toHaveBeenCalledWith(1, "thumbs_up", undefined),
    );
  });

  it("thumbs-down with a reason calls the API with both", async () => {
    mocked.listAwaitingReview.mockResolvedValue({ items: [proposal()] });
    mocked.review.mockResolvedValue(proposal());
    renderPage();
    await screen.findByText("Tune RSI");
    fireEvent.change(screen.getByPlaceholderText(/optional reason/i), {
      target: { value: "no actual change" },
    });
    fireEvent.click(screen.getByRole("button", { name: /not useful/i }));
    await waitFor(() =>
      expect(mocked.review).toHaveBeenCalledWith(1, "thumbs_down", "no actual change"),
    );
  });

  it("removes the proposal from the queue after review", async () => {
    mocked.listAwaitingReview
      .mockResolvedValueOnce({ items: [proposal()] })
      .mockResolvedValue({ items: [] });
    mocked.review.mockResolvedValue(proposal());
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "👍 Useful" }));
    await waitFor(() => expect(screen.queryByText("Tune RSI")).not.toBeInTheDocument());
  });
});
