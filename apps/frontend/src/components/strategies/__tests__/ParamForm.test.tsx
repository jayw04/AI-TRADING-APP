import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ParamForm } from "../ParamForm";
import type { ParamsSchema } from "@/api/types";

const schema: ParamsSchema = {
  rsi_period: {
    type: "integer",
    min: 2,
    max: 100,
    default: 14,
    description: "Lookback bars",
  },
  entry_threshold: {
    type: "number",
    min: 0,
    max: 100,
    default: 30,
  },
  size_method: {
    type: "enum",
    choices: ["fixed_notional", "fixed_qty", "percent_equity"],
    default: "fixed_notional",
  },
  allow_short: {
    type: "boolean",
    default: false,
  },
};

describe("ParamForm", () => {
  it("renders one row per schema field with the description text", () => {
    render(
      <ParamForm schema={schema} initialValues={{}} onSubmit={vi.fn()} />,
    );
    expect(screen.getByText("rsi_period")).toBeInTheDocument();
    expect(screen.getByText("Lookback bars")).toBeInTheDocument();
    expect(screen.getByText("entry_threshold")).toBeInTheDocument();
    expect(screen.getByText("size_method")).toBeInTheDocument();
    expect(screen.getByText("allow_short")).toBeInTheDocument();
  });

  it("seeds inputs with initialValues, not schema defaults", () => {
    render(
      <ParamForm
        schema={schema}
        initialValues={{ rsi_period: 21, entry_threshold: 25 }}
        onSubmit={vi.fn()}
      />,
    );
    // 21 (from initialValues) — NOT 14 (schema default).
    expect((screen.getByDisplayValue("21") as HTMLInputElement).value).toBe("21");
    expect((screen.getByDisplayValue("25") as HTMLInputElement).value).toBe("25");
  });

  it("shows 'Unsaved changes' after editing a field", () => {
    render(
      <ParamForm
        schema={schema}
        initialValues={{ rsi_period: 14 }}
        onSubmit={vi.fn()}
      />,
    );
    const input = screen.getByDisplayValue("14") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "20" } });
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("blocks Save and shows validation error when value is above max", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <ParamForm
        schema={schema}
        initialValues={{ rsi_period: 14 }}
        onSubmit={onSubmit}
      />,
    );
    const input = screen.getByDisplayValue("14") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: /Save/ }));
    await waitFor(() =>
      expect(screen.getByText(/Must be ≤ 100/)).toBeInTheDocument(),
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("blocks Save with 'Must be one of' when enum value isn't in the choices", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <ParamForm
        schema={schema}
        initialValues={{
          rsi_period: 14,
          entry_threshold: 30,
          size_method: "garbage",
          allow_short: false,
        }}
        onSubmit={onSubmit}
      />,
    );
    // Mark the form dirty (otherwise the Save button stays disabled). The
    // invalid value is the *seeded* enum, not the field the user touched.
    fireEvent.change(screen.getByDisplayValue("14") as HTMLInputElement, {
      target: { value: "21" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save/ }));
    await waitFor(() =>
      expect(screen.getByText(/Must be one of/)).toBeInTheDocument(),
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("calls onSubmit with typed values when Save passes validation", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <ParamForm
        schema={schema}
        initialValues={{
          rsi_period: 14,
          entry_threshold: 30,
          size_method: "fixed_notional",
          allow_short: false,
        }}
        onSubmit={onSubmit}
      />,
    );
    const input = screen.getByDisplayValue("14") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "21" } });
    fireEvent.click(screen.getByRole("button", { name: /Save/ }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const submitted = onSubmit.mock.calls[0][0];
    expect(submitted.rsi_period).toBe(21);
    // Integer parsing — not a string.
    expect(typeof submitted.rsi_period).toBe("number");
  });

  it("Reset to defaults repopulates from schema defaults", () => {
    render(
      <ParamForm
        schema={schema}
        initialValues={{ rsi_period: 21, entry_threshold: 25 }}
        onSubmit={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Reset to defaults"));
    expect((screen.getByDisplayValue("14") as HTMLInputElement).value).toBe("14");
    expect((screen.getByDisplayValue("30") as HTMLInputElement).value).toBe("30");
  });
});
