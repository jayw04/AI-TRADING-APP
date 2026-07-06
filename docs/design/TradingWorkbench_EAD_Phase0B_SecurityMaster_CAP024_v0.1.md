# TradingWorkbench — EAD Phase 0B: Point-in-Time Security Master (CAP-024) v0 design

| Field | Value |
|---|---|
| Document version | v0.1 (design for build) |
| Date | 2026-07-05 |
| Capability | **CAP-024 — Point-in-Time Security Master** (new Platform Capability; ADR 0037 Decision 9) |
| Status | **Design.** No code yet. A minimal v0 resolver — deliberately *not* CRSP-grade corporate-action mastery. |
| Authority | ADR 0037 (Accepted 2026-07-05) Decision 9 + review point on the fuzzy tier |
| Related | ADR 0027 (`CikMap`, the CIK/ticker backbone this reuses), ADR 0030 (Platform-Capability register — CAP-024 lives here), ADR 0037 Decisions 8/9/11, Phase 0A (writes `resolved_security_id`/`unresolved_reason` into `corporate_events`) |

---

## 0. Purpose & scope

Alternative data arrives keyed by inconsistent identity: SEC by **CIK**, price/factor data by **ticker**, Quiver government contracts by **company/recipient name** (often a subsidiary or legal entity, sometimes with a UEI). Every EAD event must resolve to a stable security identity *or* be explicitly, typed-unresolved — because a **silent bad mapping fabricates an event study**. CAP-024 is that resolver.

**v0 is minimal on purpose** (ADR 0037: "do not overbuild v0"). It resolves the common cases and *labels* the rest. It does **not** yet solve historical ticker reuse, mergers, delistings, or subsidiary→parent mapping; those are named as reserved reasons and v1 work (§6). The one non-negotiable v0 property: **no silent bad mapping** — every uncertain case returns unresolved with a typed reason, never a confident-looking wrong id.

---

## 1. Contract

```python
# app/altdata/security_master.py  (placement — §9)

@dataclass(frozen=True)
class ResolutionResult:
    resolved_security_id: str | None   # canonical id (§7); None when unresolved
    resolved_ticker: str | None
    cik: int | None
    confidence: float                  # [0.0, 1.0]; 0.0 when unresolved
    method: str                        # 'cik' | 'ticker' | 'exact_name' | 'fuzzy_name' | 'unresolved'
    unresolved_reason: str | None      # typed (§3); None when resolved

    @property
    def is_resolved(self) -> bool:
        return self.resolved_security_id is not None


class SecurityMaster:
    def resolve_security(
        self,
        *,
        issuer_name: str | None = None,
        ticker: str | None = None,
        cik: int | None = None,
        as_of: date | None = None,     # carried through v0 (§6); honored in v1
    ) -> ResolutionResult: ...
```

Pure, deterministic, read-only, off the order path (covered by the ADR 0037 Decision 11 CI invariant). Constructed from a `CikMap` (and, later, a ticker-history table). No network in the hot path — the `CikMap` is loaded once.

---

## 2. Resolution hierarchy (ADR 0037 Decision 9)

First tier that produces a confident match wins; otherwise fall through to unresolved. Every tier is exact except the last.

| Order | Tier | Input used | Source | `method` | `confidence` |
|---|---|---|---|---|---|
| 1 | **CIK** | `cik` | `CikMap.titles` (is it a known filer?) | `cik` | `1.00` |
| 2 | **Ticker (exact)** | `ticker` | `CikMap.by_ticker` | `ticker` | `0.99` |
| 3 | **Exact normalized name** | `issuer_name` | normalized-title → cik index (§4) | `exact_name` | `0.95` |
| 4 | **Fuzzy name (gated)** | `issuer_name` | best normalized-title similarity (§5) | `fuzzy_name` | = similarity score (only if ≥ threshold) |
| 5 | **Unresolved** | — | — | `unresolved` | `0.00` |

Tiers 1–2 are direct `CikMap` lookups. Tier 3 builds a reverse index `normalized(title) → {cik}` once from `CikMap.titles`. Tier 4 (§5) is the only inexact tier and is threshold-gated. A tier-1/2 hit that also disagrees with a supplied name is still resolved on CIK/ticker (the harder identifier wins) — but the disagreement is worth logging for the data-quality report.

---

## 3. Typed unresolved reasons — reachable in v0 vs reserved

`unresolved_reason ∈ { ambiguous_name | no_public_security | subsidiary_unmapped | ticker_reused | insufficient_confidence }`.

| Reason | Meaning | v0 status |
|---|---|---|
| `ambiguous_name` | normalized name matches **>1** distinct CIK | **reachable** (tier 3/4 collision) |
| `no_public_security` | name/ticker/CIK matched nothing public | **reachable** |
| `insufficient_confidence` | best fuzzy similarity **< threshold** | **reachable** (tier 4 floor) |
| `subsidiary_unmapped` | recipient is a subsidiary/division of a public parent | **reserved** — needs a subsidiary→parent map (v1); v0 emits `no_public_security` or `insufficient_confidence` for these |
| `ticker_reused` | ticker valid but reassigned across the `as_of` boundary | **reserved** — needs ticker-change history (v1); v0 cannot detect it |

Reserving two reasons (rather than dropping them) keeps the enum stable so v1 can start emitting them without a schema change. The data-quality report (§10) counts each reason so the reserved-vs-reachable gap is visible, not hidden.

---

## 4. Name normalization (deterministic, zero-dependency)

The one place sloppiness creates silent bad mappings, so it is explicit and tested:

1. Uppercase; NFKD-fold accents; replace `&`→`AND`.
2. Strip punctuation to spaces; collapse runs of whitespace.
3. Drop a trailing corporate-suffix token set: `INC CORP CORPORATION CO COMPANY LLC LP LLP LTD PLC NV SA AG THE CLASS A/B/C COM HLDG HOLDING(S) GRP GROUP`.
4. Drop the leading article `THE`.
5. Result is the normalization key for both the reverse index and the fuzzy candidate set.

Two distinct CIKs whose titles normalize to the **same** key are recorded as an `ambiguous_name` collision set — tier 3 returns `ambiguous_name` (never an arbitrary pick).

---

## 5. Fuzzy tier — gated so "no silent bad mapping" holds even here (review point)

Fuzzy name-matching is the classic silent-bad-mapping source, so the contract is inverted from "match if plausible" to **"unresolved unless it clears a pre-registered bar":**

- **Zero-dependency similarity** (Norton blocks `pip`/`pnpm` installs — see `blocker_norton_ssl_*`): stdlib `difflib.SequenceMatcher` ratio, **gated to `0.0` unless the two normalized names share ≥1 token**. No `rapidfuzz`/`thefuzz` dependency. *(Revised during the 0B build from the originally-proposed seq×Jaccard blend: at `FUZZY_MIN = 0.90` a Jaccard-weighted blend collapses to near-never-fires, because Jaccard drops sharply with small token sets — a genuine near-match like "General Dynamic"→"General Dynamics" scored ~0.6 and was wrongly rejected. The token-overlap **gate** is the anti-false-positive guard that the Jaccard term was meant to provide — zero shared tokens ⇒ score 0, no cross-company bleed — while the sequence ratio measures closeness and the high 0.90 bar does the rest. Same "no silent bad mapping" guarantee, without killing recall.)*
- **Pre-registered threshold** `FUZZY_MIN = 0.90` (proposed; §11 — confirm at Phase 0). Below it → `insufficient_confidence`, `resolved_security_id = None`.
- **Uniqueness guard.** The fuzzy tier resolves only if the top candidate clears the threshold **and** is unique — if two candidates are within a small margin (`FUZZY_MARGIN = 0.03`), it is `ambiguous_name`, not a coin-flip.
- `confidence` returned = the actual similarity score (so downstream can see a 0.91 differs from a 0.99), never rounded up to 1.0.

Net: the fuzzy path can only ever *lower* certainty into a resolved mapping above a high bar; everything else is typed-unresolved. This is the mechanism, not a policy note.

---

## 6. `as_of` and the honest v0 limitations

`as_of` is in the signature and threaded through, but **v0 resolution is as-of-agnostic**: `CikMap` is a current snapshot with no history. Consequences, stated plainly so no caller assumes more than exists:

- **Ticker reuse is undetectable in v0** (`ticker_reused` reserved). A ticker that changed hands is resolved to its *current* holder. For the GOVCONTRACT-001 window this is low-risk (contractors are large, stable issuers) but must be a documented caveat on the program's evidence package.
- **Delistings / mergers / historical name changes** are not modelled. A delisted contractor resolves as `no_public_security`.
- **v1 upgrade path:** back CAP-024 with a point-in-time ticker/issuer history (Sharadar `TICKERS` carries first/last trade dates and ticker changes — `data_sf1_access_tier` confirms access), at which point `as_of` becomes load-bearing and `ticker_reused` goes live. No contract change — only the backing store changes.

---

## 7. `resolved_security_id` — canonical identity

v0 uses the **zero-padded CIK** as the canonical id when a CIK is known (`"CIK0000320193"`), because CIK is the most stable public-issuer key and every tier 1/3/4 resolution yields one. A tier-2 ticker-only hit with no CIK (rare for public issuers, since `by_ticker`→CIK is available) falls back to `"TICKER:<SYM>"`. This keeps the id space small and stable; a richer internal security-id space (share classes, dual listings) is deferred to v1 and does not block the MVP. The id is opaque to callers — they store it on the event (`resolved_security_id`) and group by it; they do not parse it.

---

## 8. Data sources

- **v0:** `CikMap` from SEC `company_tickers.json` (already fetched by `load_cik_map`; ~public-company universe with tickers + titles). One network load, cached.
- **v1 (not now):** Sharadar `TICKERS` for as-of ticker history / delistings; an optional subsidiary→parent reference (e.g. from filings' `former names` / EDGAR `formerNames`, or a curated contractor map) to light up `subsidiary_unmapped` resolution rather than just labelling it.

---

## 9. Placement, dependencies, isolation

- **Path (resolved at build):** `app/altdata/security_master.py`. The design originally preferred a cross-cutting `app/data/` package, but **`app/data/` is gitignored** (`.gitignore: data/`, reserved for local data artifacts) — so the ADR-0037-sanctioned alternative `app/altdata/` was taken. It is arguably cleaner: CAP-024 imports `CikMap` from `app.altdata.sec`, so this is an intra-package import, not the cross-package inversion the design worried about. A future factor-side consumer importing from `altdata` is the acceptable trade; revisit if that coupling grates.
- **Depends on:** `app/altdata/sec/cik_map.py` (`CikMap`) — now an intra-package import (both live under `app/altdata/`).
- **Isolation:** imports no order-path module; **covered by `check_altdata_order_path_isolation.sh`** (ADR 0037 Decision 11 — the invariant's glob must include `app/altdata/security_master.py`).

---

## 10. Test plan (`tests/data/test_security_master.py`)

- **Tier precedence:** CIK beats ticker beats name; a supplied CIK wins even when the name is wrong.
- **Exact name:** normalization maps `"Apple Inc."`, `"APPLE INC"`, `"The Apple Company"` → the same key → resolves to AAPL's CIK with `method='exact_name'`.
- **Ambiguity:** two CIKs normalizing to one key → `ambiguous_name`, `resolved_security_id=None` (never an arbitrary pick).
- **Fuzzy floor:** a near-miss below `FUZZY_MIN` → `insufficient_confidence`; a clear ≥-threshold unique match → `fuzzy_name` with `confidence` = the real score; two close candidates → `ambiguous_name`.
- **No-match:** a fabricated name → `no_public_security`.
- **No-silent-bad-mapping property test:** for a corpus of subsidiary-style names (`"<PublicParent> Federal Systems LLC"`), assert the resolver **never** returns a resolved id below the confidence bar — it is unresolved-with-reason or a genuinely high-similarity parent match, never a silent guess.
- **Determinism:** identical inputs → identical `ResolutionResult` (ADR 0037 evidence discipline).
- Zero-dep, offline; no network (inject a fixture `CikMap`).

---

## 11. Pre-registered thresholds (confirm at Phase 0 sign-off)

| Knob | Proposed | Meaning |
|---|---|---|
| `FUZZY_MIN` | `0.90` | minimum blended similarity for a fuzzy resolve; below → `insufficient_confidence` |
| `FUZZY_MARGIN` | `0.03` | top-2 candidates within this → `ambiguous_name`, not a pick |

These gate a tradable universe (they feed §2.6's `confidently_resolved / public_company_events` mapping gate), so they are pre-registered, not tuned after seeing GOVCONTRACT-001 results.

---

## 12. What CAP-024 v0 unblocks

Phase 1 Quiver government-contract normalizer calls `resolve_security(issuer_name=recipient, …)` per contract row, writes `resolved_security_id` / `resolved_ticker` / `unresolved_reason` into `corporate_events` (Phase 0A columns), and sets `research_eligible = True` only on a confident resolution. The **mapping gate** (`confidently_resolved / public_company_events ≥ 85%`, kill `< 70%`) and the **USAspending cross-check** are then measurable — which is exactly what decides whether the Quiver pilot proceeds.
