# MKT-PROJ-001 §4 — Inference, API, Research-Preview Card: Plan v0.1

| Field | Value |
|---|---|
| Document version | v0.2 — synced with the owner's resolved Q1–Q4 answers and the AMENDED two-tier drift rule (approval messages 2026-07-11); v0.1 was the pre-answer draft. Backend built as PR #419. |
| Date | 2026-07-10 |
| Predecessor | §3 evidence + ModelCard v1.0 (#417, merged) — owner decision folded verbatim |
| Scope | The narrow badge only: **Validated Move-Risk Projection — Primary Horizon Only**, wording capped at "Elevated move risk; direction uncertain" |
| Estimated wall time | 6–9h (backend PR + frontend PR), plus one trading day of live verification |
| Out of scope | Everything on the owner's not-allowed list: order path · ranking · sizing · portfolio construction · directional call · secondary-horizon claim · ensemble substitution · threshold tuning · LLM-generated market explanation. Also: no new models, no new features, no re-training. |

## The eight owner guardrails → concrete mechanisms

| # | Guardrail | Mechanism |
|---|---|---|
| 1 | Freeze artifact + threshold | Registry row `calibrated_logistic_primary-…` (sha256 `5ec68701…`) is promoted `candidate → production` as an **audited action** (new `AuditAction.MKTPROJ_MODEL_PROMOTED` + on-call playbook scenario). `infer.py` loads by hash — mismatch = "Projection unavailable", never a fallback model. `ELEVATED_CALL_MIN_P = 0.5` stays a frozen constant. |
| 2 | Primary horizon only | Exactly one inference job (close−15m). No pre-open job exists; the API rejects `projection_type=PRE_OPEN_TODAY` requests with an explicit "not served — no validated claim" response. |
| 3 | Show only the capped claim | The card renders **P(MATERIAL) only** — no UP/DOWN probabilities anywhere in the UI. Two templated phrases (no LLM): elevated → *"Elevated move risk; direction uncertain."*; not elevated → *"No elevated move-risk signal today."* (owner-approved, Q2 resolved). |
| 4 | Track every served prediction | `mktproj_outcomes` (18:30 ET next session) writes realized return/label/threshold/correctness for each SUCCESS run — no served projection escapes grading. |
| 5 | CEE calibration drift | The §3 OOS envelope (Brier 0.2338, ECE 0.0312) registers as this surface's research envelope; CEE's rolling window compares served-projection calibration against it with the standard Insufficient-Evidence→Watch→Investigate ladder. |
| 6 | Monthly regime slices | A monthly job (1st, 17:05 ET) recomputes served-projection Brier by uptrend/downtrend/vol-high/vol-low/**stress-like (trailing vol top decile)** vs the baseline, writes `evidence/mkt_proj_001/regime_report_<YYYY-MM>.json`, and adds a line + any degradation alert to the daily report. |
| 7 | Stress-regime caution | The owner's regime-limitation wording (ModelCard v1.0) renders verbatim as the card's footnote and ships in the API payload. |
| 8 | Drift ⇒ downgrade | The 30-day train/serve diagnostic (live IEX features recorded per run; SIP re-fetch compared after maturity). **Owner-amended two-tier rule (Q3 resolved): WARNING/investigate — any manifest feature has ≥0.5σ standardized mean drift on a served day. AUTO-DOWNGRADE — any feature has ≥0.5σ drift for 3 consecutive served days; OR any feature has ≥1.0σ drift on one served day; OR more than 20% of manifest features exceed ≥0.5σ on the same served day.** Downgrade sets the badge to *"Research Preview — data drift under review"* + SNS alert (via the log watcher); downgrade is sticky and **restoration is operator-only** (runbook). Implemented as specified in `outcomes.apply_drift_ladder` (#419), all four branches unit-tested. |

## Components

1. **`infer.py`** — hash-verified production-model load; manifest assertion (feature-key mismatch ⇒ UNAVAILABLE); builds the pre-close feature vector from live IEX bars as of close−15m; writes a `market_projection_runs` row with `run_status ∈ SUCCESS/UNAVAILABLE/FAILED/SKIPPED`, `attempt_number` (multiple attempts kept; API serves latest SUCCESS), full probabilities stored for research, exact top-5 drivers (`attribution.logistic_drivers`), `source_json` provenance. Never fabricates (NFR-003).
2. **Jobs** (`market_projection_jobs.py`, env-gated `WORKBENCH_MARKET_PROJECTION_ENABLED`, default off): `mktproj_preclose` at 15:45 + 12:45 ET tick-and-check via `MarketSession` (mcal-authoritative since #410); `mktproj_outcomes` 18:30 ET; `mktproj_regime_report` monthly. All explicit-ET crons, max_instances=1, coalesce.
3. **Migration** — `market_projection_runs` per design §17.4 + review fields (`run_status`, `unavailable_reason`, `attempt_number`); unique `(projection_type, market_proxy, target_date, attempt_number)`.
4. **API** — `GET /api/v1/market-projection`: latest SUCCESS primary run → `p_material`, `elevated` flag, confidence, threshold, drivers, templated phrase, badge text, regime-limitation string, model/feature/label versions, `source_json`, last-updated. **Proposed (Q1): the API omits the UP/DOWN split entirely** — full probabilities stay in the DB for research; nothing directional is emitted where a UI could show it.
5. **Card** — `MarketProjectionCard.tsx`: badge ("Validated Move-Risk Projection — Primary Horizon Only" / "Research Preview — …" states incl. drift-downgraded and unavailable), P(MATERIAL) meter with the 0.5 threshold marked, templated phrase, confidence chip, top drivers, regime-limitation footnote, the standard two-line disclaimer. LOW confidence and "unavailable" designed as normal states. **Compliance wording review is the merge gate**; the NFR-006 forbidden-list test gains the five owner phrases (*predicts market direction / predicts crashes / works in bear markets / trading signal / buy-sell indicator*).
6. **Isolation CI** — `ci/check_market_projection_isolation.sh` (NFR-001): no order-path/risk/ranking/sizing/strategy module imports `app.services.market_projection`; wired into CI with the other invariants.
7. **Tests** — job tick-and-check (12:45 no-op on full days), hash-mismatch refusal, manifest-mismatch UNAVAILABLE, attempts/latest-SUCCESS API logic, outcome grading, forbidden-vocabulary scan (API strings + card constants), isolation check, drift-trigger unit test, card render states.

## Resolved questions (owner approval messages, 2026-07-11)

- **Q1 — RESOLVED**: the API omits UP/DOWN **entirely**. Serve only P(MATERIAL). No
  directional fields, labels, tooltips, or hidden API outputs. (Implemented in #419: the runs
  table keeps full probabilities for research/grading only; the served attribution vocabulary
  is `raises_move_risk` / `lowers_move_risk` — nothing directional exists in any payload.)
- **Q2 — RESOLVED**: approved non-elevated phrase: *"No elevated move-risk signal today."*
- **Q3 — RESOLVED, AMENDED** to the two-tier rule (verbatim in guardrail 8 above): warning at
  ≥0.5σ on a served day; auto-downgrade on 3-consecutive-day persistence, a single ≥1.0σ day,
  or >20% of manifest features ≥0.5σ the same day; restoration operator-only.
- **Q4 — RESOLVED**: promote artifact
  `5ec687017d9b7d4fd8af99a87ab2dae4184b1691e420d08b098fb76129a3bd95` only after full sha256 +
  provenance verification via the audited path (`promote_model.py` requires
  training-code/evidence/card commits + operator; registry `git_commit` backfilled; no
  retraining, no rebuild, no artifact substitution).

## Card wording constraints (owner-frozen; PR B's compliance test enforces these)

**May show:** Validated Move-Risk Projection — Primary Horizon Only · P(MATERIAL) ·
"Elevated move risk; direction uncertain." · "No elevated move-risk signal today." ·
the regime-limitation footnote.
**Must not show:** UP probability · DOWN probability · direction label · trade signal ·
buy/sell language · crash prediction · bear-market reliability claim · ensemble output ·
secondary horizon · LLM-generated explanation.

## Rollout (owner-approved Monday sequence)

1. Run the #407 Monday 08:50 ET probe → if it passes, merge #407.
2. Merge #419 (CI green + walk-away complete).
3. Deploy outside RTH.
4. Run the audited model promotion (full-hash + provenance).
5. Feature flag on → first live serve 15:45 ET.
6. Verify the API returns P(MATERIAL) only.
7. Grade the outcome next session.
8. Return PR B card wording for the final smoke/sign-off — **the card ships only after that**.

Registry headline updates to "§4 LIVE (Research Preview serving)" once verified.
