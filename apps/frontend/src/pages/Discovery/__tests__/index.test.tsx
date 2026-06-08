/**
 * P8 §3 — Discovery view. Author a criterion → save → run → act on matches.
 * The scanner + trading-profile api modules are mocked.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Discovery from "../index";
import {
  scannerApi,
  type ScannerDefinition,
  type ScannerRun,
} from "@/api/scanner";
import { tradingProfileApi } from "@/api/tradingProfile";
import { strategyTemplatesApi } from "@/api/strategyTemplates";

vi.mock("@/api/scanner", () => ({
  scannerApi: {
    vocabulary: vi.fn(),
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    run: vi.fn(),
    listRuns: vi.fn(),
    getRun: vi.fn(),
  },
}));
vi.mock("@/api/tradingProfile", () => ({
  tradingProfileApi: { get: vi.fn(), update: vi.fn() },
}));
vi.mock("@/api/strategyTemplates", () => ({
  strategyTemplatesApi: { applyRange: vi.fn() },
}));

const mockedScanner = vi.mocked(scannerApi, true);
const mockedProfile = vi.mocked(tradingProfileApi, true);
const mockedTmpl = vi.mocked(strategyTemplatesApi, true);

const DEF: ScannerDefinition = {
  id: 1,
  name: "Oversold",
  criteria: "RSI14 < 35",
  universe_kind: "symbols",
  universe_symbols: ["AAPL", "MSFT"],
  timeframe: "1Day",
  scheduled: false,
  created_at: "2026-06-07T00:00:00Z",
  updated_at: "2026-06-07T00:00:00Z",
};

const RUN: ScannerRun = {
  id: 9,
  scanner_definition_id: 1,
  run_at: "2026-06-07T12:00:00Z",
  status: "ok",
  universe_size: 2,
  evaluated_count: 2,
  matched_count: 1,
  skipped_count: 0,
  error: null,
  criteria_snapshot: "RSI14 < 35",
  universe_kind: "symbols",
  timeframe: "1Day",
  matched: [{ symbol: "AAPL", values: { RSI14: 30.12 } }],
  skipped: [],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <Discovery />
    </MemoryRouter>,
  );
}

describe("Discovery", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedScanner.list.mockResolvedValue([DEF]);
    mockedScanner.vocabulary.mockResolvedValue({
      indicators: ["RSI14", "ATR14"],
      fields: ["close", "price"],
    });
    mockedScanner.listRuns.mockResolvedValue([]);
  });

  it("lists saved scans and shows the vocabulary chips", async () => {
    renderPage();
    expect(await screen.findByText("Oversold")).toBeTruthy();
    // chips for an indicator + a field render as insert buttons
    expect(await screen.findByRole("button", { name: "RSI14" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "close" })).toBeTruthy();
  });

  it("inserts a chip token into the criteria box", async () => {
    renderPage();
    await screen.findByRole("button", { name: "RSI14" });
    fireEvent.click(screen.getByRole("button", { name: "RSI14" }));
    const box = screen.getByPlaceholderText(/RSI14 < 35/i) as HTMLTextAreaElement;
    expect(box.value).toContain("RSI14");
  });

  it("creates a new scan from the form", async () => {
    mockedScanner.create.mockResolvedValue({ ...DEF, id: 2, name: "New" });
    renderPage();
    await screen.findByText("Oversold");
    fireEvent.click(screen.getByRole("button", { name: /New scan/i }));
    fireEvent.change(screen.getByPlaceholderText(/scan name/i), {
      target: { value: "New" },
    });
    fireEvent.change(screen.getByPlaceholderText(/RSI14 < 35/i), {
      target: { value: "close > 100" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Create scan/i }));
    await waitFor(() =>
      expect(mockedScanner.create).toHaveBeenCalledWith(
        expect.objectContaining({ name: "New", criteria: "close > 100" }),
      ),
    );
  });

  it("includes the scheduled flag when the checkbox is toggled", async () => {
    mockedScanner.create.mockResolvedValue({ ...DEF, id: 3, scheduled: true });
    renderPage();
    await screen.findByText("Oversold");
    fireEvent.click(screen.getByRole("button", { name: /New scan/i }));
    fireEvent.change(screen.getByPlaceholderText(/scan name/i), {
      target: { value: "Sched" },
    });
    fireEvent.change(screen.getByPlaceholderText(/RSI14 < 35/i), {
      target: { value: "close > 1" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /Create scan/i }));
    await waitFor(() =>
      expect(mockedScanner.create).toHaveBeenCalledWith(
        expect.objectContaining({ scheduled: true }),
      ),
    );
  });

  it("surfaces a 400 invalid-criterion detail", async () => {
    const { ApiError } = await import("@/api/client");
    mockedScanner.create.mockRejectedValue(
      new ApiError(400, { detail: "invalid criterion: unknown name: rsi" }),
    );
    renderPage();
    await screen.findByText("Oversold");
    fireEvent.click(screen.getByRole("button", { name: /New scan/i }));
    fireEvent.change(screen.getByPlaceholderText(/scan name/i), {
      target: { value: "X" },
    });
    fireEvent.change(screen.getByPlaceholderText(/RSI14 < 35/i), {
      target: { value: "rsi < 30" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Create scan/i }));
    expect(await screen.findByText(/unknown name: rsi/i)).toBeTruthy();
  });

  it("runs a selected scan and adds a match to the watchlist", async () => {
    mockedScanner.run.mockResolvedValue(RUN);
    mockedProfile.get.mockResolvedValue({
      user_id: 1,
      watchlist: { swing_candidates: [] },
      bias_criteria: {},
      bias_thresholds: {},
      session_preferences: {},
      risk_preferences: {},
      agent_envelope: {},
    });
    mockedProfile.update.mockResolvedValue({} as never);

    renderPage();
    fireEvent.click(await screen.findByText("Oversold"));
    fireEvent.click(await screen.findByRole("button", { name: /Run scan/i }));

    expect(await screen.findByText("AAPL")).toBeTruthy();
    expect(screen.getByText("30.12")).toBeTruthy(); // value formatted
    fireEvent.click(screen.getByRole("button", { name: /\+ watchlist/i }));
    await waitFor(() =>
      expect(mockedProfile.update).toHaveBeenCalledWith({
        watchlist: { swing_candidates: ["AAPL"] },
      }),
    );
  });

  it("applies the range template to a scan match and stays on the page", async () => {
    mockedScanner.run.mockResolvedValue(RUN);
    mockedTmpl.applyRange.mockResolvedValue({
      id: 7,
      name: "Range Trader AAPL",
      status: "idle",
      code_path: "templates/range_trader.py",
      authoring_method: "template",
      symbol: "AAPL",
      prefilled_from_range_insight: true,
    });

    renderPage();
    fireEvent.click(await screen.findByText("Oversold"));
    fireEvent.click(await screen.findByRole("button", { name: /Run scan/i }));
    await screen.findByText("AAPL");

    fireEvent.click(screen.getByRole("button", { name: /apply template/i }));
    await waitFor(() =>
      expect(mockedTmpl.applyRange).toHaveBeenCalledWith("AAPL"),
    );
    // stays on the page; a "view" link to the new strategy appears
    const view = await screen.findByRole("link", { name: /view/i });
    expect(view.getAttribute("href")).toBe("/strategies/7");
  });
});
