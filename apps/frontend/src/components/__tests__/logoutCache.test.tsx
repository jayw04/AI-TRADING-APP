import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Header from "@/components/Header";
import { MarketProvider } from "@/markets/MarketContext";
import { trackQueryClient } from "@/markets/queryClient";
import { MARKETS } from "@/markets/registry";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }))),
  );
});

describe("logout", () => {
  it("clears tracked caches and leaves the session", async () => {
    const client = new QueryClient();
    client.setQueryData(["book"], { cash: 1 });
    const release = trackQueryClient(client);
    const assign = vi.fn();
    vi.stubGlobal("location", { assign, href: "http://localhost/" });

    render(
      <MemoryRouter>
        <MarketProvider value={MARKETS.cn}>
          <Header />
        </MarketProvider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(client.getQueryCache().getAll()).toHaveLength(0));
    expect(assign).toHaveBeenCalledWith("/login");
    release();
  });
});
