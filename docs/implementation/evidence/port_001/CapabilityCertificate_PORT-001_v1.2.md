# Capability Certificate — PORT-001 **v1.2**

_Re-issues v1.1 after porting the **third** sibling lever. Supersedes `CapabilityCertificate_PORT-001_v1.1.md` (retained). With this, the platform `combined-book` carries all three of the sibling's live risk changes (KMLM + correlation-aware tilt + equity-beta-cap governor) — the governor **default OFF** pending a live dry-run._

| Field | Value |
|---|---|
| Capability | **PORT-001 — "Risk-Balanced Multi-Asset Portfolio"** (the Combined Book) |
| Capability class | Portfolio Construction (multi-sleeve ERC + crash / correlation / equity-beta overlays) |
| Certificate version | **v1.2 (Gate-Passed; lever #2 shipped default-OFF)** |
| Status | ✅ Onboarding Gate PASSED at v1.1 (9-asset construction-verification, 96.7%); v1.2 adds the equity-beta-cap governor as a **default-OFF** de-risk overlay |
| Date | 2026-07-03 |
| Supersedes | v1.1 (KMLM + tilt; Gate-Passed 2026-07-03) |
| Governing ADR | `docs/adr/0030-...` — **no new ADR** (de-risk-only construction step; not a risk-engine gate; no invariant change; no new external dependency) |

## What changed in v1.2 — sibling lever #2 (spec §11 #2 / §6.2)

**Look-through equity-beta-cap governor** (`app/research/factor_lab/beta_cap.py` `cap_equity_beta`): a
de-risk-only step in the live `_rebalance` that, when the book's look-through **equity-beta risk
contribution** exceeds a budget (0.80), scales the equity-beta names (single stocks + SPY/EFA/EEM) DOWN —
raising cash — until within budget. Bonds / gold / commodities / USD / **KMLM** untouched. Faithful port
of the sibling `portfolio_riskmodel.cap_equity_beta` (sample covariance + off-diagonal shrink + masked
risk-contribution via the reused `erc.risk_contributions` + monotone bisection). Directly addresses the
capability's headline disclosure **§6.2** (equity sleeve ≈ 13% of capital but the majority of risk).

**Posture: DEFAULT OFF.** Shipped `enforce_beta_cap=False` (book unchanged) with `beta_cap_report_only=True`
so the would-be haircut is **logged on the live book** (the dry-run) before the owner enables it — mirrors
the sibling's built-off → validated → enabled path. Template `version` → **1.2.0**.

**Honest value:** with the correlation-aware tilt already live, the governor's *current* effect is small
(sibling: ~1.4% freed, equity-beta RC 83%→80%). Its worth is a **standing safety net** against future
equity-beta drift + closing §6.2 + completing sibling parity — not a large immediate reweight.

## Maturity (L0–L5)

Unchanged from v1.1: **L3 (Paper operational).** L1/L2 gate evidence stands on the v1.1 9-asset
construction-verification. The governor is a default-OFF overlay; its **live dry-run** (report-only log on
the Monday book) is the platform-side validation before it is enforced — analogous to the sibling's real-book
check. Enforcing it is an owner-gated param flip, no code change.

## Evidence

- Governor unit tests `tests/research/factor_lab/test_beta_cap.py` (de-risk-only, mask, bisection, fail-open).
- Synthetic demonstrator `scripts/verify_beta_cap.py` → `port001_beta_cap_synthetic.json` (equity-beta RC
  1.08 → 0.80, only equity names scaled, hedges untouched, cash freed).
- Live dry-run: `combined_book.py` `beta_cap_report_only` logs the real book's equity-beta RC + would-be
  haircut each rebalance (governor OFF → book unchanged).
- Package: `EvidencePackage_PORT-001_v1.2.md`.

## Honest verdict (unchanged)

**Crash-protected beta + diversification, NOT alpha.** All three levers are risk management (drawdown /
concentration control), not an alpha source.

_v1.2 — 2026-07-03. Re-issued on porting lever #2 (default-OFF, pending the live dry-run before enforcement)._
