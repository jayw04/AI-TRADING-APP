# Trading Workbench — P7 §7: Manual-Edit Detection

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-06 |
| Phase | P7 — NL → Python strategy authoring (§7 of 8 — P7b) |
| Predecessor | `p7-session6-refine-complete` (refinement chat) |
| Successor | `TradingWorkbench_P7_Session8_*` (template integration + cost polish — closes P7) |
| Direction | `TradingWorkbench_P7_Direction_v0.1.md` (Decision 5) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Detect when a saved AI-authored strategy's code has been manually edited (diverged from its authoring history) and surface it on the strategy detail page. |
| Estimated wall time | 2–3 hours |
| Tag on completion | `p7-session7-edit-detection-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

Direction Decision 5: manual editing is always allowed — the trader can open an AI-authored strategy's `.py` and change it directly. But that breaks the AI's conversation continuity: the recorded authoring history no longer matches the code on disk, and a future refinement would work from a code the trader didn't actually edit. §7 detects that divergence and surfaces it honestly ("manual edits won't be visible to the AI in future conversations"), so the trader isn't surprised — the escape hatch is allowed, but its consequence is named.

## Decisions settled for §7 (owner, 2026-06-06)

- **Detection: on-demand compare.** When the authoring status is requested, read the on-disk `strategies_user/<code_path>` and compare to the last `strategy_revision`'s code; differ → `out_of_sync`. **No schema change** — at save the file equals the last revision's code, so it's in sync until the trader edits the file.
- **Scope: detect + surface a notice.** `out_of_sync` on a lightweight status endpoint; a notice on the strategy detail page for AI-authored strategies that diverged. No "snapshot/resync" action (Decision 5 frames editing as *breaking* history, not keeping it in sync).

## What this session ships

1. `GET /strategies/{id}/authoring-status` — `{authoring_method, revision_count, out_of_sync}` (+ `out_of_sync` added to the §5 `authoring-history` GET for consistency).
2. Frontend: an "AI-authored / manually edited" notice on the strategy detail page.
3. Tests.

## Detailed work

### §7.1 — `_is_out_of_sync` + the status endpoint

`app/api/v1/strategy_authoring.py`:

```python
async def _is_out_of_sync(session, strategy) -> bool:
    if strategy.authoring_method == "manual":
        return False                      # no AI history to diverge from
    last = (await session.execute(
        select(StrategyRevision).where(StrategyRevision.strategy_id == strategy.id)
        .order_by(StrategyRevision.seq.desc()).limit(1)
    )).scalars().first()
    if last is None or not strategy.code_path:
        return False
    path = _strategies_root() / strategy.code_path
    if not path.exists():
        return False                      # can't compare → don't cry wolf
    try:
        on_disk = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return on_disk.strip() != last.code.strip()

@router.get("/strategies/{strategy_id}/authoring-status")
async def get_authoring_status(...):
    # ownership-checked (404); returns {authoring_method, revision_count, out_of_sync}
```

- **Conservative:** any ambiguity (no revisions, missing file, read error) → `out_of_sync = False`. The notice should never fire spuriously.
- `.strip()` compare absorbs trailing-newline quirks from `write_text`; a real edit changes content meaningfully.

### §7.2 — Frontend notice

- `strategyAuthoring.ts` — `authoringStatus(id) → {authoring_method, revision_count, out_of_sync}`.
- `components/strategies/AuthoringNotice.tsx` — plain `useState/useEffect` (detail page has no QueryClientProvider): fetches the status; renders nothing for `manual` strategies; for `nl_*`, shows a small "✨ AI-authored" line, and **when `out_of_sync`** an amber warning: *"Manually edited since it was AI-authored — the AI won't see these edits in future conversations."*
- Mounted on `pages/Strategies/Detail.tsx` near the other cards.

### §7.3 — Tests

- **Backend** (`test_strategy_authoring_status.py`): a freshly-saved AI strategy → `out_of_sync False`; overwrite its `.py` on disk → `out_of_sync True`; a `manual` strategy → `False`; a strategy with no revisions → `False`; another user's strategy → 404. (tmp `strategies_user` root.)
- **Frontend**: the notice renders the warning when `out_of_sync`, only the "AI-authored" line when in sync, and nothing for a manual strategy.

## What this session does NOT do

- **No resync / "snapshot current code"** — editing breaks history by design (Decision 5); §7 surfaces it, doesn't reconcile it.
- **No schema change / migration** — on-demand compare.
- **No "continue authoring a saved strategy" flow** — there's no re-open-conversation path yet; the notice is forward-looking. (Such a flow, if built, would read `out_of_sync` to warn before refining.)
- **No blocking** — a manually-edited strategy still runs/activates normally; the edit is the trader's prerogative.
- **No order-path / new CI invariant.**

## Notes & gotchas

1. **Never cry wolf** — every ambiguous case resolves to `out_of_sync = False`. A false positive here would erode trust in the notice.
2. **`manual` strategies are always in sync** (no AI history) — the notice is only for `nl_generation` / `nl_refinement`.
3. **The compare is content, not a hash** — simple and stateless; the file is small (≤~150 lines). No stored hash to keep current.
4. **`.strip()` both sides** — `write_text(body.code)` and the stored revision code can differ by a trailing newline without being a real edit.
