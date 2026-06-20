# P12 Direction Document v0.1 — Validation & Results (prove it's great)

| Field | Value |
|---|---|
| Document version | **v0.1 — draft for confirmation** (2026-06-20). Open questions (§7) to resolve before drafting per-session docs. The phase **number "P12" is the owner's to confirm/rename** — this charter does not pivot the roadmap unilaterally (CLAUDE.md). |
| Date | 2026-06-20 |
| Phase | **P12 (proposed)** — Validation & Results (follows P11 Operations & Reliability) |
| Status | **Draft charter.** Next: owner confirms the sequence + the §7 open questions → then draft the §1 per-session doc (Edge evidence package, owner-selected first). |
| Predecessor | **P11** — Operations & Reliability — code-complete (§1–§5 merged + tagged `p11-session{1..5}-complete`). `p11-complete` is *pending* the ≥30-day Operational Readiness window (tracked here as the background track). |
| Successor | TBD — explicitly **not** the Institutional Platform layer (multi-account/HA/permissions); that is a separate pivot, each piece its own ADR, and arguably counter to the product's "local-first, individual trader" identity. |
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

## 4. Governing principles (inherited)

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

## 5. Success criteria — evidence, not optimism

P12 succeeds when:
- a **reproducible edge-evidence report** exists for the live strategy, OOS + survivorship-free,
  with honest caveats (§1);
- each default-off improvement is **decided on evidence** — enabled with a quantified lift, or
  left off with the reason recorded (§2);
- the alpha program has advanced at least one validated factor beyond momentum (§3);
- `p11-complete` is signed off the ≥30-day all-PASS reliability window (§4);
- and every headline result is **traceable to a run id / audit chain** — verifiable on demand.

## 6. Definition of Done (phase exit)

**P12 is complete when** the owner can, for the live strategy, point to: (a) an OOS
survivorship-free performance report; (b) an evidence-based on/off decision for each built
improvement; (c) ≥1 validated additional factor; (d) a signed `p11-complete` reliability
attestation; and (e) a one-line provenance (run id / audit) for every headline number. Returns
themselves are **not** a gate — *defensible, verifiable evidence* is.

## 7. Open questions (resolve before drafting the §1 per-session doc)

1. **Benchmark & metrics set** — SPY total-return as the single benchmark, or also an
   equal-weight-universe baseline (ADR 0014 already defines the EW baseline)? Which headline
   metrics (Sharpe, Sortino, maxDD, Calmar, turnover, hit-rate)? *Lean: SPY + EW baseline; the
   full set, with maxDD and Sharpe as headline.*
2. **Walk-forward spec** — reuse the existing `walk_forward_vol_scaling.py` harness generalized,
   n and window count (the n=200×7 full run was ~1–2h; n=80/5-window was used before)? *Lean:
   generalize the harness; n=80/5-window for iteration, one n≈200 confirmation run for the report.*
3. **Report artifact form** — a `docs/implementation/..._Results_v0.1.md` study doc, a committed
   notebook, or a generated report from a script? *Lean: a script that emits the numbers +
   a study-doc that interprets them (script = reproducible, doc = the honest read).*
4. **Capacity/cost realism** — what fill/slippage/commission model for the headline run (the
   backtest uses flat 10bps/rebalance today)? *Lean: keep 10bps for the baseline, add a
   sensitivity row at higher cost so capacity caveats are explicit.*
5. **Universe for the report** — the survivorship-free 14k-name pool, or the live top-200 paper
   universe? *Lean: report the live-universe result as the headline (it's what trades) + the
   broad-universe result as the robustness check.*

## 8. What this phase is NOT

- **Not** the Institutional Platform layer (multi-account/permissions/HA/scaling) — a separate
  pivot, each piece its own ADR, deferred and arguably off-thesis.
- **Not** new product features, new external dependencies, or new architecture.
- **Not** a claim that paper P&L proves edge — that is explicitly rejected (§0 caveat).
- **Not** enabling any default-off overlay without its study clearing the ADR 0014 gate.
- **Not** a live-capital decision — P12 produces the *evidence* a live decision would rest on; the
  decision itself is a separate, owner-gated step.

## 9. Notes & gotchas

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
