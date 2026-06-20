# P12 Direction Document v0.1 — Validation & Results (prove it's great)

| Field | Value |
|---|---|
| Document version | **v0.2 — draft + review fold** (2026-06-20). v0.1 was the first charter; v0.2 folds the doc review (`comments.md`, rated 10/10): a **Research methodology & governance** section (§4 — research invariants, statistical confidence, study lifecycle, Research Registry, evidence template, evidence versioning, Decision Register, negative findings, research KPIs), the **5 open questions resolved** with the reviewer's answers, the flagship **Strategy Evidence Book** as the phase deliverable, and the **roadmap reframe** (P13 Productization between P12 and Institutional Scale). The phase **number "P12" remains owner-confirmable** — this charter does not pivot the roadmap unilaterally (CLAUDE.md). |
| Date | 2026-06-20 |
| Phase | **P12 (proposed)** — Validation & Results (follows P11 Operations & Reliability) |
| Status | **Draft charter.** Next: owner confirms the sequence + the §7 open questions → then draft the §1 per-session doc (Edge evidence package, owner-selected first). |
| Predecessor | **P11** — Operations & Reliability — code-complete (§1–§5 merged + tagged `p11-session{1..5}-complete`). `p11-complete` is *pending* the ≥30-day Operational Readiness window (tracked here as the background track). |
| Successor | **P13 — Productization** (reviewer's reframe): once P12 proves the edge, the next step is turning the validated strategy into a polished product — *before* P14 Institutional Scale (HA/multi-account/admin). Roadmap: **P10 Portfolio Architecture → P11 Operational Trust → P12 Evidence & Validation → P13 Productization → P14 Institutional Scale.** Each beyond P12 is its own ADR/phase; numbers owner-confirmable. |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | **0014** (backtests = primary eval ground-truth), 0019 (Research Engine — read-only/alerts), 0002/0004 (router/breaker unchanged), 0021 (operational contract — the trust substrate that makes results *verifiable*). No new architectural invariant is expected this phase. |
| Inputs | The owner's directive (*"prove this app is great and will have some great results first"*); the factor-research findings ([[factor-research-program]] — momentum is the OOS edge; low-vol/reversal negative); the 28.5-yr / 39M-row survivorship-free store + the walk-forward harness already built; the live momentum-portfolio paper book (strategy id=2). |

---

## 0. Objective (the north star)

> **The objective of P12 is to prove — with verifiable, out-of-sample evidence — that the
> platform is both trustworthy and good: that it operates reliably AND that its strategy
> decisions carry a real, honestly-measured edge.**

P11 proved the platform is **trustworthy** (observable, reproducible, recoverable, auditable).
P12 proves it is **good** — worth trusting with capital. The two are complementary, and P11 is
what makes P12 *credible*: because every decision is replayable (§4) and every position
reconciled (§3), any result the platform reports is backed by an audit chain — **"here are the
results, and here is the proof they are real."** That verifiability is the differentiator, not a
bigger backtest number.

### Two honest kinds of proof (do not conflate them)

| Proof | What it demonstrates | How it is earned | What it is NOT |
|---|---|---|---|
| **Reliability** | the system executes decisions safely + observably over time | the ≥30-day Operational Readiness window (`p11-complete`) | evidence of edge |
| **Edge** | the strategy decisions have a real, persistent advantage | rigorous **out-of-sample / walk-forward** backtests on the deep survivorship-free history | a few weeks of paper P&L |

**The load-bearing caveat (stated up front so we never fool ourselves):** *a short paper-trading
window on ~$10k is statistical noise.* It proves the plumbing works (orders route, no incidents)
— it does **not** prove alpha. Defensible edge comes from out-of-sample backtest evidence over
many regimes, read with survivorship and look-ahead honesty. P12 holds itself to that bar (ADR
0014: backtests are the primary eval ground-truth).

## 1. Why this phase exists

The owner's framing: before any expansion (and explicitly before the Institutional Platform
direction), the platform must **demonstrate it is great and produces great results.** P11
finished the reliability story; the natural and necessary next step is the *results* story —
turning "it should perform well" into "here is the out-of-sample evidence that it does, and here
is the audit chain proving the evidence is real."

This is deliberately a **measurement-and-evidence phase**, not a feature phase. Most of its output
is reproducible studies, reports, and (where a study clears its gate) the *enabling* of an
already-built improvement — not new subsystems.

## 2. The workstreams (sequence — to be confirmed, then drafted as per-session docs)

Ordered for leverage. **§1 is owner-selected to go first.** The evidence harness built in §1 is
reused by §2/§3, so building it first is also the right dependency order.

1. **§1 — Edge evidence package (the baseline).** A rigorous, reproducible out-of-sample
   performance report for the **current** momentum-portfolio book on the 28.5-yr
   survivorship-free store + walk-forward: returns, Sharpe, max-drawdown, regime breakdown,
   turnover/cost, vs the SPY benchmark — with explicit survivorship/look-ahead/capacity caveats
   and the audit-replay chain cited as proof the live decisions match the studied logic. **This
   establishes the honest baseline and the reusable evidence harness.** *Owner-selected first.*
2. **§2 — Harden the live strategy (measure the lift).** Backtest-validate the default-off
   improvements already built — **vol-scaling** (the walk-forward showed it is a drawdown tool,
   consistent across regimes) and **sector caps** — through the §1 harness; enable each *only* if
   it clears its gate, and quantify the lift vs the §1 baseline. (ADR 0014 gate; conservative
   default stays off until proven.)
3. **§3 — Advance the alpha (the bigger edge).** The next factor-program step
   ([[factor-research-program]]): SF1 fundamentals → value/quality factors → a multi-factor book,
   each OOS-validated and combined with momentum. Larger eventual results story; the most research
   effort. Re-run the §1 harness on the multi-factor book.
4. **§4 — Operational-proof window (background, parallel).** Earn `p11-complete`: run the live
   paper book over the ≥30 consecutive days, keep the Operational Readiness Report all-PASS (no
   unresolved P1/P2), then sign the attestation. Runs concurrently with §1–§3 — it is mostly
   monitoring, and it supplies the *reliability* half of the proof.

(Each per-session doc is drafted only when its predecessor is far enough along; this charter does
not pre-draft them.)

## 3. What "great results," stated defensibly, looks like

The evidence package (§1, extended by §2/§3) should let the owner make claims of this shape — each
tied to an artifact, never an assertion:

- *"Over 1997–2026, across 5 regimes incl. GFC/COVID/2022, the momentum book delivered
  [Sharpe X, maxDD Y] vs SPY [.., ..], out-of-sample, survivorship-free — see `backtest run #N`."*
- *"Vol-scaling cut max-drawdown from Y to Y' in every regime (largest in crashes) at a Sharpe
  cost of Z — walk-forward n=.., see the §2 study."*
- *"The live paper book's decisions reproduce exactly under replay (§4) and reconcile against the
  broker (§3) — the results are verifiable, not just reported."*

What it will **not** claim: that a few weeks of paper P&L proves anything, or that a
survivorship-biased / look-ahead-tainted backtest is evidence. Honesty *is* the credibility.

## 4. Research methodology, registry & governance (the scientific rigor)

P12's credibility rests on *method*, not on any single number. This section is the standing
discipline every study inherits (folded from the doc review). It mirrors the P11 pattern of
registries + invariants + a standard artifact shape — applied to research instead of operations.

### Research invariants (non-negotiable — the research analogue of the recovery invariants)

1. **Never optimize on test data** — parameters are fit on train, never on the OOS window.
2. **Always preserve out-of-sample** — a held-out / walk-forward OOS segment is sacrosanct.
3. **Never cherry-pick periods** — report all regimes, not the flattering ones.
4. **Never suppress a negative study** — a rejected hypothesis is recorded, not deleted (§Negative findings).
5. **Every reported number is reproducible** — it traces to a versioned run (§Evidence versioning).

### Statistical confidence (the "could this happen by chance?" answer)

Headline edge claims carry a significance read, not just a point estimate: **confidence intervals
+ bootstrap of the return/Sharpe distribution + a p-value where appropriate + the distribution of
outcomes** (not only the mean). Investors will ask whether a result is luck; P12 answers it
quantitatively. (A Sharpe with no CI is a number, not evidence.)

### Study lifecycle — research is separated from production

Every factor/overlay moves through an explicit gate sequence; **`Research → Enabled` directly is
forbidden**:

```
Research ─▶ Validated (OOS clears the gate) ─▶ Production Candidate ─▶ Enabled (owner decision)
```

### Research Registry (single source of truth for "what's proven")

The standing table of studies and their lifecycle state — the research analogue of the
replay/feature/capability registries:

| Study | Status | Evidence |
|---|---|---|
| Momentum (6-1) | **Validated** | factor study; walk-forward (OOS edge) |
| Vol-scaling overlay | Pending (§2) | walk-forward = drawdown tool, not Sharpe booster |
| Sector caps | Pending (§2) | — |
| Quality factor | Research (§3) | — |
| Value factor | Research (§3) | — |
| Low-volatility | **Rejected** | negative OOS ([[factor-research-program]]) |
| Short-term reversal | **Rejected** | negative OOS |

### Evidence Package Template (every study has the same shape)

```
Objective ─▶ Dataset ─▶ Methodology ─▶ Results ─▶ Limitations ─▶ Decision ─▶ Recommendation
```

Consistency makes studies comparable and reviewable; an evidence doc that skips *Limitations* or
*Decision* is incomplete.

### Evidence versioning (reproducible forever)

Every report header pins the five coordinates that reproduce it: **dataset version · code version
· factor version · walk-forward version · report version.** (The operational analogue of §4
replay's `algorithm_version`/`registry_version` triple.)

### Decision Register (governance trail)

Every study ends with a one-row register entry — the auditable "why is this on/off":

| Study | Decision | Reason | Study # | Evidence |
|---|---|---|---|---|
| *(e.g.)* Vol-scaling | Enabled / Off | improved maxDD 18% / Sharpe cost too high | §2 | run id |

### Negative findings (institutional knowledge)

A standing **Negative Results** section across the phase — rejected and marginal studies are kept,
with the reason. (Low-vol → rejected; short-term reversal → rejected; sector caps → TBD.) Knowing
what does *not* work is as valuable as what does, and prevents re-running dead ends.

### Research KPIs (P12's measurable success, alongside P11's operational KPIs)

Validated-factor count · OOS Sharpe · walk-forward stability · turnover · max-drawdown · capacity.
These make "P12 succeeded" measurable, not a vibe.

## 5. Governing principles (inherited)

- **Backtests are the primary eval ground-truth** (ADR 0014); paper/live is confirmation of
  *plumbing*, not the alpha proof.
- **Out-of-sample or it doesn't count.** Walk-forward / true OOS; in-sample fits are not evidence.
- **Survivorship & look-ahead honesty.** Use the survivorship-free store; read results with the
  capacity/bias caveats stated. A result with a hidden bias is worse than no result.
- **Conservative defaults stay off until a study clears its gate** (improvements enabled only on
  evidence; the polarity never reverses).
- **Verifiability is the differentiator.** Every reported result traces to a reproducible run +
  (for live) the audit/replay/reconcile chain.
- **Operations never changes investment decisions** (P11 §5 / Direction): measuring does not alter
  what to trade.

## 6. Success criteria — evidence, not optimism

P12 succeeds when:
- a **reproducible edge-evidence report** exists for the live strategy, OOS + survivorship-free,
  with honest caveats (§1);
- each default-off improvement is **decided on evidence** — enabled with a quantified lift, or
  left off with the reason recorded (§2);
- the alpha program has advanced at least one validated factor beyond momentum (§3);
- `p11-complete` is signed off the ≥30-day all-PASS reliability window (§4);
- and every headline result is **traceable to a run id / audit chain** — verifiable on demand.

## 7. Definition of Done (phase exit)

**P12 is complete when** the owner can, for the live strategy, point to: (a) an OOS
survivorship-free performance report **with statistical-confidence analysis** (CIs/bootstrap/
p-value); (b) an evidence-based on/off decision for each built improvement, in the **Decision
Register**; (c) ≥1 validated additional factor in the **Research Registry**; (d) a signed
`p11-complete` reliability attestation; (e) a one-line provenance (versioned run id / audit) for
every headline number; and (f) the phase's flagship deliverable — the **Strategy Evidence Book**.
Returns themselves are **not** a gate — *defensible, verifiable evidence* is.

**Flagship deliverable — the Strategy Evidence Book.** P12 concludes with one comprehensive
document combining **operational proof (P11)** with **investment proof (P12)** — the artifact
shown to investors / partners / advisors / future team members:

```
Executive Summary ─▶ Research Results ─▶ Backtests ─▶ Walk-Forward ─▶ Risk
                  ─▶ Live Paper ─▶ Operational Proof ─▶ Final Conclusion
```

This is what makes the platform's case uncommon: a single body of evidence attesting *both*
operational reliability and investment methodology, every claim traceable to a run/audit.

## 8. Open questions — RESOLVED (2026-06-20)

1. **Benchmark & metrics → three benchmarks: SPY total-return + equal-weight universe (ADR 0014)
   + cash (0%).** Headline metrics: Sharpe + max-drawdown; full set also reports Sortino, Calmar,
   turnover, hit-rate. (Reviewer added the cash baseline for a comprehensive comparison.)
2. **Walk-forward spec → generalize the existing `walk_forward_vol_scaling.py` harness;
   n=80 / 5 windows for development iteration, n≈200 / 7 windows (full production config) for the
   final report.** Fast iteration, rigorous final validation.
3. **Report artifact → script → JSON → Markdown.** A script emits raw metrics to JSON (exactly
   reproducible); a Markdown study doc interprets them (the honest read). Notebooks only for
   exploratory research, never the headline artifact.
4. **Transaction costs → publish a sensitivity sweep: 5 · 10 · 20 · 50 bps** (not a single 10bps
   point), so readers see robustness and the capacity story is explicit.
5. **Universe → report both.** Headline = live top-200 (what actually trades — mirrors
   deployment); supporting appendix = full survivorship-free universe (broader robustness).

## 9. What this phase is NOT

- **Not** the Institutional Platform layer (multi-account/permissions/HA/scaling) — a separate
  pivot, each piece its own ADR, deferred and arguably off-thesis.
- **Not** new product features, new external dependencies, or new architecture.
- **Not** a claim that paper P&L proves edge — that is explicitly rejected (§0 caveat).
- **Not** enabling any default-off overlay without its study clearing the ADR 0014 gate.
- **Not** a live-capital decision — P12 produces the *evidence* a live decision would rest on; the
  decision itself is a separate, owner-gated step.

## 10. Notes & gotchas

1. **Paper ≠ proof of edge.** The single most important discipline of this phase — repeated here
   because it is the easiest mistake to make under "show me results" pressure.
2. **The harness is the asset.** §1's reusable evidence harness (one command → the metrics) is
   what makes §2/§3 cheap and the results trustworthy; invest in it being reproducible.
3. **Survivorship cuts both ways.** The store is survivorship-free; the *live top-200 universe* is
   today's names (survivorship-biased) — read each result for what it is (overlay-validation vs
   alpha claim), per the [[factor-research-program]] note.
4. **Don't re-litigate the architecture.** P11 froze the operational architecture; P12 measures on
   top of it. Any temptation to "add a metric/table to make measurement easier" should reuse the
   existing observability/audit, not extend it.
