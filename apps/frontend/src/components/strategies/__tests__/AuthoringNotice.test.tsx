/**
 * P7 §7 — AuthoringNotice. Nothing for manual strategies; "AI-authored" for nl_*;
 * an amber warning when out_of_sync. The API module is mocked.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AuthoringNotice } from "../AuthoringNotice";
import { strategyAuthoringApi } from "@/api/strategyAuthoring";

vi.mock("@/api/strategyAuthoring");
const mocked = vi.mocked(strategyAuthoringApi, true);

describe("AuthoringNotice", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders nothing for a manual strategy", async () => {
    mocked.status.mockResolvedValue({
      strategy_id: 1, authoring_method: "manual", revision_count: 0, out_of_sync: false,
    });
    const { container } = render(<AuthoringNotice strategyId={1} />);
    await waitFor(() => expect(mocked.status).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("shows AI-authored without a warning when in sync", async () => {
    mocked.status.mockResolvedValue({
      strategy_id: 1, authoring_method: "nl_generation", revision_count: 1, out_of_sync: false,
    });
    render(<AuthoringNotice strategyId={1} />);
    expect(await screen.findByText(/AI-authored/i)).toBeTruthy();
    expect(screen.queryByText(/manually edited/i)).toBeNull();
  });

  it("warns when the code was manually edited", async () => {
    mocked.status.mockResolvedValue({
      strategy_id: 1, authoring_method: "nl_refinement", revision_count: 3, out_of_sync: true,
    });
    render(<AuthoringNotice strategyId={1} />);
    expect(await screen.findByText(/manually edited since it was AI-authored/i)).toBeTruthy();
  });
});
