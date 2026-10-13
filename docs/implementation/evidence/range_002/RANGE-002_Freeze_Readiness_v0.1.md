# RANGE-002 screen spec: freeze readiness for the 2016-Q1 diagnostic subset (v0.1)

Date: 2026-10-13. Status: working checklist, not a decision record. Nothing here is frozen, enrolled, signed or run. No data was read.
Companion files: `RANGE-002_Screen_Spec_Draft_v0.1.json` (the draft payload, loads with `parse_draft`), `RANGE-002_governance_manifest_PROPOSED.json` (patch; the committed `RANGE-002_governance_manifest.json` is untouched).

## 0. Reading guide

* Profile: screen v2 (`profile.version = 2`, both digests copied from `schema.py`). v2 requires 29 leaves; 14 are DEFERRED, 9 UNMODELLED, 16 EXEMPT. The draft sets every leaf that has a recorded value, including some deferred ones (so the stage-2 spec differs from this one only in what is still open).
* Source tags: **C13** = Jay's confirmation list 2026-10-13 (Owner Instruction Record, last section); **OIR** = Owner Instruction Record draft v0.3 baseline table (adopted when Jay confirms the record; the record is still a DRAFT); **WDR** = Weekly Decision Record items A3/B1-B4 (agenda proposals "recommended answer", decided 2026-10-15; populated here at the lead's instruction, adoption pending the minutes); **PLAN** = Implementation Plan v0.5; **CODE** = value the code accepts (only one choice exists); **LEAD** = lead message 2026-10-13.
* Blocks: **DRY** = a real `--dry-plan` (needs a frozen spec, see section 5), **FRZ** = `freeze_spec`, **RUN** = authorized run. Every FRZ blocker is therefore also a DRY blocker for a real spec. `-` = does not block.
* Resolver: **owner** = owner decision; **evidence** = read from delivered data; **computed** = derived by a command; **technical** = engineering/statistical choice, no data.

## 1. Leaves still UNSET (unresolved by programmatic check: 10 of 29 v2-required)

`costs.components`, `data.daily_price_basis`, `data.fetch_mode`, `data.intraday_price_basis`, `data.vendor`, `gates.trade_unit`, `governance.exposure_signed`, `governance.registry_genesis_id`, `universe.category_map`, `universe.n`. (Under the full profile 43 leaves would be unset; the screen profile restricts the check to the v2 list.)

| Leaf | Value | Source | Resolver | DRY | FRZ | RUN |
|---|---|---|---|---|---|---|
| `universe.category_map` | UNSET | OIR: no guessed value; candidates `Domestic Common Stock`, `...Primary Class`, optional `...Secondary Class`. Live store (NOT the history source) shows 15 labels: `Domestic Common Stock` 13,625; `...Primary Class` 2,246; `...Secondary Class` 1,345; ADR/Canadian/preferred/warrant variants; no `Domestic`, no `Domestic Primary` | evidence (`SELECT DISTINCT category` counts and examples from the history TICKERS, S1b) then owner (include Secondary Class?) | Y | Y | Y |
| `universe.n` | UNSET | PLAN section 2.1: initial proposal 100 (A-SCREEN excerpt also says N = 100). Not in OIR/C13 | owner (one-line confirm; recommend 100) | Y | Y | Y |
| `data.vendor` | UNSET | D03 recommends Alpaca SIP (feed `sip` is schema-pinned; S2 permission basis is Jay's statement) | owner (recommend a label naming Alpaca SIP minute bars) | Y | Y | - |
| `data.fetch_mode` | UNSET | D11; owner direction "left undefined"; the descriptive runner reads a local store and does not use it | owner (enumeration) | Y | Y | - |
| `data.daily_price_basis` | UNSET | CODE: only `SEP_SPLIT_ADJUSTED` is accepted (`COMPATIBLE_PRICE_BASIS_PAIRS`). OIR fact: SEP OHLCV split-adjusted, `closeunadj` definition truncated | evidence: split-window ratio check on the history snapshot (close vs closeunadj and volume across a known split) | Y | Y | Y |
| `data.intraday_price_basis` | UNSET | CODE: only `raw`. The 2026-10-12 probe requested RAW only; adjustment convention of the delivered bars is unverified | evidence: raw/adjusted check on delivered minute bars (S2) | Y | Y | Y |
| `costs.components` | UNSET | D15: "no value proposed". v2 requires non-blank; with `all_in` there is no itemisation | owner (recommend a one-key object stating `all_in`, no components) | Y | Y | - |
| `gates.trade_unit` | UNSET | D18 proposal: one entry = one trade including all exit fills; net R = total net P&L of exit fills / (qty x R_fill). D-6 recorded only the basis | owner (recommend the D18 proposal) | Y | Y | - |
| `governance.registry_genesis_id` | UNSET | read back from `RunRegistry.enroll_new` | computed (registry creation) | Y | Y | Y |
| `governance.exposure_signed` | UNSET | shape open; guard reads only key `exposure_ledger_sha256` | computed: `{"exposure_ledger_sha256": <ExposureLedger.sha256>}` after the ledger exists | Y | Y | Y |

## 2. Leaves SET in the draft

| Leaf | Value | Source | Status |
|---|---|---|---|
| `risk.per_trade_pct` / `per_trade_unit` | 0.25 / `percent` (= 0.0025 fraction; code derives the fraction) | OIR, WDR B3 | OIR |
| `costs.base/stress_bps_per_side`, `accounting_mode` | 5 / 15 (schema-pinned); `all_in` | OIR, WDR B3, CODE | OIR |
| `exits.candidates` | K = 7: E1 time; E2a/E2b fixed_r r_multiple 2.0/3.0; E3a/E3b trailing trail_r 1.0/1.5; E4a scale_out remainder eod; E4b scale_out remainder trail trail_r 1.0 | PLAN 2.2, WDR B1; param keys `r_multiple`/`trail_r`/`remainder` are the kernel's vocabulary (`params.py`), not a recorded D19 decision | WDR |
| `exits.complexity_order` | time, fixed_r, trailing, scale_out | PLAN 2.2 rank column (D-5 "ties by frozen complexity order") | OIR |
| `exits.selection` | score `bootstrap_lower_bound_mean_net_r`; tie_tolerance_r 0.0; min_pf 1.0 (strictly greater); min_trades 300; stop_test `max_stat_bootstrap` | D-1, D-4, D-5, D-2; score and stop_test strings are the Plan Appendix A examples; min_trades 300 is the OIR "< 300 trades = insufficient" figure | OIR |
| `signal.or_completeness_rule` | 0 (max DATA_GAP minutes in 09:30-09:59) | WDR B2, Sheets 5a | WDR |
| `signal.min_or_width_ticks` | 5.0 | WDR B2 ("uncalibrated baseline"). Register D05 says "no value proposed": conflict, WDR is newer | WDR |
| `exit.halfday_offset_min` | 5.0 (12:55 ET on early-close days) | WDR B2, Sheets 5g | WDR |
| `execution.crossed_before_arm_policy` | `SKIP` | WDR B2 | WDR |
| `execution.bar_timestamp_convention` | `start` | OIR fact (Alpaca FAQ); code accepts only `start`. Forum contradicts: verify with one known 09:30 bar BEFORE freeze (timestamps only, return-blind) | OIR + check |
| `fill.halt_policy` | `UNEXECUTABLE_DURING_UNAVAILABLE` | D-7, CODE | OIR |
| `gates.basis` | `signal_level` | D-6 | OIR |
| `p3.max_p3a_attempts` / `max_p3b_attempts` | 3 / 1 | C13 (p3a); LEAD (p3b = 1) | C13 |
| `p3.criteria` | object of D-1..D-7 thresholds (PF > 1.0 selection; REVISE below 1.15; max-stat alpha 0.10; confirmatory alpha 0.05; one-sided 95% bound; delta 0; 300 trades; 100 days; coverage 0.98; unavailable-exit valuation). Key names are descriptive labels; shape is open (D17) | OIR | OIR |
| `stats.bootstrap` | method `stationary`; cluster `trading_day` (pinned); **block_len 10.0 = mean block length in trading days** (leaf is method-neutral: for a stationary method it is the mean; unit follows `cluster`; runner key `mean_block_days`); ci_type `percentile`; confidence_level 0.95; reps and seed UNSET | LEAD (10 trading days), OIR D-4, A-SCREEN 6 | LEAD |
| `stats.alpha_one_sided` | 0.05 | D-3 (D-2 alpha 0.10 has no spec leaf; it is in `p3.criteria` and in the optional `--statistics-config` `alpha`) | OIR |
| `partitions`, `universe.min_price/adv_window_days/rebuild/include_delisted`, `data.feed/bar/session/tz`, `signal` fixed times, `exit.stop/eod_flat`, `gates` fixed thresholds, `stats.adjustment=holm` | schema-pinned | CODE | pinned |
| `profile` | screen v2 with both digests | CODE | pinned |

Left null on purpose (not required by v2): deferred (`controls.*`, `exits.complexity_order` is set, `registration.related_programs`, `stats.hypothesis_family`, `stats.bootstrap.reps/seed`); unmodelled execution leaves and `fill.slippage_model`; exempt `risk.*` caps, `gates.win_rate/max_dd/yearly`, `p5.*`, `diagnostics`, `stats.regime`. A later fill of reps, seed, hypothesis family etc. changes the spec hash, so stage 2 is a new frozen spec (a P3A attempt is counted per registry, not per hash).

## 3. Governance manifest (`RANGE-002_governance_manifest_PROPOSED.json`)

| Field | Value | Source | Blocks FRZ / RUN |
|---|---|---|---|
| `p3_attempt_limits.p3a` | 3 | C13: subset (1) + full development run (1) + one recorded defect recovery (1) | Y / Y; must equal spec `p3.max_p3a_attempts` |
| `p3_attempt_limits.p3b` | 1 | standing recommendation, LEAD | Y / Y; equals spec `p3.max_p3b_attempts` |
| `approved_registry_genesis_id` | null | read back from `enroll_new` (`.genesis_id`); never typed | Y / Y |
| `approved_by` | null | identifier string for the owner instruction (identifier, not signature) | Y / Y |
| `approved_on` | null | date Jay confirms the OIR; not in the future | Y / Y |

The triple is all-or-nothing (`parse_manifest`); the proposed file loads as "limits set, genesis not approved" and still makes freeze and authorize refuse.

## 4. Records the freeze and the run read

### 4.1 Exposure ledger (`ExposureLedger`, strict JSON, schema_version 1)

```
{"schema_version": 1,
 "decision": {"decision_date": "YYYY-MM-DD", "record_kind": "owner_instruction",
              "minutes_path": "<repo-relative, forward slashes>", "minutes_sha256": "<64 hex of committed bytes>"},
 "entries": [{"id": "...", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD",
              "description": "...", "source": "...", "observed_by": "..."}]}
```
`decision` null loads but the guard refuses it. Its `sha256` is the canonical-JSON hash of the whole document (including `decision`), so it moves when the cited minutes move.

What must be in the ledger BEFORE the 2016-01-01..2016-03-31 run: the pre-existing exposures from the D01 audit (RNG-001 backtest 2026-01-02..2026-06-12; the 18-name / 126-session entry study through 2026-07; candidate windows from the register, line 376). These are already inside spec `exposed` / R2 and do not overlap 2016-Q1. The owner audit content is not available to me and is not invented here.

**Conflict to decide (blocks RUN and is not a paperwork issue).** OIR S3 says the three months are registered in the exposure ledger "before RUN". `authorize` raises `ExposureOverlapError` when ANY ledger entry overlaps the requested range (citable partition). So (1) an entry for 2016-01-01..03-31 placed in the ledger before the run makes the run itself refuse; (2) the same entry placed after the run makes any later run whose range includes Q1, including a full 2016-01-01..2019-12-31 development run, refuse. Options: **A (recommended)** pre-run ledger without a Q1 entry; the planned run is registered by the run-registry row (`open_run`, protected range) and named in the owner-instruction record; after the run a successor ledger records Q1; the full development run is then requested as 2016-04-01..2019-12-31 (a month start). **B** record Q1 only in the report and the minutes (no entry). Either way a ledger change = new ledger sha = new `exposure_signed` = new spec hash.
Also decide whether count-only contacts (the 2026-10-12 probe touched 2016-01-05 for 10 symbols, counts and timestamps only) are ledger entries; as entries they would overlap Q1 and block the run. Recommend noting them in the minutes, not as entries.

### 4.2 Owner-instruction decision record (the file `decision.minutes_path` points at)

Needs: a committed file at a repo-relative path (forward slashes, no `..`); `record_kind: owner_instruction`; `decision_date` (date Jay confirms, not future); decision `approved`; scope `["run"]` (add `"build"` only if the record covers it); partitions `["DEVELOPMENT_SELECTION"]` (named whenever scope has run); `strategy_version` and `baseline_id` (proposed `RANGE-002/screen-v2`, `baseline-2026-10-12`; Jay adopts); `minutes_sha256` = SHA-256 of the committed bytes exactly as they are in the executing checkout (line endings matter; hash on the machine/checkout that runs). It must state, in prose, the P3A attempt count (1 of 3), the diagnostic-subset scope and the NON_INFERENTIAL_DESCRIPTIVE label. The check re-reads the file and compares the hash on freeze, on `--dry-plan` and on `authorize`; a one-byte edit after citing it refuses.

### 4.3 The ordering problem (exact)

* `minutes_sha256` is cited by the spec (`decision`) AND by the ledger (`decision`).
* The ledger sha is inside the spec hash (`governance.exposure_signed.exposure_ledger_sha256`).
* `decision.spec_sha256` is the spec hash and is written by `freeze_spec`; `decision` is outside the hashed payload.
* Therefore the minutes file cannot contain the spec hash or the ledger sha (minutes bytes -> minutes_sha -> ledger -> ledger_sha -> spec hash -> minutes: a cycle). The decision-to-spec binding is `decision.spec_sha256` in the FROZEN file plus `strategy_version`/`baseline_id` in the minutes. Record the frozen spec hash afterwards in a separate file (freeze receipt or the next weekly minutes) that nothing cites by hash.
* Strict order: minutes final and committed -> M = its sha -> ledger (cites M) -> L = ledger sha -> spec (cites M, contains L, genesis) -> freeze. Changing any of them upstream invalidates everything downstream.
* Hand-copying `spec_sha256` into the draft is allowed only if equal to the computed digest; leave it null and let the tool write it.

## 5. Dry plan: why a real one needs a frozen spec

`run_descriptive_screen.py --dry-plan` calls `load_frozen` (complete P0 set, decision, hash match, minutes file hash) and nothing else (no manifest, registry, ledger, data). A draft with unset leaves cannot be planned. A real freeze needs the 10 leaves above AND an approved manifest AND a genesis AND the minutes. Minimal route to see the plan before the evidence exists: a scratch-only spec with clearly labelled placeholders (`category_map: ["TEMP_PLACEHOLDER_NOT_REAL"]` etc.) written by a script, not by `freeze_spec`; I ran this offline once in scratch and the plan printed (3 universe months, 61 sessions, 7 candidates, symbol-day upper bound 6,100 at N = 100, `preflight_problems: []`). That plan is not evidence of anything: its spec hash is not the real one, and `authorize` would still refuse (manifest, genesis, ledger).

## 6. Command sequence (from `apps/backend` unless stated)

1. **Record.** Jay confirms the OIR; commit it (no spec hash, no ledger sha inside). `M = python -c "from pathlib import Path; from app.research.range002.spec.hashing import file_sha256; print(file_sha256(Path(r'../../<minutes_path>')))"`.
2. **Registry (no CLI exists).** `python -c "from pathlib import Path; from app.research.range002.governance.run_registry import RunRegistry; r=RunRegistry.enroll_new(Path('<REG_DIR>/range002_runs.jsonl'), enrolled_by='<identifier string>'); print(r.genesis_id)"`. `REG_DIR` is an owner choice and must hold no other governance file or log. Output: `G`.
3. **Manifest.** Copy the PROPOSED file to `RANGE-002_governance_manifest.json`, set `approved_registry_genesis_id = G`, `approved_by`, `approved_on`; reviewed commit so the executing checkout contains it.
4. **Ledger.** Author `LEDGER.json` (section 4.1, `decision` cites M). `L = python -c "from pathlib import Path; from app.research.range002.governance.exposure_ledger import ExposureLedger; print(ExposureLedger.from_file(Path('LEDGER.json')).sha256)"`.
5. **Draft.** Fill the 10 leaves (category_map, daily/intraday basis from evidence; n, vendor, fetch_mode, components, trade_unit from owner; `registry_genesis_id = G`; `exposure_signed = {"exposure_ledger_sha256": L}`) and the `decision` block (section 4.2, `spec_sha256: null`).
6. **Freeze.** `python scripts/research/range002/freeze_spec.py DRAFT.json --out FROZEN.json`, then `--verify FROZEN.json` (prints `spec_sha256`, `has_run_decision=True`). Refuses an existing output, a manifest/spec mismatch of genesis or limits, any unset leaf.
7. **Dry plan.** `python scripts/research/range002/run_descriptive_screen.py --dry-plan` with the arguments of step 8 (needs `--spec FROZEN.json`; reads no data).
8. **Run.** Same command without `--dry-plan`:

| Argument | Value | Where it comes from |
|---|---|---|
| `--spec` | FROZEN.json | step 6 |
| `--registry` | `<REG_DIR>/range002_runs.jsonl` | step 2 |
| `--exposure-ledger` | LEDGER.json | step 4; its sha must equal the spec's `exposure_signed` |
| `--daily-snapshot` | `/opt/workbench/data/research/range002_s1/<export-id>/` | S1 delivery (C13 destination); must carry SEP from about 2015-11-20 for the 40-day lookback |
| `--snapshot-manifest` | S1 `range002.snapshot_manifest.v1` JSON | S1 delivery; file hashes verified |
| `--minute-bars` | S2 DuckDB file, 2016-01..03 | S2 acquisition (after the S1 universe) |
| `--minute-feed` / `--minute-ts-convention` | `sip` / `start` | spec feed; same value as `execution.bar_timestamp_convention` |
| `--date-start` / `--date-end` | `2016-01-01` / `2016-03-31` | OIR S3; start must be a month start; inside DEVELOPMENT_SELECTION |
| `--partition` | `DEVELOPMENT_SELECTION` | phase P3A; consumes 1 of 3 attempts once authorization is issued |
| `--table-filter` | `SEP` | vendor `table` value in history TICKERS (evidence; verify on S1b) |
| `--lookback-calendar-days` | 40 (must be >= 20 and covered by the export) | technical; docstring example |
| `--coverage-threshold` | 0.98 | OIR |
| `--equity` | UNSET | owner (docstring example 100000; no recorded value) |
| `--tick` | 0.01 | technical (US equity minimum tick; kernel takes one tick); confirm |
| `--code-sha` | `git rev-parse HEAD` of the executing checkout (40 hex) | computed |
| `--out-dir` | new empty directory | choice |
| `--exploratory-scope-amendment-id` XOR `--raw-vendor-rows-attested` | needed unless history TICKERS has a `table` column or retained raw rows | owner scope decision (OIR S3: narrowing the universe needs its own scope decision and limitation text) |
| `--delisting-action-value delisted` XOR `--no-delisting-evidence` | candidate `delisted` NOT adopted until seen in the history ACTIONS; otherwise `--no-delisting-evidence` (nothing excluded) | evidence |
| `--provenance KEY=VALUE` | export id, S2 permission basis claimed, etc. | owner |
| `--statistics-config` | omit for the first run (optional, not preregistered) | if used: `mean_block_days` 10, `confidence` 0.95, `alpha` 0.10, `reps` and `seed` have no recorded value |

Exit codes: 0 report, 2 refused (run closed ABORTED if it was opened), 3 report with a data-quality defect. A refusal before `capability_issued` consumes no attempt; a failure after it does (1 of 3 consumed).

## 7. Evidence from the live store (2026-10-13, relayed): still needs the history source

* 2016-Q1 SEP exists for only 4 tickers: the live store cannot supply the PIT universe for 2016. It is not the history source.
* `tickers` is ticker-keyed (reuse collapsed, no `table` column): `build_month_from_store` raises the DATA-INTEGRITY BLOCKER unless an exploratory scope amendment id or raw-vendor-rows attestation is given. Historical identity intervals stay UNAVAILABLE until S1b shows them.
* Category labels (15 observed) cover the three candidate strings above; counts are from the latest-record table, not point-in-time, and are not a mapping decision.
* ACTIONS vocabulary seen (697 rows, 2026-heavy): dividend, relation, acquisitionby, acquisitionof, delisted, split, spinoff, spinoffdividend, tickerchangeto/from, acquisitioncash, acquisitionstock, exchangeto/from, initiated, acquisitioncashusd. `delisted` is the candidate string; NOT adopted until verified on the history ACTIONS (2016-2019 coverage unknown).

## 8. Open items that need a decision (nothing else blocks the freeze)

| # | Decision | Purpose | Recommendation | Work that continues meanwhile |
|---|---|---|---|---|
| 1 | Jay confirms the OIR (date, strategy_version, baseline_id, D-1..D-7, WDR B1-B4 values) | makes the populated values adopted; gives `decision_date` and `approved_on` | confirm as one record | S1 snapshot, enrollment script review, evidence checks |
| 2 | `universe.n` | PIT universe size | 100 | all |
| 3 | Subset ledger handling (4.1 A or B) and probe entries | the run must not refuse itself; full run must stay possible | A; probes in minutes only | ledger authoring |
| 4 | Scope for a ticker-keyed or limited history TICKERS (`--exploratory-scope-amendment-id`) | RUN is refused without it | decide after S1b shows whether raw rows with `table` exist | S1b retrieval |
| 5 | `--equity` | position sizing | 100000 (docstring example only) | all |
| 6 | `data.vendor` label, `data.fetch_mode`, `costs.components`, `gates.trade_unit` | fill the last non-evidence leaves | as in section 1 | all |
| 7 | `category_map` Secondary Class inclusion | universe definition | decide from history counts | S1b |
| 8 | Registry directory (canonical location) | `enroll_new` needs a path | AWS box, dedicated empty directory | all |
| 9 | `stats.bootstrap.reps` and `seed` | only before statistical selection (deferred in v2) | reps 10000 (the recorded floor); seed owner or validator | not needed for the subset |
