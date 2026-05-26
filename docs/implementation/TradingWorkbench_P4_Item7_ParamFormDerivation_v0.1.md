# P4 Item 7 — Parameter Form Derivation from `params_schema`

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-23 |
| Phase | **P4 — Polish & Extend**, Item §7 |
| Predecessor | *TradingWorkbench_P4_Item6_BacktestCharting_v0.1.md* (tag `p4-backtest-charting-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Introduce an optional `params_schema: ClassVar[dict]` on `Strategy` subclasses. The `StrategyLoader` reads it during registration; the backend exposes it on `StrategyResponse.params_schema`. The frontend renders a typed form (number / string / select / boolean) when the schema is present; falls back to the existing JSON textarea otherwise. Update the reference RSI strategy to declare its schema. Single PR — backend + frontend together because the surface is small per side. |
| Estimated wall time | 3 hours |
| Stopping point | `git tag p4-param-form-complete` |
| Out of scope | Validators beyond min/max/enum. Custom widgets (date pickers, color pickers, etc.). Cross-field constraints ("exit_threshold must be > entry_threshold"). Nested object/array params (treat as JSON-textarea fallback). Live preview ("if I change RSI period from 14 to 21, here's how the last 100 days would re-backtest"). |

---

## Session Goal

After this session:
- A Strategy subclass can optionally declare:
  ```python
  class RsiMeanReversion(Strategy):
      params_schema: ClassVar[dict] = {
          "rsi_period": {"type": "integer", "min": 2, "max": 100, "default": 14, "description": "Lookback bars for RSI"},
          "entry_threshold": {"type": "number", "min": 0, "max": 100, "default": 30, "description": "Buy below this RSI"},
          # ... more fields ...
      }
  ```
- The StrategyLoader reads `params_schema` during `load(code_path)`. If the class has the attribute, the schema is captured; if not, schema is `None`.
- `Strategy` model gains an in-memory `params_schema: dict | None` populated at registration time. **Not persisted** to the DB — it's derived from code; persisting would create stale-cache bugs when code is edited (P4 §4 hot-reload makes this concrete).
- `StrategyResponse` Pydantic schema gains an optional `params_schema` field, populated from the engine's in-memory state on each detail-page fetch.
- Frontend Strategy detail Params tab: when `params_schema` is present, render a typed form with input controls and validation. When `params_schema` is null, render the existing JSON textarea. Either way, "Save" calls the existing `PUT /strategies/{id}` endpoint with `params` as a dict.
- The reference RSI strategy gets a `params_schema` declaration so the form is demonstrable on day one.
- 8 backend tests + 5 frontend tests cover the new shape.

What does NOT happen this session:
- No persistence of the schema in the DB. The schema lives in code; the engine pulls it from the loaded class. A reload picks up schema changes for free.
- No nested objects. `params_schema` is flat: `{field_name: spec}`. Nested fields would invite complexity (recursive form rendering, dotted-path updates) for a tiny payoff at MVP scale.
- No cross-field validators. "exit_threshold > entry_threshold" is the strategy's `on_init` job, not the schema's. The form does per-field validation only.
- No params change history. The existing `audit_log` already captures `STRATEGY_UPDATED` events with the full new params dict; that's the history.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p4-backtest-charting-complete

./scripts/dev.sh &
sleep 30

# Reference RSI strategy is registered (otherwise demo nothing)
SID=$(curl -s "http://127.0.0.1:8000/api/v1/strategies?limit=1" | jq -r '.items[0].id')
curl -fs "http://127.0.0.1:8000/api/v1/strategies/${SID}" | jq '.params'

# Strategy framework exposes Strategy base class
docker compose exec backend uv run python -c "
from app.strategies.base import Strategy
print(hasattr(Strategy, 'params_schema'))   # may be False today
"

docker compose down
git checkout -b feat/p4-param-form
```

- [ ] On `main`, at `p4-backtest-charting-complete`.
- [ ] Reference RSI strategy exists.

---

## §7.1 — Schema Spec

Define the wire format. A `params_schema` entry is `{type, default, ...}` with field-specific keys:

| Type | Keys | Frontend renders |
|---|---|---|
| `"integer"` | `min`, `max`, `step`, `default`, `description` | `<input type="number" step="1">` |
| `"number"` | `min`, `max`, `step`, `default`, `description` | `<input type="number">` |
| `"string"` | `max_length`, `default`, `description` | `<input type="text">` |
| `"boolean"` | `default`, `description` | `<input type="checkbox">` |
| `"enum"` | `choices` (list[str]), `default`, `description` | `<select>` |

Examples:

```python
params_schema = {
    "rsi_period": {
        "type": "integer", "min": 2, "max": 100, "default": 14,
        "description": "Lookback bars for RSI",
    },
    "entry_threshold": {
        "type": "number", "min": 0, "max": 100, "default": 30,
        "description": "Buy when RSI dips below this",
    },
    "exit_threshold": {
        "type": "number", "min": 0, "max": 100, "default": 55,
        "description": "Sell when RSI crosses above this",
    },
    "atr_multiple_for_stop": {
        "type": "number", "min": 0.1, "max": 10, "default": 2.0, "step": 0.1,
        "description": "ATR multiple for hard stop loss",
    },
    "size_method": {
        "type": "enum", "choices": ["fixed_notional", "fixed_qty", "percent_equity"],
        "default": "fixed_notional", "description": "Position sizing approach",
    },
    "size_value": {
        "type": "number", "min": 0, "default": 1000,
        "description": "Notional ($), qty, or percent (per size_method)",
    },
    "allow_short": {
        "type": "boolean", "default": False,
        "description": "Permit short entries (requires risk_limits.allow_short)",
    },
}
```

> Unknown fields in a spec are tolerated (forward-compat). Unknown `type` values fall back to JSON textarea on the frontend.

- [ ] Spec documented (this section).

---

## §7.2 — Backend: `Strategy` Base Class

Edit `apps/backend/app/strategies/base.py`. Add a class-level placeholder:

```python
from typing import ClassVar


class Strategy:
    """Base for all Python strategies. ...existing docstring..."""

    # Optional schema describing each parameter for UI form derivation.
    # Subclasses override; if absent, the frontend falls back to a JSON
    # textarea. None means 'no schema declared'.
    params_schema: ClassVar[dict | None] = None

    # ... existing fields/methods unchanged ...
```

Two things to be careful about:

1. **`ClassVar[dict | None]`** — Pydantic / dataclasses won't treat this as a model field if Strategy is ever wrapped that way.
2. **Default of `None`** rather than empty dict, so callers can distinguish "no schema declared" from "empty schema."

- [ ] `params_schema` declared on the base class with `None` default.

---

## §7.3 — Backend: Loader Reads `params_schema`

Edit `apps/backend/app/strategies/loader.py`. After the loader imports the module + finds the `Strategy` subclass, capture its `params_schema` and stash it on the returned class. The simplest path: the engine already keeps a `dict[strategy_id -> strategy_class]` map; access `cls.params_schema` directly when serializing.

If the loader exposes a `LoadedStrategy` wrapper, add the schema to it:

```python
@dataclass
class LoadedStrategy:
    strategy_class: type[Strategy]
    code_path: str
    # ... existing fields ...

    @property
    def params_schema(self) -> dict | None:
        """The class-declared params_schema, if any. Read fresh from the
        class object so a hot-reload (P4 §4) sees the new schema without
        needing to re-wrap."""
        return getattr(self.strategy_class, "params_schema", None)
```

If the loader doesn't have a wrapper, no change needed — the engine can just read `strategy_class.params_schema` directly later.

- [ ] Loader exposes (or doesn't need to expose) `params_schema`.

---

## §7.4 — Backend: Engine Tracks Schema, Exposes via Response

Edit `apps/backend/app/strategies/engine.py`. The `StrategyEngine` already keeps the loaded class per strategy_id. Add a helper:

```python
def get_params_schema(self, strategy_id: int) -> dict | None:
    """Return the in-memory params_schema for a registered strategy.
    Returns None if the strategy isn't currently registered OR if the
    strategy class doesn't declare a schema."""
    rec = self._registry.get(strategy_id)
    if rec is None:
        return None
    return getattr(rec.strategy_class, "params_schema", None)
```

> The schema is only available for **currently registered** strategies (active or idle-but-loaded). Strategies in ERROR state from a failed import won't have a schema until they're reloaded. The frontend handles `params_schema=null` gracefully — it just shows the JSON textarea, which is the right fallback for "we couldn't load the code."

- [ ] Engine exposes `get_params_schema(strategy_id)`.

Now edit `apps/backend/app/api/v1/schemas/strategies.py`. Extend the response:

```python
class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    # ... existing fields ...
    has_pending_reload: bool = False
    pending_reload_at: Optional[datetime] = None
    params_schema: Optional[dict[str, Any]] = None     # NEW
    created_at: datetime
    updated_at: datetime
```

Edit the handler that returns `StrategyResponse`. Find `GET /strategies/{id}` in `apps/backend/app/api/v1/strategies.py`. After building the base response from the ORM row, look up the schema from the engine and inject it:

```python
@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    engine = _get_engine(request)
    schema = engine.get_params_schema(strategy_id) if engine else None

    resp = StrategyResponse.model_validate(row, from_attributes=True)
    # Pydantic v2: assignment on a constructed model works via model_copy
    return resp.model_copy(update={"params_schema": schema})
```

And the list endpoint `GET /strategies` — should it also inject schema? On the list page we don't render forms, so leaving it out keeps the response small. Skip there; only inject on the detail endpoint.

- [ ] `StrategyResponse` has the new optional field.
- [ ] Detail endpoint injects schema; list endpoint doesn't.

---

## §7.5 — Backend: Update Reference RSI Strategy

Edit `strategies_user/examples/rsi_meanreversion.py`. At the class body, before `on_init`:

```python
from typing import ClassVar


class RsiMeanReversion(Strategy):
    """RSI mean-reversion: long when oversold, exit at neutral or stop loss."""

    params_schema: ClassVar[dict] = {
        "rsi_period": {
            "type": "integer", "min": 2, "max": 100, "default": 14,
            "description": "Lookback bars for RSI",
        },
        "entry_threshold": {
            "type": "number", "min": 0, "max": 100, "default": 30,
            "description": "Buy when RSI crosses below this",
        },
        "exit_threshold": {
            "type": "number", "min": 0, "max": 100, "default": 55,
            "description": "Sell when RSI crosses above this",
        },
        "atr_period": {
            "type": "integer", "min": 2, "max": 100, "default": 14,
            "description": "Lookback bars for ATR (stop-loss sizing)",
        },
        "atr_multiple_for_stop": {
            "type": "number", "min": 0.1, "max": 10, "default": 2.0, "step": 0.1,
            "description": "ATR multiple for hard stop loss distance",
        },
        "size_notional": {
            "type": "number", "min": 0, "default": 1000,
            "description": "Notional dollars per entry",
        },
    }

    # ... rest of class unchanged ...
```

> Don't rename or remove existing keys. The strategy's `on_init` still reads them via `self.params.get("rsi_period", 14)`. The schema's `default` values *do not* automatically populate `params`; they're for the form's "reset to defaults" affordance. The DB-persisted `params_json` is still the source of truth at runtime.

- [ ] RSI strategy declares its schema.

---

## §7.6 — Backend Tests

Append to `apps/backend/tests/strategies/test_loader.py`:

```python
"""P4 §7: params_schema is read from the strategy class."""
from typing import ClassVar

import pytest

from app.strategies.base import Strategy
from app.strategies.loader import StrategyLoader


# A test strategy with a schema, defined inline to avoid touching strategies_user/
SCHEMA_FIXTURE_CODE = '''
from typing import ClassVar
from app.strategies.base import Strategy


class TestStratWithSchema(Strategy):
    params_schema: ClassVar[dict] = {
        "lookback": {"type": "integer", "min": 1, "max": 200, "default": 14},
        "threshold": {"type": "number", "min": 0, "max": 1, "default": 0.5},
    }

    async def on_init(self, ctx):
        pass

    async def on_bar(self, ctx):
        pass
'''


SCHEMA_FIXTURE_CODE_NO_SCHEMA = '''
from app.strategies.base import Strategy


class TestStratNoSchema(Strategy):
    async def on_init(self, ctx):
        pass

    async def on_bar(self, ctx):
        pass
'''


@pytest.mark.asyncio
async def test_loader_reads_schema_from_class(tmp_path):
    p = tmp_path / "with_schema.py"
    p.write_text(SCHEMA_FIXTURE_CODE)
    loader = StrategyLoader(tmp_path)
    cls = loader.load("with_schema.py")
    assert hasattr(cls, "params_schema")
    assert cls.params_schema is not None
    assert cls.params_schema["lookback"]["type"] == "integer"
    assert cls.params_schema["threshold"]["default"] == 0.5


@pytest.mark.asyncio
async def test_loader_schema_is_none_when_undeclared(tmp_path):
    p = tmp_path / "no_schema.py"
    p.write_text(SCHEMA_FIXTURE_CODE_NO_SCHEMA)
    loader = StrategyLoader(tmp_path)
    cls = loader.load("no_schema.py")
    # The base class default is None; subclass didn't override
    assert getattr(cls, "params_schema", None) is None


def test_base_strategy_has_params_schema_attribute():
    assert hasattr(Strategy, "params_schema")
    assert Strategy.params_schema is None
```

Append to `apps/backend/tests/api/test_strategies_endpoint.py`:

```python
@pytest.mark.asyncio
async def test_detail_returns_schema_when_registered(client, session_factory):
    """If the engine has a schema for the strategy, detail returns it."""
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="with-schema", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, has_pending_reload=False,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    # Stub the engine to return a schema
    fake_schema = {
        "rsi_period": {"type": "integer", "min": 2, "max": 100, "default": 14},
    }
    client._transport.app.state.strategy_engine.get_params_schema = (
        lambda strategy_id: fake_schema if strategy_id == sid else None
    )

    resp = await client.get(f"/api/v1/strategies/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["params_schema"] is not None
    assert body["params_schema"]["rsi_period"]["default"] == 14


@pytest.mark.asyncio
async def test_detail_returns_null_schema_when_engine_has_none(client, session_factory):
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="no-schema", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="user_strategies/my.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, has_pending_reload=False,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    client._transport.app.state.strategy_engine.get_params_schema = lambda strategy_id: None

    resp = await client.get(f"/api/v1/strategies/{sid}")
    assert resp.status_code == 200
    assert resp.json()["params_schema"] is None


@pytest.mark.asyncio
async def test_list_endpoint_does_not_include_schema(client, session_factory):
    """The list endpoint omits schema to keep responses small."""
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="any", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="examples/rsi.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, has_pending_reload=False,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()

    client._transport.app.state.strategy_engine.get_params_schema = lambda strategy_id: {
        "x": {"type": "integer", "default": 1}
    }

    resp = await client.get("/api/v1/strategies")
    body = resp.json()
    # The list-item shape should NOT have params_schema populated
    for item in body["items"]:
        # Either absent or null — both acceptable
        assert item.get("params_schema") is None


@pytest.mark.asyncio
async def test_update_with_form_field_only(client, session_factory):
    """A PUT that updates just one field via the dict path still works.
    (The form sends the full dict; we don't change PUT semantics in this PR.)"""
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="upd", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi.py",
            params_json={"rsi_period": 14, "entry_threshold": 30},
            symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, has_pending_reload=False,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    resp = await client.put(f"/api/v1/strategies/{sid}", json={
        "params": {"rsi_period": 21, "entry_threshold": 25},
    })
    assert resp.status_code == 200
    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
    assert row.params_json["rsi_period"] == 21
    assert row.params_json["entry_threshold"] == 25
```

Run:

```bash
cd apps/backend
uv run pytest tests/strategies/test_loader.py tests/api/test_strategies_endpoint.py -v
uv run pytest -q
cd ../..
```

- [ ] All 7 new backend tests pass (3 loader + 4 endpoint).
- [ ] Full backend suite green; P3 + P4 invariant checks still pass.

---

## §7.7 — Frontend: Type Definitions

Extend `apps/frontend/src/api/types.ts`:

```typescript
// ===== Params schema =====

export type ParamFieldType = "integer" | "number" | "string" | "boolean" | "enum";

export interface ParamFieldSpec {
  type: ParamFieldType;
  default?: number | string | boolean;
  description?: string;
  min?: number;
  max?: number;
  step?: number;
  max_length?: number;
  choices?: string[];        // for enum
}

export type ParamsSchema = Record<string, ParamFieldSpec>;

// Extend the Strategy interface:
export interface Strategy {
  // ... existing fields ...
  params_schema: ParamsSchema | null;
}
```

- [ ] Types extended.

---

## §7.8 — Frontend: `ParamForm` Component

Create `apps/frontend/src/components/strategies/ParamForm.tsx`:

```tsx
import { useEffect, useState } from "react";
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

  // If initialValues change (e.g. after a save round-trip + parent re-fetch),
  // re-seed the form UNLESS the user has unsaved edits.
  useEffect(() => {
    if (!dirty) setValues(initialValues);
    // Intentional dep: only re-seed when the parent provides a new object
    // identity; mid-edit re-seeds would wipe user input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialValues]);

  function updateField(name: string, value: unknown) {
    setValues((prev) => ({ ...prev, [name]: value }));
    setDirty(true);
  }

  function validateAll(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [name, spec] of Object.entries(schema)) {
      const value = values[name];
      const err = validateField(spec, value);
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
          {dirty && (
            <span className="text-xs text-amber-400">Unsaved changes</span>
          )}
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
    return null;     // empty + has default → server uses default
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
    if (!spec.choices?.includes(String(value))) return `Must be one of: ${spec.choices?.join(", ")}`;
  }
  return null;
}


function FieldRow({
  name, spec, value, error, disabled, onChange,
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
        {renderInput(name, spec, value, disabled, onChange)}
        {error && <div className="mt-1 text-xs text-rose-400">{error}</div>}
      </div>
    </div>
  );
}


function renderInput(
  name: string,
  spec: ParamFieldSpec,
  value: unknown,
  disabled: boolean | undefined,
  onChange: (v: unknown) => void,
) {
  const base = "w-full rounded bg-gray-800 px-2 py-1 text-sm text-white disabled:opacity-50";

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
          if (raw === "") { onChange(undefined); return; }
          onChange(spec.type === "integer" ? parseInt(raw, 10) : parseFloat(raw));
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
        <option value="" disabled>— select —</option>
        {spec.choices.map((c) => <option key={c} value={c}>{c}</option>)}
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

  // Unknown type — fallback to JSON-string editing
  return (
    <input
      type="text"
      value={value === undefined ? "" : JSON.stringify(value)}
      onChange={(e) => {
        try { onChange(JSON.parse(e.target.value)); }
        catch { onChange(e.target.value); }
      }}
      disabled={disabled}
      className={base}
    />
  );
}
```

- [ ] `ParamForm.tsx` created.

---

## §7.9 — Frontend: Wire into Params Tab

The Strategy detail Params tab from P2 Session 5 currently renders a JSON textarea. Replace it with logic that picks `ParamForm` OR the textarea based on `strategy.params_schema`.

Edit `apps/frontend/src/pages/Strategies/tabs/ParamsTab.tsx` (create if it lives inline today; the file existed in P2 Session 5):

```tsx
import { useState } from "react";
import type { Strategy } from "@/api/types";
import { strategiesApi } from "@/api/strategies";
import { ApiError } from "@/api/client";
import { ParamForm } from "@/components/strategies/ParamForm";


interface Props {
  strategy: Strategy;
  onUpdated: () => void;
}


export function ParamsTab({ strategy, onUpdated }: Props) {
  const [error, setError] = useState<string | null>(null);

  // The Pydantic field name is `params_json` on the ORM but the API returns
  // `params` via the Field alias. The frontend Strategy type uses `params`.
  const initialValues = strategy.params || {};

  async function handleSave(values: Record<string, unknown>) {
    setError(null);
    try {
      await strategiesApi.update(strategy.id, { params: values });
      onUpdated();
    } catch (e) {
      if (e instanceof ApiError) setError(e.detail);
      else setError(String(e));
      throw e;     // re-throw so ParamForm keeps "Unsaved changes" state
    }
  }

  if (strategy.params_schema) {
    return (
      <div className="space-y-2">
        <div className="text-sm text-gray-400">
          Edit parameters using the typed form below. Changes apply on Save.
          Restart the strategy if it's running.
        </div>
        {error && (
          <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
            {error}
          </div>
        )}
        <ParamForm
          schema={strategy.params_schema}
          initialValues={initialValues}
          onSubmit={handleSave}
        />
      </div>
    );
  }

  // Fallback: JSON textarea (the P2 Session 5 implementation)
  return <ParamsJsonTextareaFallback strategy={strategy} onUpdated={onUpdated} />;
}


function ParamsJsonTextareaFallback({ strategy, onUpdated }: Props) {
  const [text, setText] = useState(JSON.stringify(strategy.params, null, 2));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = text.trim() ? JSON.parse(text) : {};
    } catch (e) {
      setError(`Not valid JSON: ${e}`);
      return;
    }
    setSaving(true);
    try {
      await strategiesApi.update(strategy.id, { params: parsed });
      onUpdated();
    } catch (e) {
      if (e instanceof ApiError) setError(e.detail);
      else setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="text-sm text-gray-400">
        No schema declared on this strategy. Edit parameters as raw JSON.
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={12}
        className="w-full rounded bg-gray-800 p-2 font-mono text-xs text-white"
      />
      {error && (
        <div className="rounded border border-red-700 bg-red-900/40 p-2 text-sm text-red-200">
          {error}
        </div>
      )}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
```

> The `throw e;` after the catch in `handleSave` is intentional. `ParamForm.handleSubmit` only resets the `dirty` flag if `onSubmit` resolves cleanly. By re-throwing on failure we keep the form's "Unsaved changes" state — the user sees their edits are still there.

- [ ] `ParamsTab` chooses form vs textarea based on `strategy.params_schema`.

---

## §7.10 — Frontend Tests

Create `apps/frontend/src/components/strategies/__tests__/ParamForm.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ParamForm } from "../ParamForm";
import type { ParamsSchema } from "@/api/types";


const schema: ParamsSchema = {
  rsi_period: {
    type: "integer", min: 2, max: 100, default: 14,
    description: "Lookback bars",
  },
  entry_threshold: {
    type: "number", min: 0, max: 100, default: 30,
  },
  size_method: {
    type: "enum", choices: ["fixed_notional", "fixed_qty", "percent_equity"],
    default: "fixed_notional",
  },
  allow_short: {
    type: "boolean", default: false,
  },
};


describe("ParamForm", () => {
  it("renders one row per field with the description", () => {
    render(<ParamForm schema={schema} initialValues={{}} onSubmit={vi.fn()} />);
    expect(screen.getByText("rsi_period")).toBeInTheDocument();
    expect(screen.getByText("Lookback bars")).toBeInTheDocument();
    expect(screen.getByText("entry_threshold")).toBeInTheDocument();
    expect(screen.getByText("size_method")).toBeInTheDocument();
    expect(screen.getByText("allow_short")).toBeInTheDocument();
  });

  it("seeds inputs with initialValues", () => {
    render(<ParamForm
      schema={schema}
      initialValues={{ rsi_period: 21, allow_short: true }}
      onSubmit={vi.fn()}
    />);
    const rsi = screen.getByDisplayValue("21") as HTMLInputElement;
    expect(rsi.value).toBe("21");
    const checkbox = rsi.parentElement?.parentElement?.parentElement
      ?.querySelector('input[type="checkbox"]') as HTMLInputElement | null;
    // Loose check: there's at least one checked checkbox in the form
    const allChecks = document.querySelectorAll('input[type="checkbox"]');
    const checkedAny = Array.from(allChecks).some((el) => (el as HTMLInputElement).checked);
    expect(checkedAny).toBe(true);
  });

  it("shows 'Unsaved changes' after editing a field", () => {
    render(<ParamForm schema={schema} initialValues={{ rsi_period: 14 }} onSubmit={vi.fn()} />);
    const rsi = screen.getByDisplayValue("14") as HTMLInputElement;
    fireEvent.change(rsi, { target: { value: "20" } });
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("rejects values outside min/max", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ParamForm
      schema={schema}
      initialValues={{ rsi_period: 14 }}
      onSubmit={onSubmit}
    />);
    const rsi = screen.getByDisplayValue("14") as HTMLInputElement;
    fireEvent.change(rsi, { target: { value: "200" } });   // above max=100
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(screen.getByText(/Must be ≤ 100/)).toBeInTheDocument());
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("calls onSubmit with the typed values on Save", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ParamForm
      schema={schema}
      initialValues={{ rsi_period: 14, entry_threshold: 30,
                       size_method: "fixed_notional", allow_short: false }}
      onSubmit={onSubmit}
    />);
    const rsi = screen.getByDisplayValue("14") as HTMLInputElement;
    fireEvent.change(rsi, { target: { value: "21" } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const submitted = onSubmit.mock.calls[0][0];
    expect(submitted.rsi_period).toBe(21);
  });

  it("Reset to defaults populates from schema defaults", () => {
    render(<ParamForm
      schema={schema}
      initialValues={{ rsi_period: 21, entry_threshold: 25 }}
      onSubmit={vi.fn()}
    />);
    fireEvent.click(screen.getByText("Reset to defaults"));
    // rsi_period should now be 14 (the default)
    expect((screen.getByDisplayValue("14") as HTMLInputElement).value).toBe("14");
    expect((screen.getByDisplayValue("30") as HTMLInputElement).value).toBe("30");
  });
});
```

Append a small case to `apps/frontend/src/pages/Strategies/__tests__/StrategyDetailPage.test.tsx`:

```tsx
describe("StrategyDetailPage Params tab — P4 §7 form vs textarea", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(strategiesApi.listRuns).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(strategiesApi.listSignals).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(strategiesApi.listBacktests).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(signalsApi.list).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(ordersApi.list).mockResolvedValue({ items: [], count: 0 });
  });

  it("renders ParamForm when strategy.params_schema is present", async () => {
    vi.mocked(strategiesApi.get).mockResolvedValue({
      id: 1, name: "rsi", version: "0.1.0",
      type: "python", status: "paper",
      code_path: "examples/rsi.py",
      params: { rsi_period: 14 },
      symbols: ["AAPL"], schedule: "*/1 * * * *",
      risk_limits_id: null, error_text: null,
      has_pending_reload: false, pending_reload_at: null,
      params_schema: {
        rsi_period: { type: "integer", min: 2, max: 100, default: 14, description: "Lookback" },
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as any);

    render(
      <MemoryRouter initialEntries={["/strategies/1"]}>
        <Routes>
          <Route path="/strategies/:id" element={<StrategyDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText("Params"));
    expect(await screen.findByText("rsi_period")).toBeInTheDocument();
    expect(screen.getByText("Lookback")).toBeInTheDocument();
    // The fallback textarea label should NOT appear
    expect(screen.queryByText(/raw JSON/)).not.toBeInTheDocument();
  });

  it("renders the JSON textarea fallback when params_schema is null", async () => {
    vi.mocked(strategiesApi.get).mockResolvedValue({
      id: 1, name: "no-schema", version: "0.1.0",
      type: "python", status: "paper",
      code_path: "user_strategies/my.py",
      params: { foo: 1 },
      symbols: ["AAPL"], schedule: "*/1 * * * *",
      risk_limits_id: null, error_text: null,
      has_pending_reload: false, pending_reload_at: null,
      params_schema: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as any);

    render(
      <MemoryRouter initialEntries={["/strategies/1"]}>
        <Routes>
          <Route path="/strategies/:id" element={<StrategyDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText("Params"));
    expect(await screen.findByText(/raw JSON/)).toBeInTheDocument();
  });
});
```

Run:

```bash
cd apps/frontend
pnpm test --run
cd ../..
```

- [ ] 6 ParamForm tests + 2 detail-page tests pass.
- [ ] Existing tests still green.

---

## §7.11 — Manual Smoke

```bash
./scripts/dev.sh &
sleep 30

# Reload the reference RSI strategy so the engine picks up the new params_schema
SID=$(curl -s "http://127.0.0.1:8000/api/v1/strategies?name=rsi" | jq -r '.items[0].id')
curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${SID}/reload" | jq '.action'

# Detail endpoint returns the schema
curl -s "http://127.0.0.1:8000/api/v1/strategies/${SID}" \
  | jq '.params_schema | keys'
# Expect: ["atr_multiple_for_stop", "atr_period", "entry_threshold", "exit_threshold", "rsi_period", "size_notional"]

# A user strategy without a schema returns null
USER_SID=$(curl -s "http://127.0.0.1:8000/api/v1/strategies" | jq -r '.items[] | select(.code_path | startswith("examples/") | not) | .id' | head -1)
if [ -n "$USER_SID" ]; then
  curl -s "http://127.0.0.1:8000/api/v1/strategies/${USER_SID}" \
    | jq '.params_schema'
  # Expect: null (if the strategy didn't declare one)
fi

# Open http://localhost:5173/strategies/${SID} → Params tab.
# The typed form should render with six rows.
# Edit rsi_period from 14 to 21 → "Unsaved changes" appears → Save → toast or refresh
# Edit again with rsi_period = 200 (above max) → "Must be ≤ 100" error → Save disabled.
# Click "Reset to defaults" → values revert.

# A user strategy without params_schema should show the JSON textarea fallback.

# Test the round-trip via API
curl -s -X PUT "http://127.0.0.1:8000/api/v1/strategies/${SID}" \
  -H "Content-Type: application/json" \
  -d '{"params": {"rsi_period": 21, "entry_threshold": 25, "exit_threshold": 55, "atr_period": 14, "atr_multiple_for_stop": 2.0, "size_notional": 1500}}' \
  | jq '.params'

# Verify the form re-seeds correctly after save
curl -s "http://127.0.0.1:8000/api/v1/strategies/${SID}" | jq '.params'

docker compose down
```

- [ ] Reference RSI shows the typed form.
- [ ] Min/max validation fires correctly.
- [ ] Save round-trips the new values.
- [ ] Reset to defaults populates from schema defaults.
- [ ] User strategy without schema falls back to the JSON textarea.

---

## §7.12 — Commit and PR

```bash
git add apps/backend/app/strategies/base.py
git add apps/backend/app/strategies/loader.py
git add apps/backend/app/strategies/engine.py
git add apps/backend/app/api/v1/schemas/strategies.py
git add apps/backend/app/api/v1/strategies.py
git add apps/backend/tests/strategies/test_loader.py
git add apps/backend/tests/api/test_strategies_endpoint.py
git add strategies_user/examples/rsi_meanreversion.py
git add apps/frontend/src/api/types.ts
git add apps/frontend/src/components/strategies/ParamForm.tsx
git add apps/frontend/src/components/strategies/__tests__/ParamForm.test.tsx
git add apps/frontend/src/pages/Strategies/tabs/ParamsTab.tsx
git add apps/frontend/src/pages/Strategies/__tests__/StrategyDetailPage.test.tsx

git commit -m "feat(strategies): typed param form via params_schema (P4 §7)

- Strategy base class gains params_schema: ClassVar[dict | None] = None
- StrategyLoader exposes the class's params_schema unchanged (it's just an
  attribute on the class; no copy)
- StrategyEngine.get_params_schema(strategy_id) returns the schema for any
  currently-registered strategy
- StrategyResponse gains optional params_schema field, populated only on
  GET /strategies/{id} (not on the list endpoint) to keep list payload small
- Reference RSI strategy declares its schema (6 fields)
- Frontend ParamForm component renders typed inputs per field (integer /
  number / string / boolean / enum), validates min/max/enum, shows
  'Unsaved changes', supports Reset to defaults
- ParamsTab chooses ParamForm when strategy.params_schema is present;
  falls back to the existing JSON textarea otherwise — works for any
  user-authored strategy that hasn't declared a schema yet
- Tests: 3 loader cases, 4 endpoint cases, 6 ParamForm cases, 2 detail-tab cases

Closes P2 Session 5 §5.5.5 deferral; P2 Checklist §7.5.

The schema is NOT persisted in the DB — it lives in code and is read
fresh at registration. A hot-reload (P4 §4) picks up schema changes
for free."

git push -u origin feat/p4-param-form

gh pr create \
  --title "feat(strategies): typed param form via params_schema (P4 §7)" \
  --body "P4 Item 7 — closes the deferral from P2 Session 5 §5.5.5 (Params tab was a JSON textarea). Backwards-compatible: strategies that don't declare params_schema still get the textarea."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
git tag -a p4-param-form-complete -m "P4 §7 complete"
git push origin p4-param-form-complete
```

- [ ] PR merged.
- [ ] Tag pushed.
- [ ] `todo.md` updated: P4 §7 ✅.

---

## Verification Checklist (full session)

- [ ] §7.1 Spec documented (this doc).
- [ ] §7.2 `Strategy.params_schema: ClassVar[dict | None] = None`.
- [ ] §7.3 Loader exposes (or doesn't need to expose) `params_schema`.
- [ ] §7.4 Engine `get_params_schema()`; `StrategyResponse.params_schema` populated on detail endpoint only.
- [ ] §7.5 Reference RSI strategy declares its schema (6 fields).
- [ ] §7.6 7 backend tests pass; full suite green.
- [ ] §7.7 TypeScript types added.
- [ ] §7.8 `ParamForm` component handles all 5 field types.
- [ ] §7.9 `ParamsTab` switches between form and textarea based on schema.
- [ ] §7.10 8 frontend tests pass.
- [ ] §7.11 Live smoke walks happy path + validation + fallback.
- [ ] §7.12 PR merged, tag pushed.

---

## Notes & Gotchas

1. **Schema lives in code, not the DB.** Gotcha-of-record. Persisting a copy would create stale-cache bugs the moment someone hot-reloads (P4 §4) with a changed schema. The engine reads `cls.params_schema` fresh; reload picks up changes for free.

2. **List endpoint omits `params_schema`.** Sending the schema with every list row would bloat the response (especially with 50+ strategies). The detail endpoint includes it; the list doesn't. The frontend list page doesn't render forms, so it never needs the schema.

3. **Schema `default` values do NOT auto-populate `params`.** The DB-persisted `params_json` is still authoritative at runtime; a strategy's `on_init` reads `self.params.get("rsi_period", 14)` (with its own fallback). The schema's `default` is only used by the form's "Reset to defaults" button. Two layers of defaults: schema-default (form) and code-default (`on_init`). Keep them in sync manually.

4. **Cross-field validation is the strategy's job.** "exit_threshold must be > entry_threshold" is `on_init`'s responsibility — raise a clear `ValueError` and the strategy enters ERROR with the message visible. The form's per-field validation is intentionally simple; building general cross-field constraints would invite a half-JSON-Schema implementation.

5. **`Required` validation fires only when there's no default.** A field with `default: 0` is happy to be empty (server uses 0). A field without a `default` key requires a value. This matches the principle "if the strategy author specified a default, they meant it."

6. **`Reset to defaults` merges schema defaults INTO `initialValues`** rather than replacing. If a user has typed a value in a non-schema field that somehow exists in `params` (legacy data, manual JSON edit before), reset preserves those untouched fields. Defensive against pre-form params dicts.

7. **`useEffect` for re-seeding initialValues** uses `dirty` as a guard. Without it, a parent re-fetch mid-edit would wipe the user's input — annoying. With it: re-fetches that happen *between* saves correctly reseed; mid-edit re-fetches don't disrupt.

8. **The form re-throws on save failure.** Without `throw e;` in `ParamsTab.handleSave`, ParamForm clears `dirty` even on failure, losing the user's edit indicator. With the re-throw, ParamForm's catch leaves `dirty=true`. UX detail; matters for trust.

9. **Unknown field types fall back to JSON-string editing inside the form.** §7.8's `renderInput` else-branch handles `type: "object"` or `type: "array"` (which we don't claim to support) by serializing as JSON. Lets a strategy declare a complex field without breaking the form entirely — just makes that one row awkward to edit.

10. **No live preview ("here's how this param change would re-backtest").** The async-backtest infrastructure from P4 §2 makes it tempting, but: implicit re-backtests on every keystroke could blow through the budget, surprise the user, and lock the worker. If "preview a backtest with these params" is wanted, it's a separate explicit button — propose as a future polish item if real users ask.

11. **Schema is per-class, not per-version.** If you publish a v0.2.0 of a strategy with new fields, the new fields appear in the form on the next reload. Old `params_json` rows missing the new fields show empty inputs; the user fills them in and saves. No migration of historic data; new fields default at the code level.

12. **Don't bundle other P4 items.** Tag and ship.

---

*End of P4 Item 7 v0.1.*
