/**
 * OrdersTab — verifies the P4 §5 backend filter is what's actually called,
 * not just that the resulting list renders correctly. The old pull-500-and-
 * filter-client-side implementation would also render orders correctly; this
 * test is specifically about the API parameters.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { OrdersTab } from "../OrdersTab";
import { ordersApi } from "@/api/orders";

vi.mock("@/api/orders");

const mockedOrdersApi = vi.mocked(ordersApi, true);

describe("OrdersTab — P4 §5 server-side scoping", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedOrdersApi.list.mockResolvedValue({ items: [], count: 0 });
  });

  it("calls ordersApi.list with source_type='strategy' + source_id + bounded limit", async () => {
    render(<OrdersTab strategyId={42} />);

    await waitFor(() => expect(mockedOrdersApi.list).toHaveBeenCalled());

    const callArgs = mockedOrdersApi.list.mock.calls[0]?.[0];
    expect(callArgs?.source_type).toBe("strategy");
    expect(callArgs?.source_id).toBe("42");
    // Old impl pulled 500 unconditionally; we should be well under that.
    expect(callArgs?.limit ?? 100).toBeLessThanOrEqual(100);
  });

  it("never falls back to an unscoped list call", async () => {
    render(<OrdersTab strategyId={7} />);
    await waitFor(() => expect(mockedOrdersApi.list).toHaveBeenCalled());

    // Every call (initial render + any internal effect re-runs) must carry
    // the scoping filter. If a future refactor re-introduces a pull-all
    // path, this assertion catches it.
    for (const [args] of mockedOrdersApi.list.mock.calls) {
      expect(args?.source_type).toBe("strategy");
      expect(args?.source_id).toBe("7");
    }
  });
});
