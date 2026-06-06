# Trading Workbench — P7 §4: "Author with AI" UI + Save Flow

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-06 |
| Phase | P7 — NL → Python strategy authoring (§4 of 8 — **completes P7a**) |
| Predecessor | `p7-session3-backtest-complete` (§3 auto-backtest) |
| Successor | `TradingWorkbench_P7_Session5_*` (P7b — `strategy_revisions` table + refinement) |
| Direction | `TradingWorkbench_P7_Direction_v0.1.md` (Decisions 1/4/5) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | The "Author with AI" page (describe → generate → review code+backtest → save) + the authored-save flow + the `authoring_method` field. Closes P7a. |
| Estimated wall time | 4–6 hours |
| Tag on completion | `p7-session4-authoring-ui-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

§2 generates code; §3 backtests it; §4 gives the trader a place to *do* it and a way to keep the result. A new "Author with AI" page takes a plain-English description, calls the §2/§3 endpoint, shows the generated code + the backtest + the "what I assumed" list + the explanation, and lets the trader **save** it — at which point the generated `.py` is written, validated, and registered as a normal strategy (Decision 4: standard lifecycle, no bypass) tagged `authoring_method = "nl_generation"`. With §4, P7a (single-shot generation) is a shippable, end-to-end feature.

## Decisions settled for §4 (owner, 2026-06-06)

- **Save:** a new **`POST /strategies/author/save`** endpoint — re-run the §3 AST safety check (never persist unsafe code), write `strategies_user/<slug>.py`, validate via `StrategyLoader`, and create the `strategies` row with `authoring_method = "nl_generation"`.
- **UI:** **read-only display + save-as-is** — the generated code is shown (zero-dep `<pre>`; Norton blocks a highlighter), saved exactly as generated. Inline editing + manual-edit detection is §7.

## What this session ships

1. Migration + model: `strategies.authoring_method` (`String(16)`, default `"manual"`).
2. `POST /strategies/author/save` (in `strategy_authoring.py`).
3. Frontend: the "Author with AI" page, its API client, the route, and an entry point from the Strategies list.
4. Tests (backend save + frontend page).

## Detailed work

### §4.1 — Schema: `authoring_method`

`app/db/models/strategy.py` — add after `harness_role`:
```python
# P7 §4: how this strategy was authored — "manual" (hand-written / registered by
# code_path), "nl_generation" (single-shot AI), "nl_refinement" (P7b), "template"
# (P8). Default "manual"; the authored-save endpoint sets "nl_generation".
authoring_method: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
```
Alembic migration (new revision, down-rev `f1b8d3e6a2c7`): `batch_alter_table` adds the column with `server_default="manual"` (backfills existing rows). Round-trip up/down/up. Add `authoring_method` to `StrategyResponse` (additive).

### §4.2 — `POST /strategies/author/save`

`app/api/v1/strategy_authoring.py`:
```python
class SaveAuthoredRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40000)
    name: str = Field(min_length=1, max_length=128)

@router.post("/strategies/author/save")
async def save_authored_strategy(body, request, current_user, session):
    # 1. Safety: validate_generated_code(body.code) → 400 on SyntaxError / UnsafeCodeError.
    # 2. slug = _slugify(body.name); path = strategies_user/<slug>.py; exists → 409.
    # 3. write the file; on ANY subsequent failure, delete it (no orphan file).
    # 4. StrategyLoader(strategies_user).load(<slug>.py) → cls  (StrategyLoadError → 400 + cleanup).
    # 5. StrategyRow(user_id, name=body.name, version=cls.version, type=PYTHON, status=IDLE,
    #      code_path="<slug>.py", params_json=dict(cls.default_params), symbols_json=list(cls.symbols),
    #      schedule=cls.schedule, authoring_method="nl_generation"); audit STRATEGY_REGISTERED
    #      (payload notes authoring_method). commit.
    # 6. return the StrategyResponse (the UI navigates to /strategies/{id}).
```

- **Safety on save is non-negotiable** — the save re-validates with the §3 AST validator. Generation already validated, but the save is a separate trust boundary (a client could POST arbitrary `code`).
- **Slug**: lowercase, non-alphanumeric → `_`, collapse repeats, strip; empty → 400. Collision → 409 ("a strategy file by that name already exists").
- The generated code is **self-describing** — version / schedule / symbols / default_params come from the loaded class, not the request (the request is just `{code, name}`).
- **No backtest on save** — it was backtested at generation; save just persists.

### §4.3 — Frontend: the "Author with AI" page

- `src/api/strategyAuthoring.ts` — `author(description)` → `POST /strategies/author` (returns `{code, assumptions, explanation, cost_usd, model, backtest}`); `saveAuthored(code, name)` → `POST /strategies/author/save` (returns the strategy).
- `src/pages/Strategies/AuthorWithAI.tsx` — plain `useState` (no react-query needed):
  - a description `<textarea>` + **Generate** button (disabled while generating / empty);
  - on result: the code in a read-only `<pre className="font-mono ...">`, a **backtest panel** (status + metrics: total return, Sharpe, max drawdown, win rate, trade count — or the failure message / "unavailable"), the **assumptions** list ("What the AI assumed"), the **explanation**, and the **cost**;
  - a **Save** row (name input + Save button → `saveAuthored` → navigate to `/strategies/{id}`) and **Discard** (clears back to the description).
  - error handling: 429 budget / 400 no-key / 502 generation-failure surfaced as friendly messages.
- Route `/strategies/author` in `App.tsx`; an **"✨ Author with AI"** button on `pages/Strategies/index.tsx` next to "+ New strategy".

### §4.4 — Tests

- **Backend** (`tests/api/test_strategy_authoring_save.py`): save success → a `strategies` row with `authoring_method="nl_generation"`, `status=IDLE`, a written file + STRATEGY_REGISTERED audit; unsafe code → 400 + **no file, no row**; a duplicate name → 409; a code that the loader can't resolve (no Strategy subclass) → 400 + cleanup. Uses a tmp `strategies_user` root (monkeypatch `_strategies_root`) so the suite never writes into the repo.
- **Frontend** (`AuthorWithAI.test.tsx`): generate renders code + backtest metrics + assumptions; Save calls `saveAuthored` with the code+name and navigates; budget/no-key errors render.

## What this session does NOT do

- **No inline code editing** — read-only display; the editable area + "AI is out of sync" manual-edit detection is §7.
- **No refinement / conversation** — §5–§6 (P7b); §4 is single-shot only.
- **No `strategy_revisions` table / `authoring_history`** — §5.
- **No `DEBUG_SYSTEM` auto-retry** — a failed backtest is shown; the trader re-describes or saves anyway.
- **No syntax highlighting** — zero-dep `<pre>` (Norton blocks adding a highlighter).
- **No order-path / risk-engine / new CI invariant.** Generated, saved strategies obey every existing gate (24h cooldown, risk engine) like any strategy (Decision 4).

## Notes & gotchas

1. **Re-validate on save.** The save endpoint runs the §3 AST validator again — the generation safety check does not transfer trust to a separate save request.
2. **Clean up the file on any post-write failure** so a failed save never leaves an orphan `.py` under `strategies_user/`.
3. **`authoring_method` default `"manual"`** backfills existing rows + covers the manual create path (which doesn't set it). The migration uses `server_default`.
4. **Tests must not write into the repo's `strategies_user/`** — monkeypatch the root to a tmp dir.
5. **The saved strategy is `IDLE`** and goes through the normal backtest → paper → activation lifecycle — §4 does not start, paper, or activate it (Decision 4).
6. **Norton:** the generate call's real Sonnet + the backtest's real bars can't run locally; the page is exercised against a mocked API in vitest, and the live path on a non-Norton stack.
