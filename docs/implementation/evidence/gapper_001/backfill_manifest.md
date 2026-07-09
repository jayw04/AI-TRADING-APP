# GAPPER-001 — Backfill Manifest (2026-07-08)

Provenance record for the historical evidence backfill (GAPPER-001 pre-registration **v0.2 §9**). The
design was **frozen BLIND before** this backfill; every available same-day gappers file from the sibling
`claude-trading-view` app was included — **no cherry-picking**. Each evidence record was **regenerated
PIT-valid** (store-as-of-that-day) and marked `backfilled`.

**Totals:** 20 files · **20 valid** (≥1 candidate) · **72 candidate-events** → accrual **20/40 dates,
72/100 events**.

| Trading day | Source file | **Scanned (orig, UTC)** | Box-copy ts | sha256 (16) | Candidates | Fresh | Status |
|---|---|---|---|---|---:|:---:|---|
| 2026-06-08 | premarket_gappers_2026-06-08.json | **2026-06-08T15:34Z ⚠ post-open** | 2026-07-09T00:47Z | `35e0c247cab65495` | 6 | yes | included (⚠ see note) |
| 2026-06-09 | premarket_gappers_2026-06-09.json | 2026-06-09T12:30Z | 2026-07-09T00:47Z | `823e023d0095e134` | 5 | yes | included |
| 2026-06-10 | premarket_gappers_2026-06-10.json | 2026-06-10T12:30Z | 2026-07-09T00:47Z | `b804b947bcfa1981` | 3 | yes | included |
| 2026-06-11 | premarket_gappers_2026-06-11.json | 2026-06-11T12:30Z | 2026-07-09T00:47Z | `fc1ad4cfba0b7dc0` | 3 | yes | included |
| 2026-06-12 | premarket_gappers_2026-06-12.json | 2026-06-12T12:30Z | 2026-07-09T00:47Z | `c2255d57bb45adae` | 1 | yes | included |
| 2026-06-15 | premarket_gappers_2026-06-15.json | 2026-06-15T12:30Z | 2026-07-09T00:47Z | `3a222e3721db8540` | 2 | yes | included |
| 2026-06-16 | premarket_gappers_2026-06-16.json | 2026-06-16T12:30Z | 2026-07-09T00:47Z | `f0a7cdf18308f7c5` | 3 | yes | included |
| 2026-06-17 | premarket_gappers_2026-06-17.json | 2026-06-17T12:30Z | 2026-07-09T00:47Z | `547a5c34d3ee4ce9` | 4 | yes | included |
| 2026-06-18 | premarket_gappers_2026-06-18.json | 2026-06-18T12:30Z | 2026-07-09T00:47Z | `b87aa2793b1801ea` | 2 | yes | included |
| 2026-06-22 | premarket_gappers_2026-06-22.json | 2026-06-22T12:30Z | 2026-07-09T00:47Z | `c9d6bc8cb2596ca6` | 4 | yes | included |
| 2026-06-23 | premarket_gappers_2026-06-23.json | 2026-06-23T12:32Z | 2026-07-09T00:47Z | `f8d0d649347ab004` | 3 | yes | included |
| 2026-06-24 | premarket_gappers_2026-06-24.json | 2026-06-24T12:30Z | 2026-07-09T00:47Z | `5679a57cfe4da088` | 1 | yes | included |
| 2026-06-25 | premarket_gappers_2026-06-25.json | 2026-06-25T12:32Z | 2026-07-09T00:47Z | `b25e8b80394e3939` | 5 | yes | included |
| 2026-06-26 | premarket_gappers_2026-06-26.json | 2026-06-26T12:30Z | 2026-07-09T00:47Z | `247671e03dd573ca` | 6 | yes | included |
| 2026-06-29 | premarket_gappers_2026-06-29.json | 2026-06-29T13:26Z (09:26 ET, pre-open) | 2026-07-09T00:47Z | `2dbf7540e73c34b8` | 4 | yes | included |
| 2026-06-30 | premarket_gappers_2026-06-30.json | 2026-06-30T12:30Z | 2026-07-09T00:47Z | `af713dd2b5668bde` | 5 | yes | included |
| 2026-07-02 | premarket_gappers_2026-07-02.json | 2026-07-02T12:30Z | 2026-07-09T00:47Z | `816b19b24d6293d6` | 5 | yes | included |
| 2026-07-06 | premarket_gappers_2026-07-06.json | 2026-07-06T12:30Z | 2026-07-09T00:47Z | `2298b7195a464229` | 6 | yes | included |
| 2026-07-07 | premarket_gappers_2026-07-07.json | 2026-07-07T12:30Z | 2026-07-09T00:47Z | `e2bd6a038f0f2f2b` | 3 | yes | included |
| 2026-07-08 | premarket_gappers_2026-07-08.json | 2026-07-08T12:30Z | 2026-07-09T00:47Z | `7599eced0851fbef` | 1 | yes | included |

### Skipped days (listed for completeness — genuinely absent, not excluded by choice)

| Trading day | Reason |
|---|---|
| 2026-07-01 | No same-day gappers file was ever produced/synced (scanner didn't run; only a prior file was available → stale, now purged). |
| 2026-07-03 | No 2026-07-03 file exists (the sync shipped 07-02's file that day). |

### Notes

- **Content anchor = the sha256** (first 16 hex shown). The **Box-copy ts** column is when each file was
  copied to the box in this backfill (2026-07-08 evening), **not** the original production time. The
  **Scanned (orig, UTC)** column *is* the original production time — read from each file's embedded
  `scanned_at` field, verified against the sibling's on-disk originals (all 20 sha256s match, added
  2026-07-09 per the registry-review provenance suggestion). 18/20 scans ran at the scheduled
  ~12:30Z ≈ 07:30 **CT** premarket slot; 2026-06-29 ran late but still pre-open (13:26Z = 09:26 ET).
- ⚠ **2026-06-08 was scanned POST-open (15:34Z = 11:34 ET)** — its candidate set may embed intraday
  information (gap/RVOL observed after the open), so that day is *not* premarket-PIT in the same sense
  as the rest. It stays included per the no-selection rule, but the **locked replay must run a
  drop-2026-06-08 sensitivity**; if the verdict flips on that single day, the concentration criterion
  (v0.2 §5 #4) already treats it as disqualifying.
- **PIT validity:** each record used only store data with `date < asof`, so the regeneration is
  point-in-time correct regardless of when it was run.
- **Rule:** all available same-day files were included (no selection); any skipped date is enumerated
  above with its reason.
