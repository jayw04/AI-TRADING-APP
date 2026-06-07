# Trading Workbench — P7 §5: Authoring History (`strategy_revisions`)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-06 |
| Phase | P7 — NL → Python strategy authoring (§5 of 8 — first P7b session) |
| Predecessor | `p7-session4-authoring-ui-complete` (P7a complete) |
| Successor | `TradingWorkbench_P7_Session6_*` (the refinement chat UI + REVISION/DEBUG calls) |
| Direction | `TradingWorkbench_P7_Direction_v0.1.md` (Decision 3) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | The `strategy_revisions` table + conversation-history capture: the save persists the authoring conversation, read-only, linked to the saved strategy. The display lands with §6. |
| Estimated wall time | 3–4 hours |
| Tag on completion | `p7-session5-revisions-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

Direction Decision 3: an AI-authored strategy preserves its authoring conversation — the description, the AI's responses, each code revision, and the backtest at each turn — as read-only metadata of the saved strategy, separate from the audit log. §5 builds the data layer for that: the `strategy_revisions` table and the capture path. It is the foundation §6's refinement chat appends to, so it goes first (Direction order).

## Decisions settled for §5 (owner, 2026-06-06)

- **Persistence model: persist-on-save.** The client holds the conversation turns during authoring (generation stays stateless); **Save** sends the full history and the server writes them as `strategy_revisions` linked to the saved strategy. Only saved strategies have history — **no orphan rows, no cleanup cron**, and the generate endpoint is unchanged. Matches "read-only metadata of the saved strategy."
- **Scope: backend capture + read endpoint.** §5 ships the table, the save-captures-history, and `GET .../authoring-history`; AuthorWithAI sends its single generation turn on save. The read-only *view* lands with §6's refinement chat (where a multi-turn conversation is worth rendering).

## What this session ships

1. `strategy_revisions` table + model + migration.
2. `POST /strategies/author/save` accepts an optional `history: RevisionInput[]` and persists it.
3. `GET /strategies/{id}/authoring-history` (read-only).
4. Frontend: AuthorWithAI sends the generation turn on save (no new view).
5. Tests.

## Detailed work

### §5.1 — `strategy_revisions` (`app/db/models/strategy_revision.py`)

```python
REVISION_GENERATION = "generation"
REVISION_REFINEMENT = "refinement"

class StrategyRevision(Base):
    id; strategy_id (FK strategies, CASCADE); seq (int, 0-based turn order);
    kind (generation | refinement);
    user_message (Text — the description / change request);
    assumptions_json (JSON list); explanation (Text); code (Text);
    backtest_json (JSON | None — the turn's backtest outcome dict);
    cost_usd (Numeric(20,4) | None); created_at;
    Index("ix_strategy_revisions_strategy_seq", "strategy_id", "seq")
```
Migration: new revision, down-rev `a4c7e9b2f1d6`. Register in `models/__init__`.

### §5.2 — Save persists the history

`SaveAuthoredRequest` gains `history: list[RevisionInput]` (default `[]`, max 100). `RevisionInput = {kind, user_message, assumptions, explanation, code, backtest, cost_usd}` — all loosely typed (it's the user's own conversation, metadata only, **not executed**: only `body.code` is AST-validated + run). After the strategy row is created (and `flush`ed for its id), each turn is inserted as a `StrategyRevision(strategy_id=row.id, seq=i, ...)` before the commit. **Empty history → one `generation` turn from the saved code**, so every authored strategy has at least its final code recorded. The existing orphan-file cleanup covers a revision-insert failure too.

### §5.3 — `GET /strategies/{id}/authoring-history`

Ownership-checked (404 if not the user's). Returns `{strategy_id, authoring_method, revisions: [{seq, kind, user_message, assumptions, explanation, code, backtest, cost_usd, created_at}]}` ordered by `seq`. Empty `revisions` for a manually-authored strategy. Read-only — there is no write/edit endpoint for history.

### §5.4 — Frontend

`saveAuthored(code, name, history)` gains the history arg. `AuthorWithAI` records the description it generated from (`generatedFrom`) and, on save, sends a single `generation` turn `{user_message: generatedFrom, assumptions, explanation, code, backtest, cost_usd}`. No new UI — §6 renders the history.

### §5.5 — Tests

- **Backend** (`test_strategy_authoring_history.py`): save with a 2-turn history → `GET` returns both in `seq` order with the right kinds/backtests; save with no history → one `generation` turn from the code; a manual strategy → empty `revisions`; another user's strategy → 404.
- **Frontend**: the existing `AuthorWithAI` save test asserts `saveAuthored` is called with the code, name, and a `generation` history turn.

## What this session does NOT do

- **No refinement / `REVISION_SYSTEM` / `DEBUG_SYSTEM` calls** — §6. §5 only captures the single generation turn the client produces today.
- **No history *view*** — §6's chat renders it; §5 ships the read endpoint only.
- **No eager/server-side capture, no conversation_id, no orphan-expiry cron** — persist-on-save (owner pick).
- **No edit/delete of history** — read-only after save (Decision 3).
- **No `authoring_history_id` column on `strategies`** — the history is queried by `strategy_id`; a single-FK column doesn't fit a many-row conversation.
- **No order-path / new CI invariant.**

## Notes & gotchas

1. **History is metadata, never executed.** Only `body.code` (the strategy being saved) is AST-validated + loaded; the `history[].code` entries are stored verbatim for reference.
2. **Persist inside the save transaction** — revisions are added after the strategy `flush` (for the FK) and before the commit; a failure rolls back the row *and* unlinks the file.
3. **Empty-history fallback** keeps the invariant "every AI-authored strategy has ≥1 revision" so §6's chat always has a starting point.
4. **Query by `strategy_id`, ordered by `seq`** — `seq` is the authoritative turn order (not `created_at`, which can tie within one save).
