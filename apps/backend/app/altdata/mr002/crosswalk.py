"""MR-002 historical identity crosswalk (pre-reg v0.5 §2 — FROZEN schema).

Effective-dated ``permaticker <-> ticker <-> cik`` identity resolution, built under
the frozen source precedence:

  1. Sharadar security metadata + ``secfilings`` identifier (CIK embedded in the URL —
     works for delisted names, which current ``company_tickers.json`` drops);
  2. EDGAR submissions / filing-header identity (cross-check + entity evidence);
  3. corporate-action predecessor/successor evidence (Sharadar ACTIONS
     ``tickerchangefrom/to``, ``spunofffrom``, ``acquisitionby``, ``delisted``);
  4. archived historical ticker mappings (reserved — none wired yet);
  5. manually reviewed override table (explicit windows with evidence + reviewer;
     used where higher sources are silent or time-invariant — e.g. the
     Google->Alphabet predecessor/successor CIK chain, which no vendor field carries).

Semantics (registered):
- ``effective_from``/``effective_to`` are inclusive dates; ``effective_to = None`` =
  open-ended. A ticker symbol may map to DIFFERENT permatickers over time (e.g. GOOG:
  Class A pre-2014-03-27, Class C after) — resolution is always (ticker, date).
- Override rows claim their stated windows; automatic (precedence-1) rows cover only
  the remainder of the security's price history. Unresolved periods are EXCLUDED —
  never inherit the current issuer's CIK (owner control, CAP-024 principle).
- Every row carries source, source_record_id, confidence, and mapping_rationale;
  every manual override additionally requires reviewer approval before the crosswalk
  hash freezes.

Pure transformation — all vendor rows are passed in by the runner. Off the order
path (ADR 0037 isolation).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

CIK_RE = re.compile(r"CIK=0*(\d+)", re.IGNORECASE)

RELATIONSHIP_TYPES = (
    "direct", "ticker_rename", "share_class", "predecessor_cik",
    "successor_cik", "spin_off", "acquisition", "manual_override",
)


@dataclass
class CrosswalkRow:
    permaticker: int
    ticker: str
    cik: int | None
    effective_from: date
    effective_to: date | None          # inclusive; None = open-ended
    relationship_type: str
    source: str
    source_record_id: str
    confidence: str                    # high | medium | manual_pending_review
    mapping_rationale: str
    review_status: str = "auto_high_precedence"   # overrides: pending_owner_review


@dataclass
class CrosswalkBuild:
    rows: list[CrosswalkRow] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def resolve(self, ticker: str, on: date) -> CrosswalkRow | None:
        """(ticker, date) -> row, or None (unresolved periods are excluded)."""
        t = ticker.strip().upper()
        hits = [r for r in self.rows
                if r.ticker == t and r.effective_from <= on
                and (r.effective_to is None or on <= r.effective_to)]
        if not hits:
            return None
        if len({(h.permaticker, h.cik) for h in hits}) > 1:
            self.conflicts.append(f"ambiguous:{t}@{on}:" + ",".join(
                f"{h.permaticker}/{h.cik}/{h.relationship_type}" for h in hits))
            return None  # unexplained identity conflicts are a coverage gate (=0)
        return hits[0]

    def cik_for(self, permaticker: int, on: date) -> int | None:
        hits = [r for r in self.rows
                if r.permaticker == permaticker and r.cik is not None
                and r.effective_from <= on
                and (r.effective_to is None or on <= r.effective_to)]
        ciks = {h.cik for h in hits}
        if len(ciks) > 1:
            self.conflicts.append(f"ambiguous_cik:{permaticker}@{on}:{sorted(ciks)}")
            return None
        return ciks.pop() if ciks else None


def cik_from_secfilings(url: str | None) -> int | None:
    if not url:
        return None
    m = CIK_RE.search(str(url))
    return int(m.group(1)) if m else None


def _d(s: str | None) -> date | None:
    return date.fromisoformat(str(s)[:10]) if s else None


def build_security(
    build: CrosswalkBuild,
    tickers_row: dict[str, Any],
    actions: list[dict[str, Any]],
    *,
    edgar_tickers_now: list[str] | None = None,
    overrides: list[CrosswalkRow] | None = None,
) -> None:
    """Add one security's effective-dated rows to the build.

    ``tickers_row`` = the Sharadar TICKERS row (table=SEP) for the CURRENT ticker;
    ``actions`` = Sharadar ACTIONS rows for that ticker; ``edgar_tickers_now`` = the
    ticker list from the CIK's EDGAR submissions (precedence-2 cross-check);
    ``overrides`` = reviewed manual rows for this permaticker (explicit windows).
    """
    perma = int(tickers_row["permaticker"])
    current = str(tickers_row["ticker"]).upper()
    first = _d(tickers_row.get("firstpricedate"))
    last = _d(tickers_row.get("lastpricedate"))
    delisted = str(tickers_row.get("isdelisted", "N")).upper() in ("Y", "TRUE", "1")
    cik = cik_from_secfilings(tickers_row.get("secfilings"))
    if first is None:
        build.conflicts.append(f"no_firstpricedate:{current}")
        return
    if cik is None:
        build.conflicts.append(f"no_cik_in_secfilings:{current}")
        return
    end = last if delisted else None

    # precedence-2 cross-check: for LIVE names, the EDGAR submissions ticker list
    # should contain the current ticker; a mismatch is logged, never silently kept.
    if edgar_tickers_now is not None and not delisted \
            and current not in [t.upper() for t in edgar_tickers_now]:
        build.conflicts.append(
            f"edgar_ticker_mismatch:{current}:cik{cik}:{edgar_tickers_now}")

    ovr = sorted(overrides or [], key=lambda r: r.effective_from)
    for r in ovr:
        if r.permaticker != perma:
            build.conflicts.append(f"override_permaticker_mismatch:{current}:{r.permaticker}")
            return
        build.rows.append(r)

    # ticker renames (precedence 3): tickerchangefrom rows carry the OLD symbol in
    # ``contraticker`` at the change date. Multiple renames are applied oldest-first.
    renames = sorted(
        (a for a in actions if a.get("action") == "tickerchangefrom"),
        key=lambda a: str(a.get("date")),
    )
    spans: list[tuple[str, date, date | None, str, str]] = []  # ticker, from, to, rel, why
    cursor = first
    for a in renames:
        chg = _d(a.get("date"))
        old = str(a.get("contraticker") or "").upper()
        if not chg or not old or old in ("N/A",):
            continue
        if chg <= cursor:  # when-issued symbol retired at listing (e.g. GEHCV) — no traded window
            build.notes.append(f"rename_zero_window:{current}:{old}@{chg}")
            continue
        spans.append((old, cursor, chg - timedelta(days=1), "ticker_rename",
                      f"traded as {old} until renamed {chg} (ACTIONS tickerchangefrom)"))
        cursor = chg
    spans.append((current, cursor, end, "direct",
                  "current symbol per Sharadar TICKERS; CIK from secfilings"))

    # windows already claimed by overrides are excluded from automatic rows
    def clip(lo: date, hi: date | None) -> list[tuple[date, date | None]]:
        segs: list[tuple[date, date | None]] = [(lo, hi)]
        for r in ovr:
            nxt: list[tuple[date, date | None]] = []
            for s_lo, s_hi in segs:
                r_hi = r.effective_to or date.max
                if r.effective_from > (s_hi or date.max) or r_hi < s_lo:
                    nxt.append((s_lo, s_hi))
                    continue
                if s_lo < r.effective_from:
                    nxt.append((s_lo, r.effective_from - timedelta(days=1)))
                if r.effective_to is not None and (s_hi is None or r.effective_to < s_hi):
                    nxt.append((r.effective_to + timedelta(days=1), s_hi))
            segs = nxt
        return segs

    for tick, lo, hi, rel, why in spans:
        for s_lo, s_hi in clip(lo, hi):
            build.rows.append(CrosswalkRow(
                permaticker=perma, ticker=tick, cik=cik,
                effective_from=s_lo, effective_to=s_hi,
                relationship_type=rel, source="sharadar_tickers.secfilings",
                source_record_id=f"permaticker:{perma}",
                confidence="high", mapping_rationale=why,
                review_status="auto_high_precedence",
            ))

    # spin-off / acquisition / delisting evidence rows (annotations, not identities)
    for a in actions:
        act = a.get("action")
        if act == "spunofffrom":
            build.notes.append(
                f"spin_off:{current}@{a.get('date')}:parent={a.get('contraticker')}")
        elif act == "acquisitionby":
            build.notes.append(
                f"acquisition:{current}@{a.get('date')}:acquirer={a.get('contraticker')}")
        elif act == "delisted":
            build.notes.append(f"delisted:{current}@{a.get('date')}")


def share_class_pass(build: CrosswalkBuild) -> None:
    """Re-label 'direct' rows as 'share_class' where several permatickers share a CIK
    in overlapping windows (dual-class issuers keep distinct permanent identities)."""
    by_cik: dict[int, set[int]] = {}
    for r in build.rows:
        if r.cik is not None:
            by_cik.setdefault(r.cik, set()).add(r.permaticker)
    for r in build.rows:
        if r.cik is not None and len(by_cik.get(r.cik, set())) > 1 \
                and r.relationship_type == "direct":
            r.relationship_type = "share_class"


def integrity_check(build: CrosswalkBuild) -> list[str]:
    """Identity-interval integrity invariants (owner review 2026-07-11 §3), enforced
    in code: per (permaticker, ticker) intervals must not overlap; a permaticker's
    overlapping intervals must not carry different CIKs (each trading date resolves
    to at most one CIK); gaps are allowed only as explicit unresolved periods. A
    lower-precedence source never silently overwrites a higher-precedence interval —
    overlaps are ERRORS, not merges. Violations are appended to build.conflicts and
    returned."""
    errs: list[str] = []

    def overlaps(a: CrosswalkRow, b: CrosswalkRow) -> bool:
        a_hi = a.effective_to or date.max
        b_hi = b.effective_to or date.max
        return a.effective_from <= b_hi and b.effective_from <= a_hi

    by_pt: dict[tuple[int, str], list[CrosswalkRow]] = {}
    by_p: dict[int, list[CrosswalkRow]] = {}
    for r in build.rows:
        by_pt.setdefault((r.permaticker, r.ticker), []).append(r)
        by_p.setdefault(r.permaticker, []).append(r)
    for (perma, tick), rows in by_pt.items():
        rows = sorted(rows, key=lambda r: r.effective_from)
        for a, b in zip(rows, rows[1:], strict=False):
            if overlaps(a, b):
                errs.append(f"interval_overlap:{perma}:{tick}:"
                            f"{a.effective_from}..{a.effective_to}|{b.effective_from}..{b.effective_to}")
    for perma, rows in by_p.items():
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a.cik != b.cik and overlaps(a, b):
                    errs.append(f"cik_conflict_in_overlap:{perma}:{a.cik}vs{b.cik}:"
                                f"{a.ticker}/{b.ticker}")
    build.conflicts.extend(errs)
    return errs
