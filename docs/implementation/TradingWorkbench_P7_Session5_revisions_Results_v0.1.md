# P7 Session 5 — Authoring history (`strategy_revisions`) — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-06 |
| Phase | P7 — NL → Python strategy authoring (§5 of 8 — first P7b session) |
| Plan doc | `TradingWorkbench_P7_Session5_revisions_v0_1.md` |
| Predecessor | `p7-session4-authoring-ui-complete` (P7a complete) |
| Tag | **`p7-session5-revisions-complete`** (`d9af21a` squash → moved to the §5 todo commit) |
| Shipped as | PR **#70** — branch `feat/p7-session5-revisions`; squash-merged `d9af21a` |
| Verdict | **GO.** The authoring-history data layer. Full backend + frontend suites + migration + 3 coverage gates + all 10 invariants green. |

## What shipped

- **`strategy_revisions` table** (`app/db/models/strategy_revision.py`) — `id`, `strategy_id` (FK `strategies`, CASCADE), `seq` (0-based turn order), `kind` (`generation` | `refinement`), `user_message`, `assumptions_json`, `explanation`, `code`, `backtest_json`, `cost_usd`, `created_at`; `Index(strategy_id, seq)`. Alembic `b6d1f4a8c3e2` (down-rev `a4c7e9b2f1d6`; round-trips).
- **`POST /strategies/author/save`** gains `history: RevisionInput[]` (default `[]`, max 100) — persisted as `strategy_revisions` linked to the saved strategy, inside the save transaction (a revision-insert failure rolls back the row **and** unlinks the file via the existing orphan guard). **Empty history → one `generation` turn from the saved code.** History is metadata, **never executed** — only `body.code` is AST-validated + loaded.
- **`GET /strategies/{id}/authoring-history`** — read-only, ownership-checked (404 otherwise), ordered by `seq`; empty `revisions` for a manually-authored strategy.
- **Frontend** — `saveAuthored(code, name, history)` gains the history arg; `AuthorWithAI` records `generatedFrom` (the description it generated from) and sends a single `generation` turn on save. No new view (§6 renders it).

## Decisions settled (owner, 2026-06-06 — AskUserQuestion)

1. **Persistence:** persist-on-save — the client holds the conversation; Save writes the full history. No orphan rows, no cleanup cron, generation stays stateless.
2. **Scope:** backend capture + read endpoint; the read-only history view lands with §6's refinement chat.

## Notes

- **No `authoring_history_id` on `strategies`** — the history is queried by `strategy_id` (a single-FK column doesn't fit a many-row conversation). The Direction's "FK if applicable" wording is satisfied by the reverse FK on `strategy_revisions`.
- **`seq` is the authoritative order**, not `created_at` (which can tie within one save commit).

## Verification

- 4 backend history tests (2-turn save → GET in `seq` order with kinds/backtests; no-history → one `generation` turn from the code; manual strategy → empty; other-user → 404) + the frontend `AuthorWithAI` save test updated to assert the `generation` history turn.
- Full backend suite **1024 passed / 9 skipped / 0 failed**; ruff + mypy(187) clean; migration round-trips; 3 coverage gates (risk 0.904 / P2 / P3); all 10 shell invariants. Frontend **vitest 131** + tsc + eslint clean.
- PR CI all green (Python-backend 4m24s). Merged on the owner's "merge on green."

## Next

**§6** — the refinement chat UI + the `REVISION_SYSTEM`/`DEBUG_SYSTEM` calls (prompt-ready from §1; `create_message` supports tool-use from §2): a `POST /strategies/author/refine` (stateless, like generate — prior code + change request → revised complete file via `emit_strategy`) + re-backtest (reuse §3) + the chat UI that accumulates turns into the history §5 captures + accept/revert. The `DEBUG_SYSTEM` auto-retry-on-backtest-failure loop lands here. Then **§7** (manual-edit detection) and **§8** (template + cost polish). Open Qs: conversation pruning (Q3 — keep-last-N / summarize, relevant once refine appends many turns), logic-bug mitigation (Q5).
