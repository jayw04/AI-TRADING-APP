import { useEffect, useRef, useState } from "react";
import type { ParamFieldSpec, ParamsSchema } from "@/api/types";

interface Props {
  schema: ParamsSchema;
  initialValues: Record<string, unknown>;
  onSubmit: (values: Record<string, unknown>) => Promise<void>;
  disabled?: boolean;
}

export function ParamForm({ schema, initialValues, onSubmit, disabled }: Props) {
  const [values, setValues] = useState<Record<string, unknown>>(initialValues);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [dirty, setDirty] = useState(false);

  // A parent re-fetch (e.g. after a save round-trip) should re-seed the
  // form — but NOT mid-edit, or we'd wipe the user's input. The `dirty`
  // ref tracks the latest value without re-running the effect on every
  // edit.
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(() => {
    if (!dirtyRef.current) setValues(initialValues);
  }, [initialValues]);

  function updateField(name: string, value: unknown) {
    setValues((prev) => ({ ...prev, [name]: value }));
    setDirty(true);
  }

  function validateAll(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [name, spec] of Object.entries(schema)) {
      const err = validateField(spec, values[name]);
      if (err) out[name] = err;
    }
    return out;
  }

  async function handleSubmit() {
    const errs = validateAll();
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    setSubmitting(true);
    try {
      await onSubmit(values);
      setDirty(false);
      setErrors({});
    } catch {
      // ParamsTab re-throws on save failure so the form keeps "Unsaved
      // changes" visible. Swallow here — the parent already surfaced the
      // error message.
    } finally {
      setSubmitting(false);
    }
  }

  function handleReset() {
    const defaults: Record<string, unknown> = {};
    for (const [name, spec] of Object.entries(schema)) {
      if (spec.default !== undefined) defaults[name] = spec.default;
    }
    setValues({ ...initialValues, ...defaults });
    setDirty(true);
    setErrors({});
  }

  return (
    <div className="space-y-3">
      <div className="divide-y divide-gray-800">
        {Object.entries(schema).map(([name, spec]) => (
          <FieldRow
            key={name}
            name={name}
            spec={spec}
            value={values[name]}
            error={errors[name]}
            disabled={disabled || submitting}
            onChange={(v) => updateField(name, v)}
          />
        ))}
      </div>

      <div className="flex items-center justify-between border-t border-gray-800 pt-3">
        <button
          onClick={handleReset}
          disabled={disabled || submitting}
          className="text-xs text-gray-400 hover:text-gray-200 disabled:opacity-40"
        >
          Reset to defaults
        </button>
        <div className="flex items-center gap-2">
          {dirty && <span className="text-xs text-amber-400">Unsaved changes</span>}
          <button
            onClick={handleSubmit}
            disabled={disabled || submitting || !dirty}
            className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700"
          >
            {submitting ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function validateField(spec: ParamFieldSpec, value: unknown): string | null {
  if (value === undefined || value === null || value === "") {
    if (spec.default === undefined) return "Required";
    return null; // empty + has default → server uses default
  }
  if (spec.type === "integer" || spec.type === "number") {
    const n = Number(value);
    if (Number.isNaN(n)) return "Must be a number";
    if (spec.type === "integer" && !Number.isInteger(n)) return "Must be an integer";
    if (spec.min !== undefined && n < spec.min) return `Must be ≥ ${spec.min}`;
    if (spec.max !== undefined && n > spec.max) return `Must be ≤ ${spec.max}`;
  }
  if (spec.type === "string") {
    const s = String(value);
    if (spec.max_length !== undefined && s.length > spec.max_length) {
      return `Max length ${spec.max_length}`;
    }
  }
  if (spec.type === "enum") {
    if (!spec.choices?.includes(String(value))) {
      return `Must be one of: ${spec.choices?.join(", ")}`;
    }
  }
  return null;
}

function FieldRow({
  name,
  spec,
  value,
  error,
  disabled,
  onChange,
}: {
  name: string;
  spec: ParamFieldSpec;
  value: unknown;
  error?: string;
  disabled?: boolean;
  onChange: (v: unknown) => void;
}) {
  return (
    <div className="grid grid-cols-12 gap-3 py-2">
      <div className="col-span-4">
        <div className="font-mono text-sm text-white">{name}</div>
        {spec.description && (
          <div className="mt-0.5 text-xs text-gray-500">{spec.description}</div>
        )}
      </div>
      <div className="col-span-8">
        {renderInput(spec, value, disabled, onChange)}
        {error && <div className="mt-1 text-xs text-rose-400">{error}</div>}
      </div>
    </div>
  );
}

function renderInput(
  spec: ParamFieldSpec,
  value: unknown,
  disabled: boolean | undefined,
  onChange: (v: unknown) => void,
) {
  const base =
    "w-full rounded bg-gray-800 px-2 py-1 text-sm text-white disabled:opacity-50";

  if (spec.type === "integer" || spec.type === "number") {
    return (
      <input
        type="number"
        step={spec.step ?? (spec.type === "integer" ? 1 : "any")}
        min={spec.min}
        max={spec.max}
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "") {
            onChange(undefined);
            return;
          }
          onChange(
            spec.type === "integer" ? parseInt(raw, 10) : parseFloat(raw),
          );
        }}
        disabled={disabled}
        className={base}
      />
    );
  }

  if (spec.type === "boolean") {
    return (
      <input
        type="checkbox"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="h-4 w-4"
      />
    );
  }

  if (spec.type === "enum" && spec.choices) {
    return (
      <select
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={base}
      >
        <option value="" disabled>
          — select —
        </option>
        {spec.choices.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    );
  }

  if (spec.type === "string") {
    return (
      <input
        type="text"
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
        maxLength={spec.max_length}
        disabled={disabled}
        className={base}
      />
    );
  }

  // Unknown type — fallback to JSON-string editing so the row stays usable.
  return (
    <input
      type="text"
      value={value === undefined ? "" : JSON.stringify(value)}
      onChange={(e) => {
        try {
          onChange(JSON.parse(e.target.value));
        } catch {
          onChange(e.target.value);
        }
      }}
      disabled={disabled}
      className={base}
    />
  );
}
