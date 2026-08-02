"""Layer 2 — the governed old-key → permanent-lineage crosswalk (owner ruling, 2026-07-29).

The countersigned universe is 14,150 historical TICKER KEYS. Layer 2 restricts the rebuilt corpus by
the PERMANENT-IDENTITY IMAGE of that set, so this establishes the mapping — and, critically, refuses
to guess. Every one of the 14,150 keys receives an explicit disposition; nothing disappears silently.

## Why a key cannot be mapped by ticker equality

A display symbol is reused across unrelated issuers and retro-mapped on rename, so `ticker == ticker`
resolves the wrong security in exactly the cases that matter. `ECHO` is the worked example: the frozen
corpus holds Echo Global Logistics' 2009-2021 prices under that key, while the current vendor master
says `ECHO` is EchoStar (permaticker 193776) and files Echo Global as `ECHO2` (193608). Mapping the old
key by spelling would attach one company's universe membership to another's price history.

## Resolution order

  1. candidates = the lineage whose CURRENT ticker is the old key, plus every lineage listing the old
     key among its `relatedtickers` (which is how the vendor records a retired alias);
  2. one candidate            -> MAPPED_UNIQUE
  3. several candidates       -> resolve by EFFECTIVE INTERVAL against the span the old key actually
                                 priced in the frozen corpus. Exactly one covering lineage resolves it;
                                 anything else is AMBIGUOUS_MULTIPLE_LINEAGES and stops for adjudication;
  4. no candidate             -> UNRESOLVED_NO_PERMANENT_ID
  5. several old keys landing on one lineage -> MAPPED_ALIAS_COLLAPSE, recorded as a group

Alias collapse is identity NORMALIZATION, not a universe-selection change: the securities are the same,
counted once. Universe-size reporting therefore carries three numbers, never one.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

import truststore  # noqa: E402

truststore.inject_into_ssl()

from dotenv import load_dotenv  # noqa: E402

for _e in (Path(os.environ.get("WORKBENCH_ENV_FILE", ".env")),
           Path(os.environ.get("WORKBENCH_ENV_FILE_ALT", "apps/backend/.env"))):
    if _e.exists():
        load_dotenv(_e, override=False)

from app.factor_data.providers.sharadar import SharadarProvider  # noqa: E402
from app.validation.governed_corpus import canonical_json  # noqa: E402
from scripts.forward_validation._governed_window import (  # noqa: E402
    REQUIRED_HISTORY_SESSIONS,
    governed_decision_window,
)
from scripts.forward_validation._session_arg import add_session_argument  # noqa: E402

LEGACY_UNIVERSE_SHA256 = "2b34970fc123689b66c82c6c119d0e946bf99181b9109b878cb1ba6148d3bcc4"

#: Finalized by the owner 2026-07-29, EXPRESSLY CONDITIONAL on being computed over exactly the
#: 14,145 MAPPED permanent identities. Asserted here so the condition is machine-enforced: an
#: exclusion that leaked an identity into the permanent universe would move this digest.
PERMANENT_UNIVERSE_SHA256 = "fd2c843a631f8d9831f221b747937f5e617074c43621c6743cc9b36c718bccc7"
PERMANENT_IDENTITY_COUNT = 14145
SOURCE_KEY_COUNT = 14150

#: Same threshold the ratified identity contract uses to separate a disconnected price segment from a
#: data blemish (`security_lineage.LINEAGE_BRIDGE_HOLE_MIN_SESSIONS`).
REUSE_HOLE_SESSIONS = 20
_ALL_SESSIONS: list = []


def _worst_gap_sessions(key_sessions: tuple) -> int:
    """Longest run of governed sessions with no mark inside the key's own priced span."""
    if len(key_sessions) < 2:
        return 0
    marks = set(key_sessions)
    lo, hi = min(key_sessions), max(key_sessions)
    window = [d for d in _ALL_SESSIONS if lo <= d <= hi]
    run = worst = 0
    for d in window:
        run = 0 if d in marks else run + 1
        worst = max(worst, run)
    return worst

MAPPED_UNIQUE = "MAPPED_UNIQUE"
MAPPED_ALIAS_COLLAPSE = "MAPPED_ALIAS_COLLAPSE"
UNRESOLVED_NO_PERMANENT_ID = "UNRESOLVED_NO_PERMANENT_ID"
AMBIGUOUS_MULTIPLE_LINEAGES = "AMBIGUOUS_MULTIPLE_LINEAGES"
INVALID_SOURCE_RECORD = "INVALID_SOURCE_RECORD"

#: Terminal owner-adjudicated exclusion classes (ruling 2026-07-29). Neither creates an identity —
#: an excluded key leaves the permanent universe entirely, so neither can move
#: `governed_permanent_universe_sha256`, which is computed over MAPPED rows only.
EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING = "EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING"
EXCLUDED_UNRESOLVED_SOURCE_MASTER = "EXCLUDED_UNRESOLVED_SOURCE_MASTER"
EXCLUSION_CLASSES = (EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING, EXCLUDED_UNRESOLVED_SOURCE_MASTER)

DISPOSITION_AUTHORITY = (
    "owner ruling 2026-07-29 (Jay Wang) — final adjudication of the five unresolved Layer 2 "
    "crosswalk keys; synthetic permaticker values NOT authorized"
)

#: The RULING. Evidence for every clause below is MEASURED by this script from the countersigned
#: corpus and its ACTIONS table — the table records what was decided, never what was observed.
#: Applied ONLY to keys that independently resolve to UNRESOLVED_NO_PERMANENT_ID; a key the crosswalk
#: manages to map is a premise failure and stops the run, because the ruling was made on the express
#: finding that no permanent identity is available.
OWNER_DISPOSITIONS: dict[str, str] = {
    "PGIE": EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING,
    "MRXLY": EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING,
    "DHCC": EXCLUDED_UNRESOLVED_SOURCE_MASTER,
    "EVTV": EXCLUDED_UNRESOLVED_SOURCE_MASTER,
    "GAMB": EXCLUDED_UNRESOLVED_SOURCE_MASTER,
}

#: The decision window is DERIVED per run from `--session` — see `_governed_window`. It was the
#: constant `DECISION_WINDOW = (date(2025, 6, 25), date(2026, 7, 27))`, which PR #589's sweep missed
#: because a tuple is not the assignment shape it looked for. A crosswalk built for one session and
#: silently scored over another session's window yields evidence that is internally consistent and
#: wrong, and no downstream digest can detect it. Hence: no window literal, no default.

#: ⚠ HISTORICAL CONTRACT FACT — deliberately still a constant, and registered as such in
#: `scripts/check_layer2_date_literals.py`.
#:
#: This is NOT a corpus property and does not move when the corpus does. It is the fixed date at which
#: the vendor's source master terminates for the three keys the owner ruled out as
#: EXCLUDED_UNRESOLVED_SOURCE_MASTER on 2026-07-29 — a property of that adjudicated evidence, not of
#: any session. Measuring it from a corpus would be a category error: it would let a later corpus
#: silently redefine what a past ruling was made about. Asserted, not assumed — a key ruled out on the
#: strength of this coincidence must actually exhibit it.
SOURCE_MASTER_BOUNDARY = date(2026, 6, 12)


def _iso(v: object) -> str | None:
    return v.isoformat() if isinstance(v, date) else (str(v) if v else None)


def _as_date(v: object) -> date | None:
    """The provider returns lifetime bounds as strings; the corpus returns them as dates. Compare on
    one type, so an interval test can never silently become a string comparison."""
    if isinstance(v, date):
        return v
    text = str(v or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Layer 2 universe crosswalk.")
    ap.add_argument("--corpus", required=True, help="the COUNTERSIGNED corpus defining U_old")
    ap.add_argument("--out", required=True)
    add_session_argument(ap)
    args = ap.parse_args(argv)
    session: date = args.session
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(args.corpus, read_only=True)
    old_keys = sorted(r[0] for r in con.execute("SELECT DISTINCT ticker FROM sep").fetchall())
    spans = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
        "SELECT ticker, min(date), max(date), count(*) FROM sep GROUP BY ticker").fetchall()}
    # The frozen corpus carries its OWN ticker master from the legacy vintage. That is the
    # authoritative record of which security the vendor assigned each symbol to AT THE FREEZE — which
    # is the governing anchor (owner ruling 2026-07-29). A company taking the symbol afterwards does
    # not retroactively change what the countersigned key represented.
    legacy_master = {r[0]: {"name": str(r[1] or ""), "first": _as_date(r[2]), "last": _as_date(r[3])}
                     for r in con.execute(
                         "SELECT ticker, name, firstpricedate, lastpricedate FROM tickers").fetchall()}
    global _ALL_SESSIONS
    _ALL_SESSIONS = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM sep ORDER BY date").fetchall()]
    spans_sessions = {r[0]: tuple(r[1]) for r in con.execute(
        "SELECT ticker, list(date ORDER BY date) FROM sep GROUP BY ticker").fetchall()}

    # ---- evidence for the owner-adjudicated keys, measured from the countersigned corpus ----
    # The window is derived from the governed session by the shared rule, never copied as a literal.
    # It refuses outright when the corpus cannot supply the exact window ending on the session, so a
    # crosswalk can never be scored over a window belonging to a different session.
    w0, w1 = governed_decision_window(con, session)
    window_sessions = con.execute(
        "SELECT count(DISTINCT date), max(date) FROM sep WHERE date BETWEEN ? AND ?",
        [w0, w1]).fetchone()
    master_cols = [c[0] for c in con.execute("DESCRIBE tickers").fetchall()]
    corpus_has_permaticker = "permaticker" in master_cols
    adjudication_evidence: dict[str, dict] = {}
    for key in OWNER_DISPOSITIONS:
        master = con.execute("SELECT * FROM tickers WHERE ticker = ?", [key]).fetchall()
        acts = con.execute(
            "SELECT date, action, ticker, name, value, contraticker FROM actions WHERE ticker = ? "
            "ORDER BY date, action", [key]).fetchall()
        contra = con.execute(
            "SELECT date, action, ticker, name, value, contraticker FROM actions "
            "WHERE contraticker = ? AND ticker <> ? ORDER BY date, action", [key, key]).fetchall()
        win = con.execute(
            "SELECT count(*), min(date), max(date) FROM sep WHERE ticker = ? AND date BETWEEN ? AND ?",
            [key, w0, w1]).fetchone()
        lastupd = con.execute(
            "SELECT min(lastupdated), max(lastupdated) FROM sep WHERE ticker = ?", [key]).fetchone()
        adjudication_evidence[key] = {
            # strict=False: the vendor master row and the column list are produced by the same
            # SELECT, so a length mismatch cannot occur here; the flag is explicit rather than relying
            # on zip's silent-truncation default.
            "legacy_master_row": ([dict(zip(master_cols,
                                            [_iso(v) if isinstance(v, date) else v for v in m],
                                            strict=False)) for m in master] or None),
            "legacy_master_row_count": len(master),
            "actions_rows_as_ticker": [[_iso(c) if isinstance(c, date) else c for c in a]
                                       for a in acts],
            "actions_rows_naming_key_as_contraticker": [
                [_iso(c) if isinstance(c, date) else c for c in a] for a in contra],
            "decision_window_row_count": int(win[0]),
            "decision_window_first_priced": _iso(win[1]),
            "decision_window_last_priced": _iso(win[2]),
            "sep_lastupdated_min": _iso(lastupd[0]),
            "sep_lastupdated_max": _iso(lastupd[1]),
        }
    con.close()
    print(f"U_old (countersigned ticker keys): {len(old_keys):,}")

    legacy = hashlib.sha256(canonical_json(sorted(old_keys))).hexdigest()
    print(f"legacy_governed_universe_sha256  : {legacy}")
    if legacy != LEGACY_UNIVERSE_SHA256:
        raise SystemExit(f"U_old does not reproduce the countersigned digest {LEGACY_UNIVERSE_SHA256}")
    print("  reproduces the countersigned digest")

    with SharadarProvider() as p:
        tk = p.fetch_table("TICKERS")
    src = tk[tk["table"] == "SEP"]
    print(f"source master (table=SEP)        : {len(src):,} rows")

    # Authorized source-recovery fallback (owner ruling 2026-07-29, evidence order #2): a governed key
    # may carry SEP price rows while the vendor files its master record under a NON-SEP slice —
    # measured for HYPG and OCCI, both listed under SFP. The permaticker is the security's permanent
    # identity whichever slice records it, so an EXACT ticker match in the full export is authoritative.
    # Deliberately exact-ticker only: no name similarity, no price-path matching, no date coincidence.
    # Consulted only in the branch where no SEP-slice lineage claims the key at all, so it can never
    # override a SEP-slice resolution.
    other_slices: dict[str, dict] = {}
    for _, r in tk[tk["table"] != "SEP"].iterrows():
        other_slices.setdefault(str(r["ticker"]), {
            "permaticker": str(r["permaticker"]).strip(), "ticker": str(r["ticker"]),
            "name": str(r.get("name") or ""), "first": _as_date(r.get("firstpricedate")),
            "last": _as_date(r.get("lastpricedate")), "slice": str(r["table"])})
    print(f"recoverable from non-SEP slices  : {len(other_slices):,} tickers")

    by_ticker: dict[str, dict] = {}
    by_related: dict[str, list[dict]] = defaultdict(list)
    for _, r in src.iterrows():
        rec = {"permaticker": str(r["permaticker"]).strip(), "ticker": str(r["ticker"]),
               "name": str(r.get("name") or ""), "first": _as_date(r.get("firstpricedate")),
               "last": _as_date(r.get("lastpricedate"))}
        by_ticker[rec["ticker"]] = rec
        for alias in str(r.get("relatedtickers") or "").replace(",", " ").split():
            by_related[alias].append(rec)

    # index the CURRENT master by the two vendor-authoritative fields the legacy master also carries
    by_name_first: dict[tuple, dict] = {}
    by_name: dict[str, list[dict]] = defaultdict(list)
    for rec in by_ticker.values():
        by_name_first.setdefault((rec["name"].strip().upper(), rec["first"]), rec)
        by_name[rec["name"].strip().upper()].append(rec)

    def legacy_freeze_owner(key: str, candidates: list | None = None) -> dict | None:
        """The lineage the vendor assigned this symbol to at the legacy freeze.

        Matched on (name, firstpricedate) — both sides are vendor records, so this is evidence, not
        inference. Never falls back to ticker equality, which is the very thing being disambiguated.
        """
        leg = legacy_master.get(key)
        if not leg or not leg["name"]:
            return None
        hit = by_name_first.get((leg["name"].strip().upper(), leg["first"]))
        if hit is not None:
            return hit
        same_name = by_name.get(leg["name"].strip().upper(), [])
        if len(same_name) == 1:
            return same_name[0]
        # A company RENAME breaks the name match while the security is unchanged (measured: MBAVU,
        # "M3-BRIGADE ACQUISITION V CORP" -> "VELOS ACQUISITION I CORP"). First-price date is a hard
        # vendor fact that a rename cannot move, so it disambiguates — but ONLY within the candidate
        # set for this key, never as a global lookup, where the date alone collides freely.
        if candidates is not None and leg["first"] is not None:
            dated = [r for r in candidates if r["first"] == leg["first"]]
            if len(dated) == 1:
                return dated[0]
        return None

    rows: list[dict] = []
    for key in old_keys:
        lo, hi, n = spans.get(key, (None, None, 0))
        # ⚠ PRECEDENCE: a lineage whose CURRENT ticker IS the key owns it outright. `relatedtickers`
        # is only a fallback for a RETIRED key, never a competing claim — a SPAC's common, unit and
        # warrant siblings all cross-reference each other, so treating alias claims as equal to
        # ownership manufactures ambiguity for ~11% of the universe (measured: 1,561 keys) where none
        # exists. Alias claims are consulted only when no lineage currently spells the key.
        direct = by_ticker.get(key)
        if direct is not None:
            cands = {direct["permaticker"]: direct}
        else:
            cands = {}
            for rec in by_related.get(key, []):
                cands.setdefault(rec["permaticker"], rec)

        row = {"old_ticker_key": key, "old_first_priced": _iso(lo), "old_last_priced": _iso(hi),
               "old_row_count": int(n), "candidate_permatickers": sorted(cands),
               "claim_basis": "current_ticker" if direct is not None else "relatedtickers"}

        # Symbol REUSE is invisible to interval logic when the current lineage's lifetime happens to
        # span the old key's whole range (exactly the ECHO case: EchoStar 2008-2026 "covers" Echo
        # Global's 2009-2021 rows). The signature that distinguishes them is a structural hole in the
        # old key's own priced history, so it is tested directly.
        if direct is not None and n:
            hole = _worst_gap_sessions(spans_sessions.get(key, ()))
            if hole >= REUSE_HOLE_SESSIONS:
                others = [r for r in by_related.get(key, [])
                          if r["permaticker"] != direct["permaticker"]]
                owner = legacy_freeze_owner(key, [direct, *others])
                if owner is not None:
                    # RATIFIED: legacy-freeze ownership governs; post-freeze symbol reuse does not
                    # alter what the countersigned key represented.
                    row |= {"disposition": MAPPED_UNIQUE, "permaticker": owner["permaticker"],
                            "current_ticker": owner["ticker"], "name": owner["name"],
                            "effective_first": _iso(owner["first"]),
                            "effective_last": _iso(owner["last"]),
                            "evidence": "legacy_freeze_owner(name,firstpricedate)",
                            "reuse_hole_sessions": hole,
                            "superseded_by_current_symbol_owner": direct["permaticker"]}
                    rows.append(row)
                    continue
                row |= {"disposition": AMBIGUOUS_MULTIPLE_LINEAGES, "permaticker": None,
                        "current_ticker": None,
                        "reason": (f"the key's own priced history has a {hole}-session structural hole, "
                                   f"the signature of a symbol reused across issuers"),
                        "candidates": [{"permaticker": r["permaticker"], "ticker": r["ticker"],
                                        "name": r["name"], "first": _iso(r["first"]),
                                        "last": _iso(r["last"])}
                                       for r in [direct, *others]]}
                rows.append(row)
                continue

        if not cands:
            # last authoritative resort before refusing: the legacy master's own ownership record
            if (owner := legacy_freeze_owner(key, list(by_related.get(key, [])))) is not None:
                row |= {"disposition": MAPPED_UNIQUE, "permaticker": owner["permaticker"],
                        "current_ticker": owner["ticker"], "name": owner["name"],
                        "effective_first": _iso(owner["first"]),
                        "effective_last": _iso(owner["last"]),
                        "evidence": "legacy_freeze_owner(name,firstpricedate)"}
                rows.append(row)
                continue
            rec = other_slices.get(key)
            leg = legacy_master.get(key)
            if rec is not None and leg and rec["name"].strip().upper() == leg["name"].strip().upper():
                row |= {"disposition": MAPPED_UNIQUE, "permaticker": rec["permaticker"],
                        "current_ticker": rec["ticker"], "name": rec["name"],
                        "effective_first": _iso(rec["first"]), "effective_last": _iso(rec["last"]),
                        "evidence": f"exact_ticker_in_{rec['slice']}_slice"}
                rows.append(row)
                continue
            # Record the recovery attempts THEMSELVES, in the owner's ordered evidence hierarchy, so a
            # refusal is auditable as work performed rather than as an absence of work.
            row |= {"disposition": UNRESOLVED_NO_PERMANENT_ID, "permaticker": None,
                    "current_ticker": None,
                    "legacy_name": (leg or {}).get("name"),
                    "legacy_isdelisted_at_freeze": None,
                    "source_recovery_performed": {
                        "1_current_ticker_claim_sep_slice": key in by_ticker,
                        "2_relatedtickers_alias_claim_sep_slice": len(by_related.get(key, [])),
                        "3_legacy_freeze_owner_name_firstpricedate": False,
                        "4_exact_ticker_any_non_sep_slice": (
                            other_slices[key]["slice"] if key in other_slices else None),
                        "4_non_sep_slice_name_matched_legacy_master": bool(
                            rec is not None and leg
                            and rec["name"].strip().upper() == leg["name"].strip().upper()),
                    },
                    "reason": "no lineage claims this key by ticker or alias in ANY slice, and the "
                              "legacy master record does not match any current lineage"}
        elif len(cands) == 1:
            rec = next(iter(cands.values()))
            row |= {"disposition": MAPPED_UNIQUE, "permaticker": rec["permaticker"],
                    "current_ticker": rec["ticker"], "name": rec["name"],
                    "effective_first": _iso(rec["first"]), "effective_last": _iso(rec["last"]),
                    "evidence": "current_ticker" if key in by_ticker else "relatedtickers"}
        else:
            # several lineages claim the key — resolve ONLY by effective interval, never by spelling
            covering = [rec for rec in cands.values()
                        if rec["first"] and rec["last"] and lo and hi
                        and rec["first"] <= lo and rec["last"] >= hi]
            if len(covering) == 1:
                rec = covering[0]
                row |= {"disposition": MAPPED_UNIQUE, "permaticker": rec["permaticker"],
                        "current_ticker": rec["ticker"], "name": rec["name"],
                        "effective_first": _iso(rec["first"]), "effective_last": _iso(rec["last"]),
                        "evidence": "effective_interval_covers_old_span"}
            elif (owner := legacy_freeze_owner(key, list(cands.values()))) is not None:
                row |= {"disposition": MAPPED_UNIQUE, "permaticker": owner["permaticker"],
                        "current_ticker": owner["ticker"], "name": owner["name"],
                        "effective_first": _iso(owner["first"]),
                        "effective_last": _iso(owner["last"]),
                        "evidence": "legacy_freeze_owner(name,firstpricedate)"}
            else:
                row |= {"disposition": AMBIGUOUS_MULTIPLE_LINEAGES, "permaticker": None,
                        "current_ticker": None,
                        "reason": (f"{len(cands)} lineages claim the key and "
                                   f"{len(covering)} cover its priced span {lo}..{hi}"),
                        "candidates": [{"permaticker": r["permaticker"], "ticker": r["ticker"],
                                        "name": r["name"], "first": _iso(r["first"]),
                                        "last": _iso(r["last"])} for r in cands.values()]}
        rows.append(row)

    # alias collapse: several old keys resolving to one lineage
    groups: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r.get("permaticker"):
            groups[r["permaticker"]].append(r["old_ticker_key"])
    for r in rows:
        p = r.get("permaticker")
        if p and len(groups[p]) > 1:
            r["disposition"] = MAPPED_ALIAS_COLLAPSE
            r["alias_group"] = sorted(groups[p])

    # ---- terminal owner adjudication of the keys no authoritative source could resolve ----
    by_key = {r["old_ticker_key"]: r for r in rows}
    missing = sorted(set(OWNER_DISPOSITIONS) - set(by_key))
    if missing:
        raise SystemExit(f"adjudicated key(s) absent from U_old: {missing}")
    premise_failures = [k for k in OWNER_DISPOSITIONS
                        if by_key[k]["disposition"] != UNRESOLVED_NO_PERMANENT_ID]
    if premise_failures:
        # The ruling's express finding is that no permanent identity is available. If the crosswalk
        # now maps one, the ruling's premise is void and the key must go back to the owner — silently
        # overwriting a resolved mapping with an exclusion would destroy a real security.
        raise SystemExit(
            "PREMISE FAILURE — the following adjudicated key(s) now RESOLVE to a permanent identity, "
            "so the 2026-07-29 exclusion ruling no longer applies to them. Return to the owner: "
            + ", ".join(f"{k}->{by_key[k]['disposition']}" for k in premise_failures))

    exclusions: list[dict] = []
    for key, klass in sorted(OWNER_DISPOSITIONS.items()):
        row = by_key[key]
        ev = adjudication_evidence[key]
        master = (ev["legacy_master_row"] or [{}])[0]
        delistings = [a for a in ev["actions_rows_as_ticker"]
                      if str(a[1]).endswith("delisting") or a[1] == "delisted"]

        record = {
            "old_ticker_key": key,
            "disposition": klass,
            "disposition_authority": DISPOSITION_AUTHORITY,
            "permaticker": None,
            "synthetic_identity_created": False,
            "legacy_ticker": key,
            "legacy_name": master.get("name"),
            "legacy_master_record": master,
            "legacy_isdelisted_at_freeze": master.get("isdelisted"),
            "legacy_master_lifetime": [master.get("firstpricedate"), master.get("lastpricedate")],
            "priced_span_in_corpus": [row["old_first_priced"], row["old_last_priced"]],
            "price_row_count": row["old_row_count"],
            "governed_session": session.isoformat(),
            "required_history_sessions": REQUIRED_HISTORY_SESSIONS,
            "decision_window": [w0.isoformat(), w1.isoformat()],
            "decision_window_sessions_in_corpus": int(window_sessions[0]),
            "decision_window_max_session_in_corpus": _iso(window_sessions[1]),
            "decision_window_row_count": ev["decision_window_row_count"],
            "sep_lastupdated_span": [ev["sep_lastupdated_min"], ev["sep_lastupdated_max"]],
            "actions_rows_as_ticker": ev["actions_rows_as_ticker"],
            "actions_rows_naming_key_as_contraticker":
                ev["actions_rows_naming_key_as_contraticker"],
            "source_recovery_performed": row.get("source_recovery_performed"),
            "permanent_identity_unavailable_because": row["reason"],
            "legacy_corpus_records_no_permaticker_column": not corpus_has_permaticker,
        }

        if klass == EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING:
            if not delistings:
                raise SystemExit(
                    f"{key}: ruled a DOCUMENTED historical delisting but ACTIONS holds no delisting "
                    f"row; the basis of the ruling is not present in the authoritative record")
            if ev["decision_window_row_count"] != 0:
                raise SystemExit(
                    f"{key}: ruled to have no rows in the decision window but "
                    f"{ev['decision_window_row_count']} are present")
            record |= {
                "authoritative_delisting_action": delistings[-1][1],
                "authoritative_delisting_date": delistings[-1][0],
                "authoritative_delisting_source": "SHARADAR/ACTIONS (countersigned corpus)",
                "affects_july_27_scoring_proxy_ranking_or_observation": False,
                "basis": [
                    "authoritative ACTIONS records establish the delisting date",
                    "no rows in the decision window",
                    "cannot affect the July 27 scoring, proxy, ranking or observation",
                    "no current permanent identity is available",
                ],
            }
        else:
            if delistings:
                raise SystemExit(
                    f"{key}: ruled UNRESOLVED_SOURCE_MASTER but ACTIONS holds a delisting row "
                    f"{delistings[-1]}; that is a documented delisting, not an unexplained "
                    f"disappearance")
            if ev["actions_rows_as_ticker"] or ev["actions_rows_naming_key_as_contraticker"]:
                raise SystemExit(
                    f"{key}: ruled to have NO ACTIONS record explaining its disappearance, but "
                    f"ACTIONS rows referencing it exist")
            last = date.fromisoformat(str(row["old_last_priced"]))
            if last != SOURCE_MASTER_BOUNDARY:
                raise SystemExit(
                    f"{key}: ruled to terminate at the defective source boundary "
                    f"{SOURCE_MASTER_BOUNDARY}, but its last priced session is {last}")
            record |= {
                "terminates_at_defective_source_boundary": SOURCE_MASTER_BOUNDARY.isoformat(),
                "isdelisted_at_freeze": master.get("isdelisted"),
                "actions_explanation_present": False,
                "quarantined": True,
                "owner_ruling_is_an_adjudication_not_a_validity_finding": True,
                "basis": [
                    "no authoritative current master lineage",
                    "no permanent identifier",
                    "no ACTIONS record explaining the disappearance",
                    "terminates exactly at the defective 2026-06-12 source boundary",
                    "recent price rows cannot be trusted as complete single-vintage histories",
                    "a surrogate would preserve data whose identity and continuation are unproven",
                ],
                "excluded_from": ["governed corpus", "ranking", "proxy",
                                  "completeness calculations"],
            }

        exclusions.append(record)
        # The crosswalk row carries the terminal disposition and the owner-required preservation
        # fields; the full evidence lives in the exclusion artifact, bound by digest.
        row |= {"disposition": klass, "permaticker": None, "current_ticker": None,
                "disposition_authority": DISPOSITION_AUTHORITY,
                "legacy_ticker": key, "legacy_name": record["legacy_name"],
                "historical_span": record["priced_span_in_corpus"],
                "decision_window_row_count": record["decision_window_row_count"],
                "permanent_identity_unavailable_because": record[
                    "permanent_identity_unavailable_because"]}
        if klass == EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING:
            row |= {"authoritative_delisting_action": record["authoritative_delisting_action"],
                    "authoritative_delisting_date": record["authoritative_delisting_date"]}
        else:
            row |= {"terminates_at_defective_source_boundary":
                    record["terminates_at_defective_source_boundary"], "quarantined": True}

    rows.sort(key=lambda r: r["old_ticker_key"])
    payload = canonical_json({"kind": "governed_universe_key_crosswalk", "version": "v2.0",
                              "legacy_governed_universe_sha256": legacy,
                              "source_key_count": len(rows), "rows": rows})
    (out / "universe_crosswalk_v2.json").write_bytes(payload)
    crosswalk_sha = hashlib.sha256(payload).hexdigest()

    resolved = sorted({r["permaticker"] for r in rows if r.get("permaticker")})
    perm_sha = hashlib.sha256(canonical_json(resolved)).hexdigest()

    # The owner finalized `governed_permanent_universe_sha256` CONDITIONALLY. Enforce the condition
    # rather than restate it: exactly the mapped identities, exactly that many, exactly that digest.
    if len(resolved) != PERMANENT_IDENTITY_COUNT or perm_sha != PERMANENT_UNIVERSE_SHA256:
        raise SystemExit(
            f"the permanent universe does not satisfy the owner's finalization condition: "
            f"{len(resolved)} identities digesting to {perm_sha}, expected "
            f"{PERMANENT_IDENTITY_COUNT} digesting to {PERMANENT_UNIVERSE_SHA256}")
    if len(rows) != SOURCE_KEY_COUNT:
        raise SystemExit(f"source key count {len(rows)} != ratified {SOURCE_KEY_COUNT}")

    # The complete exclusion artifact (all five terminal exclusions) and the quarantine/evidence
    # artifact (the three unresolved-source-master keys), each bound by its own digest.
    excl_payload = canonical_json({
        "kind": "governed_universe_exclusions", "version": "v2.0",
        "disposition_authority": DISPOSITION_AUTHORITY,
        "legacy_governed_universe_sha256": legacy,
        "governed_permanent_universe_sha256": perm_sha,
        "synthetic_identities_authorized": False,
        "excluded_documented_historical_delisting_count": sum(
            1 for e in exclusions if e["disposition"] == EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING),
        "excluded_unresolved_source_master_count": sum(
            1 for e in exclusions if e["disposition"] == EXCLUDED_UNRESOLVED_SOURCE_MASTER),
        "exclusions": exclusions,
    })
    (out / "universe_exclusions_v2.json").write_bytes(excl_payload)
    exclusions_sha = hashlib.sha256(excl_payload).hexdigest()

    quarantined = [e for e in exclusions
                   if e["disposition"] == EXCLUDED_UNRESOLVED_SOURCE_MASTER]
    quar_payload = canonical_json({
        "kind": "governed_universe_quarantine_unresolved_source_master", "version": "v2.0",
        "disposition_authority": DISPOSITION_AUTHORITY,
        "common_termination_boundary": SOURCE_MASTER_BOUNDARY.isoformat(),
        "not_a_finding_of_invalidity_or_delisting": True,
        "must_not_enter": ["governed corpus", "ranking", "proxy", "completeness calculations"],
        "keys": quarantined,
    })
    (out / "quarantine_unresolved_source_master_v2.json").write_bytes(quar_payload)
    quarantine_sha = hashlib.sha256(quar_payload).hexdigest()

    census: dict[str, int] = defaultdict(int)
    for r in rows:
        census[r["disposition"]] += 1

    print("\n=== disposition census ===")
    for k in sorted(census):
        print(f"   {k:<32} {census[k]:>7,}")
    print(f"   {'TOTAL':<32} {sum(census.values()):>7,}")
    assert sum(census.values()) == len(old_keys), "dispositions do not reconcile to U_old"

    collapse_groups = {p: g for p, g in groups.items() if len(g) > 1}
    print("\n=== universe sizes ===")
    print(f"   governed_source_key_count        : {len(old_keys):,}")
    print(f"   governed_permanent_identity_count: {len(resolved):,}")
    print(f"   alias_collapse_groups            : {len(collapse_groups):,}")
    print(f"   keys absorbed by alias collapse  : {sum(len(g) for g in collapse_groups.values()) - len(collapse_groups):,}")
    n_delist = sum(1 for e in exclusions
                   if e["disposition"] == EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING)
    n_srcmaster = len(quarantined)
    print("\n=== terminal dispositions (owner ruling 2026-07-29) ===")
    print(f"   legacy source keys                        : {len(rows):>7,}")
    print(f"   mapped permanent identities               : {len(resolved):>7,}")
    print(f"   documented-delist exclusions              : {n_delist:>7,}")
    print(f"   unresolved-source-master exclusions       : {n_srcmaster:>7,}")
    print(f"   unadjudicated keys                        : "
          f"{len(rows) - len(resolved) - n_delist - n_srcmaster:>7,}")
    for e in exclusions:
        print(f"     {e['old_ticker_key']:<6} {e['disposition']:<40} "
              f"rows={e['price_row_count']:>6,} window={e['decision_window_row_count']:>4} "
              f"{e['priced_span_in_corpus'][0]}..{e['priced_span_in_corpus'][1]}")

    print("\n=== identities ===")
    print(f"   legacy_governed_universe_sha256       : {legacy}")
    print(f"   governed_universe_key_crosswalk_sha256: {crosswalk_sha}")
    print(f"   governed_permanent_universe_sha256    : {perm_sha}  (FINALIZED, condition enforced)")
    print(f"   governed_universe_exclusions_sha256   : {exclusions_sha}")
    print(f"   governed_universe_quarantine_sha256   : {quarantine_sha}")

    blocking = [r for r in rows if r["disposition"] in
                (UNRESOLVED_NO_PERMANENT_ID, AMBIGUOUS_MULTIPLE_LINEAGES, INVALID_SOURCE_RECORD)]
    print(f"\n=== FAIL-CLOSED: {len(blocking)} key(s) require owner adjudication ===")
    for r in blocking[:40]:
        print(f"   {r['old_ticker_key']:<8} {r['disposition']:<30} rows={r['old_row_count']:>6,} "
              f"{r['old_first_priced']}..{r['old_last_priced']}  {r.get('reason','')[:70]}")
    if len(blocking) > 40:
        print(f"   … and {len(blocking)-40} more")

    (out / "crosswalk_summary.json").write_text(json.dumps({
        "legacy_governed_universe_sha256": legacy,
        "governed_universe_key_crosswalk_sha256": crosswalk_sha,
        "governed_permanent_universe_sha256": perm_sha,
        "governed_universe_exclusions_sha256": exclusions_sha,
        "governed_universe_quarantine_sha256": quarantine_sha,
        "governed_source_key_count": len(old_keys),
        "governed_permanent_identity_count": len(resolved),
        "excluded_documented_historical_delisting_count": n_delist,
        "excluded_unresolved_source_master_count": n_srcmaster,
        "unresolved_key_count": len(rows) - len(resolved) - n_delist - n_srcmaster,
        "disposition_authority": DISPOSITION_AUTHORITY,
        "synthetic_identities_authorized": False,
        "governed_session": session.isoformat(),
        "required_history_sessions": REQUIRED_HISTORY_SESSIONS,
        "decision_window": [w0.isoformat(), w1.isoformat()],
        "decision_window_sessions_in_corpus": int(window_sessions[0]),
        "decision_window_max_session_in_corpus": _iso(window_sessions[1]),
        "alias_collapse_groups": len(collapse_groups),
        "disposition_census": dict(sorted(census.items())),
        "blocking_count": len(blocking),
        "blocking": [{k: r.get(k) for k in
                      ("old_ticker_key", "disposition", "old_row_count", "old_first_priced",
                       "old_last_priced", "reason", "candidates")} for r in blocking],
        "alias_groups": {p: g for p, g in sorted(collapse_groups.items())},
    }, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
