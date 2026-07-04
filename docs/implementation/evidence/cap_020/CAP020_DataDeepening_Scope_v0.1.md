# Factor-Store History Deepening — Scope (unblocks CAP-020 validation)

| Field | Value |
|---|---|
| Version | v0.1 (scope — for a go/option decision) |
| Date | 2026-07-04 |
| Why | CAP-020 validation is Inconclusive **(data-gated)** — the factor store's 4-book overlap is only 1.5y (2024-12→2026-06). This scopes the data work to get ≥4y incl. the 2020/2022 bears. |
| Runtime | The **box** (Norton-free, has Sharadar creds + truststore + the store). Multi-day background ingest. |

## Root cause (measured on the box store)

The SEP price table has the **universe only from 2024 onward**; before that, essentially nothing:

| Year | SEP rows | Distinct tickers |
|---|---|---|
| 2015–2023 | ~1,000/yr | **4** (proxies only) |
| 2024 | 180,442 | 1,227 |
| 2025 | 309,618 | 1,247 |
| 2026 | 140,004 | 1,253 |

`ingest_runs` shows a bulk `sep:<TICKER>` backfill on **2026-06-14** that pulled **~509 rows/ticker (~2 years)** — bounded by a `--start` filter to stay under Nasdaq Data Link's ~1M-rows/day cap. So this is an **ingestion-completeness gap, not a source limit**: Sharadar SEP history is deep (the store's own bounds show 1997-12-31 for the 4 proxies) and the paid tier already includes it (Core US Equities Bundle). The universe's *deep* history was simply never pulled.

## What's needed

Re-ingest **SEP** for the universe with an earlier `--start` (≈ **2017-01-01**) so each ticker gains its 2017–2023 rows. `ingest_sep` is `INSERT OR REPLACE` keyed by `(ticker, date)`, so a deeper re-pull **backfills** the missing rows without deleting the 2024+ data — idempotent and convergent.

**Not blockers (confirmed):**
- **SF1 fundamentals are not needed** — all four books are price/metadata based: momentum/low-vol/trend price off `closeadj`; sector uses `tickers.sector` (metadata, already fully populated: 21,679 tickers). So the Sharadar SF1 2016Q1 floor does **not** gate this.
- **No incremental $ cost** — SEP is in the already-paid bundle; the only constraint is the ~1M-rows/day rate limit.

## Two options (the decision)

| | Option A — Pragmatic | Option B — Rigorous (survivorship-free) |
|---|---|---|
| Universe | The **~1,254** tickers already in SEP (today's active large/mid-caps) | The full **14,150**-name survivorship pool (`survivorship_pool.txt`, incl. delisted) |
| Rows to pull (→2017) | ~1,254 × ~2,100 ≈ **2.6M** | ~14,150 × ~2,100 ≈ **28M** |
| Time at ~1M rows/day | **~3 days** | **~4 weeks** |
| Fidelity | Mild **survivorship bias** pre-2024 (misses names delisted before 2024) | Survivorship-free (matches the backtest's design intent) |
| Unblocks validation | Yes, quickly, with a documented caveat | Yes, fully faithful |

**Decision (owner, 2026-07-04): Option 3 — A now, B if borderline.** Run Option A to get an evidence-based answer in days; escalate to B only if the pre-committed triggers below fire. This preserves the evidence-first, incremental rollout discipline and avoids 4 weeks of ingest before knowing it's needed.

### Escalation rule (PRE-COMMITTED — decided before Option A runs, so escalation is objective, not taste)

Escalate to **Option B (full survivorship-free universe)** if **any** of these fire on the Option-A result:

1. **Verdict = Conditionally Promising** (not a clean Validated or Rejected).
2. **A primary-metric CI includes or *nearly* includes zero** — objectively: ΔCalmar CI-low `< 0.02` (i.e. within 20% of the `0.10` threshold) **or** ΔMaxDD CI-low `< 1.0 pp` (within 20% of the `5 pp` threshold), including any CI that spans zero.
3. **Robustness only narrowly satisfied** — the grid pass rate is in `[2/3, 7/9]` (≤ 1 cell of slack above the bar).
4. **High transaction-cost sensitivity** — the verdict flips across the 5/10/20/50 bps sweep, **or** headline ΔCalmar degrades > 50% from 5 → 50 bps.
5. **Conflicting conclusions across parameters** — the sign of ΔCalmar or ΔMaxDD is inconsistent across the SMA×gross grid (some cells materially improve, others materially worsen).

Only a **clean, cost-insensitive, robust Validated or a clean Rejected** avoids escalation. These triggers are encoded so the escalation decision does not depend on whether we "like" the Option-A numbers.

### Survivorship-bias disclaimer (goes verbatim in the Option-A result doc)

> *"This validation uses the active-name universe available in the current factor store. Results are suitable for engineering validation and research prioritization but are **not** considered the final survivorship-free evidence package. If the outcome is borderline, validation will be repeated using the full historical survivorship-free universe."*

### Option B is strategic infrastructure, not just a contingency

Even when Option A answers CAP-020, a complete survivorship-free factor store is a program-level asset, not a one-study cost. It strengthens: new factor research, multi-factor portfolio construction, regime studies, cross-validation / walk-forward testing, and external white-paper / evidence packages. Regardless of the CAP-020 outcome, **Option B is worth scheduling as background infrastructure** (it can run un-prioritized behind the rate limit over weeks); the escalation rule only governs whether it *blocks* the CAP-020 verdict.

## Mechanics — SAFE staging deepen + deferred swap (no live impact until the swap)

The backend holds `factor_data.duckdb` **read-only** and DuckDB is single-writer, so an ingest must **not**
write the live store directly (it would lock out / fail against live factor reads incl. Monday's
rebalance). Follow the established `deploy/aws/factor-refresh.sh` pattern: **deepen a copy, swap later.**

```bash
ssh workbench && cd /opt/workbench/app
DATADIR=/opt/workbench/app/data
# 0) universe = the ~1,254 tickers already in sep (dump once)
sudo docker compose ... exec -T backend python -c \
  "import duckdb;[print(r[0]) for r in duckdb.connect('/app/data/factor_data.duckdb',read_only=True).execute('SELECT DISTINCT ticker FROM sep ORDER BY 1').fetchall()]" \
  | sudo tee $DATADIR/cap020_deepen_universe.txt >/dev/null
# 1) snapshot live -> a DEDICATED deepen copy (NOT the factor-refresh staging file — avoid collision)
sudo cp -f $DATADIR/factor_data.duckdb $DATADIR/factor_data.deepen.duckdb
# 2) deepen the COPY to 2017 — depth-aware resume so a daily re-run only pulls still-shallow tickers
sudo docker compose ... exec -T \
  -e WORKBENCH_FACTOR_DATA_DB_PATH=/app/data/factor_data.deepen.duckdb backend \
  python scripts/ingest_sharadar.py --tickers-file data/cap020_deepen_universe.txt \
    --datasets sep --from 2017-01-01 --skip-deep-enough
```

- **`--skip-deep-enough`** (this PR) is the resume enabler: it skips a ticker only when its existing
  earliest SEP date is already ≤ `--from`. (Plain `--skip-existing` skips on mere presence → would
  deepen nothing.) So the job is safely re-runnable daily across the ~1M-rows/day cap; a **daily box
  cron** runs it until every universe ticker is deep, then no-ops. ~2.6M rows ≈ **~3 daily passes**.
- The live store is **untouched** throughout — only the `.deepen.duckdb` copy grows.

### Deferred swap (the only step that touches live — do it consciously)
When the deepen copy is complete and verified (`min(date) ≤ 2017` for the universe, row counts sane),
swap it in at a **safe time — NOT during/near a rebalance** (avoid Monday 14:40 UTC): `mv -f
factor_data.deepen.duckdb factor_data.duckdb` then restart the backend (resume-on-boot re-registers).
This is the reversible/gated boundary; the weekend deepen before it carries no live risk.

## Verification (turns the harness verdict real)

After the backfill, re-run the CAP-020 harness (already merged, `#349`) — **no code change**:
```bash
python scripts/cap020_regime_validation.py --report-dir research/cap020/
```
Success = the data-sufficiency gate clears (usable window ≥4y, ≥4 OOS flips, ≥1 bear environment) → the harness emits a real **Validated / Conditionally Promising / Rejected** verdict against the owner-approved Calmar-primary hierarchy.

## Follow-ups
- Reconcile the FI-001 Phase 4 "2019–2026" claim vs the store's 2024+ overlap (Phase 4 may have run on a fuller store, or its eqw was on the same intersection). See [[factor_data_staleness_gap]].
- If Option A, document the survivorship caveat in the eventual result doc.
