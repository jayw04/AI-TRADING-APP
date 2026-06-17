# Promotion workflow (Research Engine, P10 Phase 2 §3)

How a research idea moves from a hypothesis to live capital, and who/what acts at
each stage. The **promotion gate** (`app/research/promotion/gate.py`) automates the
*research* transitions; **deployment** transitions are owner-driven (the gate
validates; it never deploys).

Two orthogonal lifecycle axes (registry §1):

- **research_state**: `RESEARCH → VALIDATED → REJECTED → ARCHIVED`
- **deployment_state**: `NONE → PAPER → CANARY → LIVE → RETIRED`

Every transition records a **reason** in the `transitions` log.

## Stages

| Stage | Who/what | Action | State change |
|---|---|---|---|
| **Research** | orchestrator (§2) | run the experiment, record metrics + artifacts | research=RESEARCH |
| **Gate** | `gate_experiment()` | apply the profile; compute confidence 0–100; verdict GO / GO_WARNING / NO-GO / INCONCLUSIVE | research → VALIDATED (GO/GO_WARNING) or REJECTED (NO-GO); INCONCLUSIVE stays RESEARCH |
| **Paper** | owner | promote a VALIDATED strategy to paper trading | deployment NONE → PAPER |
| **Paper validation** | revalidation (§4) | the strategy meets its live metrics in paper over a watch window | (monitored; alert on breach) |
| **Promotion review** | owner | review paper evidence + confidence score; decide live candidacy | deployment PAPER → CANARY (optional small-size) |
| **Live** | owner | full deployment | deployment CANARY → LIVE |
| **Monitoring** | revalidation (§4) | continuous monthly revalidation; Research Alert on edge decay | (alert; may propose RETIRED) |
| **Retirement** | owner | edge decayed / superseded | deployment → RETIRED; research → ARCHIVED |

## The gate verdicts

- **GO** — all criteria pass and the sample is strong (evidence ≥ strong threshold). VALIDATED.
- **GO_WARNING** — all criteria pass but the sample is thin (floor ≤ evidence < strong). VALIDATED, **but owner signoff required** before paper.
- **NO-GO** — at least one criterion fails. REJECTED.
- **INCONCLUSIVE** — below the evidence floor (can't pass or fail). Stays RESEARCH; gather more evidence (widen window, more trades).

Profiles (`PROFILES`): `book_backtest` is the faithful port of the §5c
pre-registered criteria (PF≥1.3, win≥0.45, payoff≥1.0, expectancy≥0.15R,
maxDD≤8%, OOS PF ≥ max(1.0, 0.8·IS PF), coverage≥0.97, robustness ≥0.8×, trade
floor 30 / strong 50). `factor_ic` gates a single factor (OOS IC>0, OOS
LS-Sharpe≥0.5, IC hit≥50%, rolling-12m IC positive ≥60%).

## Confidence score (0–100)

The weight-weighted fraction of a profile's criteria that pass — OOS/robustness
criteria are weighted higher (2×). It is **advisory** (surfaced on the dashboard
and in promotion review), not a gate by itself: the verdict gates; the score ranks.

## Discipline

- **Tighten, don't loosen** profile thresholds after seeing results (the §5c rule).
- The gate is read-only/off the order path; **no automatic deployment or
  retirement** — every deployment-axis move is an owner decision with a recorded
  reason. Continuous revalidation (§4) may *propose* RETIRED via an alert, never
  execute it.
