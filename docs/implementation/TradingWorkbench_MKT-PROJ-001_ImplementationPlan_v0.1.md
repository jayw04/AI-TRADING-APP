# MKT-PROJ-001 — Market Projection Engine: Implementation Plan

| Field | Value |
|---|---|
| Document version | v0.1 (draft — for owner review; execution starts only after the §0 freeze) |
| Date | 2026-07-10 |
| Program | MKT-PROJ-001 (design: `Docs/design/TradingWorkbench_MarketProjectionEngine_RequirementsDesign_v0.2.md`) |
| Capability | CAP-TBD — Market Projection Engine (id assigned at registry entry) |
| Sessions | §0–§5, one or more PRs each (~6 PRs total) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Build the v0.2 design end-to-end: PIT dataset → baselines → walk-forward → calibrated ML + attribution → scheduled inference → API + Research Preview card → realized-outcome tracking → evidence verdict |
| Estimated wall time | 27–42 hours across sessions (each session 3–9h; see per-session estimates) |
| Tag on completion | `mkt-proj-001-s<N>-complete` per session; `mkt-proj-001-built` when §4 ships |
| Out of scope | Everything in design §4.2, plus: SHAP library, new paid data, futures/VIX/options features, any trading integration (that is MKT-PROJ-STRAT-001, a separate future program) |

---

## Why this plan exists

Design v0.2 (§23) instructs the development team to produce an implementation plan covering
modules, data, features, labels, models, validation, floors, attribution, jobs, API/UI, tests,
rollout, and open questions. This document is that plan, grounded in what the platform actually
has today (verified 2026-07-10): `MarketSession` already does holiday/half-day classification
(mcal-backed, 13:00 ET early close), the factor store cannot supply ETF history (Sharadar SEP is
stocks-only; no SFP), Alpaca is the ETF price source (SIP *historical* permitted, IEX real-time
only — confirmed live by the GAP-NATIVE-001 probe), and the backend has numpy/pandas/pandas-ta
but **no scikit-learn**.

The realistic prior (design §3) is Rejected/Inconclusive on direction. The plan treats that as a
first-class outcome: the evidence harness (§1–§3) is the product's spine; the display surface
(§4) is honest at every evidence state, starting at Research Preview.

## What this program ships (mapped to design MVP criteria §21)

1. Pre-registration + frozen primary configuration (§0) — criteria 1, 2, 6.
2. PIT training dataset + UP/DOWN/NEUTRAL labeler with PIT ATR threshold (§1) — criteria 3, 4.
3. Baselines + walk-forward harness with magnitude/direction decomposition + sample floor (§2) — criteria 5, 7, 8, 9.
4. Calibrated ML models + attribution payload (§3) — criteria 10, 11.
5. Scheduled inference + API + dashboard card + compliance wording (§4) — criteria 12, 13, 14, 15.
6. Realized-outcome tracking + rolling calibration + evidence package + verdict (§4/§5) — criteria 16, 17.

---

## Proposed files/modules (design §17.1, adjusted to repo conventions)

```text
apps/backend/app/services/market_projection/
  __init__.py
  schemas.py            # typed payloads: ProjectionRecord, Drivers, TrainingRow, enums
  labels.py             # PIT ATR threshold + UP/DOWN/NEUTRAL labeler (both horizons)
  features_preclose.py  # intraday features as-of close_minus_15m (FR-003)
  features_preopen.py   # gap + prior-day features as-of 09:20 ET (FR-004)
  dataset.py            # historical dataset builder → market_projection_training_rows
  baselines.py          # the 6 pre-registered baselines (FR-005)
  validate.py           # walk-forward engine + §13 metrics + §14 sample floor
  train.py              # logistic regression + HistGradientBoosting + calibration (FR-006)
  attribution.py        # coef×std-value, model-native importances, permutation (FR-008)
  infer.py              # load registry model → daily projection record (FR-009)
  explain.py            # LLM formatter over the attribution payload ONLY (§10.3; flag-gated)
  model_registry.py     # artifact store + market_projection_model_registry table access
  outcomes.py           # realized-outcome finalizer (FR-013)

apps/backend/app/jobs/market_projection_jobs.py   # 3 scheduled entry points (§17.3)
apps/backend/app/api/v1/market_projection.py      # GET /api/v1/market-projection (FR-011)
apps/frontend/src/components/MarketProjectionCard.tsx  # Research Preview card (FR-010)

apps/backend/alembic/versions/  # 3 migrations: training_rows, runs, model_registry (§17.4)
scripts/research/mkt_proj_001/  # build_dataset.py, run_validation.py, train_models.py,
                                # make_evidence.py (evidence artifacts → the evidence dir)
docs/implementation/TradingWorkbench_MKT-PROJ-001_PreRegistration_v0.1.md
docs/implementation/evidence/mkt_proj_001/   # walk-forward JSON, result md, model card
ci/check_market_projection_isolation.sh      # NFR-001 order-path isolation (see Tests)
```

Notes vs the design's sketch: evidence lives under `docs/implementation/evidence/` next to the
other programs' artifacts rather than a new top-level `evidence/`; research runners live in
`scripts/research/` (the GOVCONTRACT/TREND pattern) so heavy dataset/training work never runs
inside a request path.

## Data sources (design §9, verified against the platform)

| Need | Source | Notes |
|---|---|---|
| Daily OHLCV, SPY/QQQ/IWM/DIA + 11 SPDR sector ETFs | Alpaca historical (SIP-delayed) | Factor store can't serve ETFs (no SFP). ~2016→today ≈ 10y. |
| Intraday bars (pre-close features) | Alpaca historical minute/5-min (SIP-delayed) | Fetch in monthly chunks in `dataset.py` — NEVER a naive multi-year query (the bar_cache 10k-truncation gotcha). |
| Live inference bars (09:20 / 15:45 snapshots) | Alpaca real-time (IEX feed) | Train/serve provenance difference (SIP-historical vs IEX-live) recorded in `source_json` + quality flags per §9.3; SPY/QQQ/sector ETFs are liquid enough on IEX for index-level features. |
| Premarket gap (pre-open features) | Alpaca snapshots (IEX) | Same quality-flag rule; the GAP-NATIVE probe already characterizes IEX premarket behavior. |
| Exchange calendar / half-days | `app/market/session.py` (`MarketSession`) | Already handles holidays + 13:00 early closes; no new dependency. |
| SCAN/GAPPER shadow features | gate evidence records + shadow ledger + native gapper files | **Shadow rows only** (§8.4 Policy A); never in the displayed model. |

**No new external service.** One new Python library: `scikit-learn` (see Open questions Q1).

## Feature policy (design §8 — enforced in code, not just prose)

- `TrainingRow.features_json` carries a `feature_version`; the production model's feature list
  is frozen in the pre-registration and asserted at inference: `infer.py` refuses to run if the
  live feature vector's keys ≠ the registry model's `feature_version` manifest (fail-soft:
  "Projection unavailable — feature mismatch").
- Shadow features live in a *separate* column namespace (`shadow_features_json`) and a separate
  shadow model id; the API never returns shadow model output. Promotion path per §8.4 only.
- Every feature function takes `(bars, as_of)` and is unit-tested for PIT: given data past
  `as_of`, output must be identical to data truncated at `as_of` (the leakage test pattern).

## Label construction (design §5.3, §6, FR-002)

- `threshold_t = max(0.60%, 0.50 × ATR20_pct_t)`, ATR20 through **t−1** only (PIT), computed
  from the same daily-bar series the features use.
- PRE_CLOSE_TOMORROW label: close(t+1) vs close(t). PRE_OPEN_TODAY label: close(t) vs
  regular-session open(t) — open-to-close, the v0.2 leakage fix.
- Half days: label uses the actual early close; days where the market is closed produce no row.
  Rows with data-quality exclusions carry `valid_for_training=false` + `exclusion_reason`
  (missing bars, split anomalies) rather than being silently dropped.
- Sensitivity labeler: fixed ±0.75% behind the same interface (one parameter object, frozen
  in pre-registration; the dynamic threshold is primary).

## Model approach (design §10, FR-005/006)

- **Baselines (all six, pre-registered):** Always-Neutral; unconditional class frequencies;
  prior-day direction; 5-day momentum direction; volatility-clustering move-risk (P(MATERIAL)
  from recent realized vol quantile); premarket-gap direction (PRE_OPEN only). The binding gate
  compares against the **best** of these per metric (design §0.5).
- **ML:** scikit-learn `LogisticRegression` (L2, standardized features) and
  `HistGradientBoostingClassifier`, each wrapped in `CalibratedClassifierCV` (isotonic for the
  boosted model, Platt for logistic) fitted walk-forward-safely (calibration split inside each
  training window only). Three-class output; `P(MATERIAL) = P(UP)+P(DOWN)`.
- **No deep nets, no SHAP dependency** in v1 (attribution below covers §10.2 with what sklearn
  provides). Simple average ensemble of the two calibrated models is computed and reported but
  is NOT the primary unless pre-registered as such — one primary model is frozen in §0.
- Artifacts: joblib dumps under `data/market_projection/models/` with sha256 in the registry
  row; `model_version = {model_type}-{feature_version}-{train_window}-{git_short}`.

## Validation plan (design FR-007, §13)

- Walk-forward: anchored expanding window — train on years [start, k], test on the next 6
  months, roll by 6 months, aggregate all out-of-sample periods. First train window ≥3 years.
  (~2016 start ⇒ roughly 2019–2026 ≈ 14 test folds ≈ 1,750 OOS days.)
- Metrics computed per fold and pooled, magnitude and direction **separately** (§13.1/13.2):
  Brier/log-loss/ECE/AUC for MATERIAL-vs-NEUTRAL; UP/DOWN precision, balanced accuracy,
  uplift vs best baseline, FPR, confusion matrix, mean realized move after calls; three-class
  Brier/log-loss + reliability curves (§13.3).
- CIs: stationary block bootstrap over OOS days (block ≈ 10 trading days) for improvement-vs-
  best-baseline deltas; the gate needs the CI to exclude zero (§15).
- Regime slices reported (not gated numerically, reviewed per §15 "no major regime failure"):
  calendar year, high-vs-low VIX-proxy (realized-vol) halves, up-vs-down 200dma regime.

## Sample floors (design §14 — enforced, not advisory)

`validate.py` computes directional metrics only when OOS non-neutral calls ≥100 with ≥50 UP and
≥50 DOWN; otherwise the directional verdict field is the literal `insufficient_sample` and no
directional CI appears anywhere in the evidence package or API. The floor check is unit-tested.

## Attribution method (design §10.2, FR-008)

- Logistic: per-feature `coef × standardized value` for the predicted class (exact, cheap,
  per-projection).
- Boosted: per-projection attribution via sklearn's `partial_dependence`-free fallback —
  feature contributions approximated by single-feature perturbation against the day's vector
  (documented approximation), plus batch-level `permutation_importance` in the evidence package.
- Payload shape exactly as FR-008 (`feature`, `direction: supports_<LABEL>`, `weight`, `value`),
  top-5 by |weight|, stored in `drivers_json`. `explain.py` receives ONLY this payload + the
  probabilities; its prompt forbids anything not in the payload, output length-capped; the whole
  LLM step is optional and flag-gated (`WORKBENCH_MKTPROJ_LLM_EXPLAIN`), default off
  (conservative default; the card renders drivers without prose when off). LLM calls audited
  (cost, model, prompt/response) via the existing app/llm plumbing.

## Scheduled jobs (design §17.3, using the platform's proven patterns)

| Job id | Time (ET) | What |
|---|---|---|
| `mktproj_preopen` | 09:20 mon–fri | PRE_OPEN_TODAY inference → runs row |
| `mktproj_preclose` | 15:45 mon–fri **and** 12:45 mon–fri | PRE_CLOSE_TOMORROW inference; each fire asks `MarketSession` whether it is exactly close−15m for today (full vs half day) and no-ops otherwise — the tick-and-check pattern, so half days are handled without dynamic cron rewriting |
| `mktproj_outcomes` | 18:30 mon–fri | finalize labels for matured projections (FR-013) |

All three: explicit `timezone="America/New_York"` on every CronTrigger (the #405 UTC-drift
lesson), `max_instances=1`, `coalesce=True`, fail-soft (a failed inference writes
"Projection unavailable + reason", never a fabricated projection — NFR-003), env-gated
`WORKBENCH_MARKET_PROJECTION_ENABLED` default off (hermetic CI, box opt-in — the insider/
gap-native pattern). Latency budget (NFR-005) is trivially met: features are a handful of bar
queries; inference is a sklearn predict.

## API / UI changes

- `GET /api/v1/market-projection` (FR-011): latest (or `date=`) run per `projection_type` /
  `market_proxy`; returns probabilities, label, display phrase, confidence (§18 mapping),
  threshold, drivers, optional llm_explanation, model/feature/label versions, evidence status,
  source provenance. Read-only, no auth beyond the session (mirrors /benchmarks).
- `MarketProjectionCard.tsx` (FR-010): the two projections side by side, probability bars,
  P(MATERIAL), confidence chip, threshold, top drivers, evidence-status badge, last-updated,
  and the fixed two-line disclaimer. Wording passes the same advice-adjacent review as the
  Opportunity Report (NFR-006 vocabulary enforced by a frontend constant + a backend test that
  scans display phrases against the forbidden list). Design must read naturally when confidence
  is LOW every day (§18 reality check) and when the API returns "Projection unavailable".

## Storage (design §17.4)

Three Alembic migrations (reviewed by hand per repo convention, `alembic heads` before writing —
the 7/7 non-head gotcha): `market_projection_training_rows`, `market_projection_runs`,
`market_projection_model_registry`, fields exactly as design §17.4 (runs.id as UUID pk;
`(projection_type, market_proxy, as_of.date)` unique on runs; `(date, projection_type,
market_proxy, feature_version)` unique on training rows). Projections are research artifacts,
not consequential actions — no audit-log entries for routine runs; model registry
status changes (a new production model) ARE audit-logged (MODEL_REGISTERED action + runbook
scenario, per the audit-log skill checklist).

## Tests (per session; the repo bar)

- **PIT/leakage:** every feature fn + labeler: truncated-vs-full-data equality at `as_of`;
  ATR threshold uses t−1; pre-open features contain no post-09:20 data; pre-close no post-15:45.
- **Labeler:** threshold math both regimes (0.60% floor vs ATR-scaled), half-day close, no-row
  on holidays, exclusion_reason paths.
- **Walk-forward harness:** fold boundaries never overlap, calibration fits inside train only,
  metrics reproduce on a synthetic dataset with known answers (e.g. a planted signal the
  harness must find, and pure noise it must NOT find), sample-floor enforcement, best-baseline
  gate picks the max per metric.
- **Baselines:** each baseline's predictions on hand-computable fixtures.
- **Attribution:** logistic attribution equals coef×std-value analytically; payload schema.
- **Inference job:** feature-manifest mismatch → unavailable; missing bars → unavailable +
  reason; registry resolution; tick-and-check half-day logic (12:45 no-ops on a full day).
- **API:** shape, filters, forbidden-vocabulary scan of display phrases.
- **Isolation (NFR-001):** `ci/check_market_projection_isolation.sh` — no order-path/risk/
  ranking/sizing/strategy module imports `app.services.market_projection` (mirrors
  `check_altdata_order_path_isolation.sh`; adding a CI invariant is additive — no ADR needed).
- Frontend: card renders all evidence states + unavailable state (component test).

## Rollout plan

Session sequence (each = its own PR(s), tagged, ≥1h walk-away; §1–§3 are research-code PRs,
§4 touches the product surface → 2h walk-away):

| Session | Ships | Est. |
|---|---|---|
| **§0 Pre-registration + data audit** | Pre-registration doc (frozen labels/threshold/primary config/baselines/feature manifest/shadow list); data-audit script proving ETF daily+minute depth ~2016→now and gap quality; scikit-learn dependency added + pinned; program + capability registered (Planning) in `research/programs.py`/registry | 2–3h |
| **§1 Dataset + labels** | `schemas/labels/features_*/dataset` + training-rows migration + builder script + PIT tests; dataset built on the box (SIP-historical) | 5–8h |
| **§2 Baselines + walk-forward** | `baselines/validate` + metrics/floors/bootstrap + synthetic-data harness tests + baseline-only evidence run (this alone answers "how hard is the target") | 5–8h |
| **§3 ML + calibration + attribution** | `train/attribution/model_registry` + registry migration + full walk-forward evidence package v1 + model card; **owner checkpoint: review evidence before building the surface** | 6–9h |
| **§4 Inference + API + card** | `infer/explain/outcomes` + jobs + runs migration + endpoint + card + compliance review + isolation CI check + box deploy (flag on) | 6–9h |
| **§5 Evidence review + lifecycle** | Verdict scripts (move-risk and direction separately, §15), registry status update, CEE hook for rolling calibration drift, decision summary | 3–5h |

Deploy per the standard box recipe (outside RTH, ≥60min from rebalances). After §4, the card
runs as Research Preview regardless of §5's verdict — the verdict changes the *badge*, never
retroactively the claims. Forward realized-outcome accrual starts the day §4 deploys.

## Open questions (blocking §0 freeze — owner answers wanted)

1. **scikit-learn dependency** — pure-Python/compiled lib, no network, pinned. OK to add? (No
   external *service*, so no ADR per the dependency rule; flagging because deps are curated.)
2. **History start** — Alpaca gives ~2016+. With ~40% material days, the §14 directional floor
   (50/50/100) will be met, but power for *uplift CIs* is modest. Accept ~10y, or source longer
   daily history (pre-close intraday features would still cap the intraday-feature era)?
3. **LLM explanation in v1** — build `explain.py` but ship flag-off (my recommendation:
   drivers table reads fine without prose; zero LLM cost until wanted), or enable from day 1?
4. **Sector basket freeze** — the 11 SPDR sector ETFs (XLK/XLF/XLV/XLE/XLI/XLY/XLP/XLU/XLB/
   XLRE/XLC; XLRE/XLC only exist from 2015/2018 — breadth features must handle a changing
   basket PIT). Confirm this basket for the freeze.
5. **Primary model** — freeze which single model is *the* primary for the gate (my
   recommendation: calibrated logistic — most transparent, exact attribution; boosted +
   ensemble as pre-registered secondaries).
6. **Secondary proxies/horizons in v1 build** — QQQ + fixed-threshold sensitivity are cheap to
   run in §2/§3; DIA/IWM/sector-basket proxies deferred to §5 unless asked. Confirm.
7. **Confidence mapping** (§18 thresholds) — accept as-is for v1 display? It is display-only,
   so it can be frozen loosely, but freezing avoids later "tuning after seeing results" optics.

## Notes & gotchas (inherited platform lessons this plan must respect)

1. Cron timezone: every trigger gets explicit `America/New_York` (#405).
2. bar_cache multi-year intraday truncation: dataset builder fetches monthly chunks directly.
3. `alembic heads` (not `ls -t`) before writing migrations (7/7 gotcha).
4. IEX-vs-SIP train/serve provenance goes in `source_json` on every run (design §9.3).
5. Env-gated scheduling keeps CI hermetic (insider/gap-native pattern).
6. No parameter tuning after seeing validation results (design §4.2) — hyperparameters are
   frozen in the pre-registration; the walk-forward harness runs them once.
7. The realistic outcome is Rejected/Inconclusive on direction (design §3) — §2's
   baseline-only run lands *before* any ML is built, so expectations are calibrated early and
   cheaply.
