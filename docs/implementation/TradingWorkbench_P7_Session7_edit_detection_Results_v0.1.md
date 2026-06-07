# P7 Session 7 — Manual-edit detection — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-06 |
| Phase | P7 — NL → Python strategy authoring (§7 of 8 — P7b) |
| Plan doc | `TradingWorkbench_P7_Session7_edit_detection_v0_1.md` |
| Predecessor | `p7-session6-refine-complete` |
| Tag | **`p7-session7-edit-detection-complete`** (`722aea4` squash → moved to the §7 todo commit) |
| Shipped as | PR **#72** — branch `feat/p7-session7-edit-detection`; squash-merged `722aea4` |
| Verdict | **GO.** Manual edits to an AI-authored strategy are detected and surfaced. Full backend + frontend suites + 3 coverage gates + all 10 invariants green; no migration. |

## What shipped

- **`_is_out_of_sync(session, strategy)`** + **`GET /strategies/{id}/authoring-status`** `{authoring_method, revision_count, out_of_sync}` — on-demand compare: read the on-disk `strategies_user/<code_path>` and compare (`.strip()`) to the last `strategy_revision`'s code. **Conservative — never cry wolf:** `manual` method / no `code_path` / no revisions / missing file / read error all resolve to `out_of_sync = False`. `out_of_sync` also added to the §5 `authoring-history` GET. **No schema change.**
- **`AuthoringNotice.tsx`** (frontend) — fetches the status; renders nothing for `manual` strategies; "✨ AI-authored" (or "AI-authored (refined)") for `nl_*`, plus an amber warning when `out_of_sync`: *"This strategy's code has been manually edited since it was AI-authored. The AI won't see these edits in future conversations…"* Mounted on the strategy detail page (outside the active-status guard, so IDLE AI-authored strategies show it).

## Decisions settled (owner, 2026-06-06 — AskUserQuestion)

1. **Detection:** on-demand compare (no schema change, always accurate).
2. **Scope:** detect + surface a notice (no snapshot/resync — editing breaks history by design, per Decision 5).

## Verification

- 4 backend tests (in-sync after save; `out_of_sync` after a manual file edit; `manual` strategy never out-of-sync; other-user 404; tmp `strategies_user` root) + 3 frontend tests (nothing for manual; AI-authored in sync; warning when out_of_sync).
- Full backend suite **1033 passed / 9 skipped / 0 failed** — one unrelated `test_full_pipeline_paper_buy` integration flake appeared in the full run and **passed in isolation** (§7 is a read-only authoring-status endpoint; it touches nothing in the order pipeline). ruff + mypy(187) clean; 3 coverage gates (risk 0.904 / P2 / P3); all 10 shell invariants. Frontend **vitest 135** + tsc + eslint clean. **No migration.**
- PR CI all green (Python-backend 5m6s). Merged on the owner's "merge on green."

## Next — §8 closes P7

**§8** — template integration (Direction Q6 — P8's range template; **but P8 isn't built yet**, so whether template integration belongs in P7 is itself a §8 decision) + cost-surfacing UI (Q7) + cross-feature polish. After §8, P7 (NL → Python authoring, P7a + P7b) is complete; **P8** (Discovery screener + Range Insight) is the next phase. The `DEBUG_SYSTEM` loop (§6), the authoring history (§5), and this edit-detection (§7) round out P7b.
