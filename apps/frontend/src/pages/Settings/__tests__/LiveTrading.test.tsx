/**
 * P6b §4.5 (ADR 0015) — Settings → Live Trading master switch. Renders the
 * current state and runs the TOTP-gated enable flow. The API module is mocked.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import LiveTrading from "../LiveTrading";
import { liveAutodispatchApi } from "@/api/liveAutodispatch";

vi.mock("@/api/liveAutodispatch");

const mocked = vi.mocked(liveAutodispatchApi, true);

describe("LiveTrading (master switch)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.status.mockResolvedValue({ enabled: false });
    mocked.set.mockResolvedValue({ enabled: true });
  });

  it("renders the OFF state by default", async () => {
    render(<LiveTrading />);
    expect(await screen.findByText(/OFF — LIVE strategies do not auto-trade/i)).toBeTruthy();
  });

  it("runs the TOTP-gated enable flow", async () => {
    render(<LiveTrading />);
    fireEvent.click(await screen.findByRole("button", { name: /Enable live auto-dispatch/i }));
    // modal TOTP input
    const totp = await screen.findByPlaceholderText(/TOTP code/i);
    fireEvent.change(totp, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: /^Enable$/i }));
    await waitFor(() => expect(mocked.set).toHaveBeenCalledWith(true, "123456"));
  });

  it("disables Enable until a 6-digit TOTP is entered", async () => {
    render(<LiveTrading />);
    fireEvent.click(await screen.findByRole("button", { name: /Enable live auto-dispatch/i }));
    const confirm = screen.getByRole("button", { name: /^Enable$/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(await screen.findByPlaceholderText(/TOTP code/i), {
      target: { value: "12345" },
    });
    expect(confirm.disabled).toBe(true); // 5 digits still too short
  });
});
