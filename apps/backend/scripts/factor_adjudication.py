"""Single source of truth for factor-store staleness adjudication.

Two components consume the same governed evidence artifact
(``_factor_exhaustion_evidence.json``) and, before this module existed, reached
*different verdicts from it*:

* ``scripts/factor_refresh.py`` — the refresh verifier, gating the staging→live swap.
  It **derived** each classification from live facts and refused evidence it could not
  corroborate, then gated on a coverage figure that ignored the classification it had
  just computed.
* ``deploy/aws/factor-freshness.sh`` — the readiness watchdog, publishing the verdict
  that vetoes dispatch. It **trusted** the ``expected_classification`` written in the
  file, and removed those names from the coverage denominator.

On 2026-08-11 that produced the contradiction this module removes: the watchdog
published ``data_freshness=PASS`` with ``coverage=1.0000`` while the refresh aborted
with ``coverage=0.9784`` — from the same artifact, the same store and the same
universe. Adjudication that does not reach the gate it exists to inform is decoration.

Three asymmetries are closed here, and each is a named, tested rule:

1. **Classification is derived, never declared.** ``expected_classification`` in the
   evidence file is an input to be checked, not a verdict to be believed.
   :func:`classify_stale_symbol` recomputes it from frontiers, corroboration and
   operational facts that the caller supplies from the live system.
2. **One gating coverage figure.** :func:`gating_coverage` is the only figure any gate
   may compare against a threshold. Attributed names leave the denominator; they
   neither count against the pool nor pad it.
3. **One exemption ceiling.** Attribution above :func:`exemption_ceiling` is itself a
   failure — an evidence file excusing a large slice of the pool is a suppressed check,
   not a healthy store — and voids attribution for the whole run.

⚠ **This module must import nothing but the standard library**, and in particular must
not import the ``app`` package or ``duckdb``. Its two callers run in different places:
the verifier runs in a one-off container against raw stores, and the watchdog ships
*this file's source over stdin* into whatever backend image happens to be deployed.
That is deliberate — see ``deploy/aws/factor-freshness.sh``. The watchdog must never
depend on a module baked into the running image, because the image may predate it and
a readiness watchdog must never become the reason to deploy. Shipping the source keeps
one implementation without creating that coupling.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- verdicts

#: A universe symbol's freshness verdict at adjudication time.
FRESH = "FRESH"
PROVIDER_EXHAUSTED = "PROVIDER_EXHAUSTED"
PROVIDER_NOT_COVERED = "PROVIDER_NOT_COVERED"
FAILED_OR_UNEXPLAINED = "FAILED_OR_UNEXPLAINED"

#: Verdicts that are attributable — a refresh can never make them fresh HERE, and each
#: carries per-symbol evidence saying why. They are never counted as fresh.
ATTRIBUTED = (PROVIDER_EXHAUSTED, PROVIDER_NOT_COVERED)

#: The only classifications an evidence record may claim. Anything else is ignored
#: rather than trusted — an unrecognised label must not become a silent exemption.
CLAIMABLE = frozenset(ATTRIBUTED)

#: The timezone the refresh schedule is expressed in. The refresh container runs UTC and the
#: watchdog computes ET; evidence ages in DAYS, so two clocks over one artifact means four
#: hours every evening in which one component calls a record expired and the other does not.
#: One definition, HERE, because this module is the one both of them already share.
DEFAULT_SCHEDULE_TZ = "America/New_York"


def schedule_today(tz_name: str = DEFAULT_SCHEDULE_TZ) -> date:
    """Today's date in the refresh schedule's timezone. The RUN DATE, on one calendar.

    ⚠ This is the clock for **evidence age**, and it is not the store frontier. Conflating the
    two is the defect found in review on 2026-08-28: ``factor_evidence.generate`` dated its own
    run by ``max(stage_effective)`` — the newest SEP row, which at 06:00 ET is always the PRIOR
    trading day — while stamping ``adjudicated_at_utc`` with the current instant. Every record
    it wrote therefore claimed to be observed AFTER its own run date, which
    :func:`classify_stale_symbol` correctly refuses, so the generator refused every record it
    produced and regeneration could never clear a name. The frontier is a fact about the DATA;
    it is not a clock.

    Falls back to UTC only when the zone cannot be resolved (no tzdata), and says so, because a
    silent fallback would reintroduce the two-calendar problem this exists to remove.
    """
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:  # noqa: BLE001 - tzdata absent; UTC is the honest fallback
        print(f"WARNING could not resolve schedule timezone {tz_name!r}; using UTC")
        return datetime.now(UTC).date()


#: How long a corroboration observation may be relied upon before it must be observed
#: again. The corroboration block records what an alternate source said AT ONE INSTANT;
#: it is provenance, not a live feed. Bounding it explicitly is what stops a past
#: observation from decaying into a silent misclassification — see
#: :func:`classify_stale_symbol`. Expiry is a LOUD, named failure that says regenerate.
MAX_EVIDENCE_AGE_DAYS = 30


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return None


def _observed_on(v: Any) -> date | None:
    """Calendar date of an observation timestamp, e.g. ``2026-08-11T19:30:57Z``.

    Separate from :func:`_as_date` because that one takes a plain date and would reject
    a full timestamp. Only the date part matters: the tolerance this feeds is measured
    in days, so sub-day precision would imply an accuracy the source does not have.
    """
    d = _as_date(v)
    if d is not None:
        return d
    s = str(v).strip()
    return _as_date(s[:10]) if len(s) >= 10 else None


# ------------------------------------------------------------------------ evidence io


#: Why a stale symbol ended up ``FAILED_OR_UNEXPLAINED``. These are DIAGNOSTIC labels, never
#: verdicts: nothing here can change what :func:`classify_stale_symbol` decided. They exist
#: because ``UNEXPLAINED: ['WBS']`` — the line that aborted three consecutive production
#: refreshes on 2026-08-25/26/27 — is indistinguishable between four operationally different
#: situations that need four different operator responses. Three of them are cleared by
#: regenerating the artifact; the fourth is a real finding about the symbol and is not.
EVIDENCE_ABSENT = "EVIDENCE_ABSENT"
EVIDENCE_NOT_CLAIMABLE = "EVIDENCE_NOT_CLAIMABLE"
EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"
EVIDENCE_PRESENT_REFUSED = "EVIDENCE_PRESENT_REFUSED"

#: Operator prose per diagnosis, held HERE so the refresh verifier's abort line and the
#: watchdog's alert say the SAME words about the same condition. Two components describing one
#: state in two vocabularies is how an operator comes to believe they are two states.
EVIDENCE_DIAGNOSIS_DETAIL = {
    EVIDENCE_ABSENT: (
        "no evidence record exists for this symbol at all - the artifact predates the name "
        "going stale and nothing regenerated it; regenerate (scripts/factor_evidence.py)"
    ),
    EVIDENCE_NOT_CLAIMABLE: (
        "an evidence record exists but claims no adjudicable classification, so it was "
        "dropped before adjudication - regenerate the artifact"
    ),
    EVIDENCE_EXPIRED: (
        "the record's corroboration observation is older than the permitted window - it is "
        "provenance, not a live signal, and must be re-observed; regenerate the artifact"
    ),
    EVIDENCE_PRESENT_REFUSED: (
        "a CURRENT evidence record was adjudicated and REFUSED on its merits - this is a real "
        "finding about the symbol, not a gap in the artifact, and REGENERATING EVIDENCE WILL "
        "NOT CLEAR IT"
    ),
}


def load_evidence_records(
    path: str | Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], str, str]:
    """Read the artifact. Returns ``(all_by_symbol, claimable_by_symbol, note, status)``.

    ``claimable_by_symbol`` is what adjudication consumes, and is exactly what
    :func:`load_evidence` returns. ``all_by_symbol`` additionally retains records claiming
    nothing adjudicable, because "a record was DROPPED" and "no record ever existed" are
    different facts about the system and only the diagnosis layer needs to tell them apart.

    Adjudication must never see the dropped ones, and does not: they are returned in a
    SEPARATE mapping, and :func:`adjudicate` is only ever handed the claimable one. Returning
    them from the same function is what keeps a single parser and a single set of failure
    labels — a second reader would be a second chance to disagree.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, {}, "evidence artifact ABSENT - nothing attributable", "absent"
    except Exception as exc:  # noqa: BLE001 - any parse failure is the same verdict
        return (
            {},
            {},
            f"evidence artifact UNREADABLE ({type(exc).__name__}) - nothing attributable",
            "unreadable",
        )

    records = raw.get("symbols") if isinstance(raw, dict) else None
    if not isinstance(records, list):
        return (
            {},
            {},
            "evidence artifact MALFORMED (no 'symbols' list) - nothing attributable",
            "malformed",
        )

    all_by_symbol: dict[str, dict[str, Any]] = {}
    claimable: dict[str, dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        symbol = str(rec.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        all_by_symbol[symbol] = rec
        claim = str(rec.get("expected_classification", "")).strip().upper()
        if claim in CLAIMABLE:
            claimable[symbol] = rec
    generated = raw.get("generated_at_utc") if isinstance(raw, dict) else None
    return (
        all_by_symbol,
        claimable,
        f"{len(claimable)} adjudicable record(s), evidence generated {generated}",
        "ok",
    )


def diagnose_unexplained(
    symbols: Sequence[str],
    *,
    all_records: dict[str, dict[str, Any]],
    claimable_records: dict[str, dict[str, Any]],
    as_of: date,
    max_evidence_age_days: int = MAX_EVIDENCE_AGE_DAYS,
) -> dict[str, str]:
    """Label each unexplained symbol with WHY it is unexplained. Pure; no I/O.

    ⚠ Reporting, not policy. Deliberately incapable of changing a verdict: it takes the
    already-decided unexplained set as input and only names which of four conditions produced
    it. It lives in this module rather than in either caller so the verifier and the watchdog
    cannot invent two vocabularies for one state — the exact failure ADR 0051 exists to end.

    :data:`EVIDENCE_PRESENT_REFUSED` is the one that means *investigate the symbol*. The other
    three mean *the artifact is out of date* and are cleared by regeneration.

    ⚠ The order of the tests below is deliberate, and NOT "claimable first". A record written
    by ``scripts/factor_evidence.py`` for a name the shared rule refused carries a current
    observation and a recorded derivation, but claims nothing adjudicable — because the rule
    itself refused it. Testing claimability first would label that ``EVIDENCE_NOT_CLAIMABLE``,
    whose advice is "regenerate", and regeneration is exactly what will NOT help. Freshness of
    the observation is therefore judged before claimability, and a recorded derivation is
    treated as proof the rule already ran.
    """
    out: dict[str, str] = {}
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip().upper()
        record = all_records.get(symbol)
        if record is None:
            out[symbol] = EVIDENCE_ABSENT
            continue
        observed = _observed_on(record.get("adjudicated_at_utc"))
        if observed is None or (as_of - observed).days > max_evidence_age_days:
            out[symbol] = EVIDENCE_EXPIRED
            continue
        if symbol in claimable_records or record.get("generator_derived_classification"):
            # Either adjudication was handed this record and refused it, or the generator
            # applied the same shared rule at write time and recorded that it refused. Both
            # mean the rule has seen current observations for this name.
            out[symbol] = EVIDENCE_PRESENT_REFUSED
            continue
        out[symbol] = EVIDENCE_NOT_CLAIMABLE
    return out


def evidence_expiry(
    records: dict[str, dict[str, Any]],
    *,
    as_of: date,
    max_evidence_age_days: int = MAX_EVIDENCE_AGE_DAYS,
) -> dict[str, Any]:
    """How far is this artifact from expiring? Pure; no I/O.

    Every record carries ONE observation timestamp, and in a hand-built artifact they are all
    the SAME timestamp — so attributions do not expire one at a time, they expire together. On
    2026-08-27 the live artifact held eleven records observed ``2026-08-11``: eleven
    simultaneous expiries due ``2026-09-10``, after which the refresh would have failed on
    eleven names rather than one. A control whose failure mode is a cliff must report its
    distance from that cliff while there is still time to act, which is what this returns.

    ``days_remaining`` goes negative once passed. A record with no parseable observation time
    is counted in ``undated_symbols`` and treated as already expired — an undatable
    observation cannot be shown to be current, and unproven is not permission.
    """
    expiries: list[date] = []
    undated: list[str] = []
    expired_now: list[str] = []
    for symbol, rec in sorted(records.items()):
        observed = _observed_on(rec.get("adjudicated_at_utc"))
        if observed is None:
            undated.append(symbol)
            expired_now.append(symbol)
            continue
        expiries.append(observed + timedelta(days=max_evidence_age_days))
        if (as_of - observed).days > max_evidence_age_days:
            expired_now.append(symbol)
    earliest = min(expiries) if expiries else None
    return {
        "record_count": len(records),
        "undated_symbols": undated,
        "earliest_expiry_on": earliest.isoformat() if earliest else None,
        "days_remaining": (earliest - as_of).days if earliest else None,
        "expired_symbols": sorted(expired_now),
        "expired_count": len(expired_now),
        "max_evidence_age_days": max_evidence_age_days,
    }


def load_evidence(path: str | Path) -> tuple[dict[str, dict[str, Any]], str, str]:
    """Read the exhaustion evidence artifact. Returns ``(by_symbol, note, status)``.

    The adjudication-facing reader. Only records that *claim* one of :data:`CLAIMABLE` are
    returned: the claim is not honoured here — :func:`classify_stale_symbol` re-derives the
    verdict — but a record claiming nothing adjudicable is not evidence of anything.

    ``status`` is one of ``ok``/``absent``/``unreadable``/``malformed``. It is returned
    separately from the note because a broken artifact is a FINDING in its own right:
    the evidence file is a control, and a caller must be able to raise it even on a run
    where nothing happens to be stale and the absence would otherwise pass silently.

    Fail-closed in every direction: a missing, unreadable, malformed or
    wrongly-shaped artifact yields an EMPTY mapping, so no symbol can be attributed
    and every stale name falls through to ``FAILED_OR_UNEXPLAINED``. The note is
    operator prose naming which of those happened; callers surface it verbatim.
    """
    _all, claimable, note, status = load_evidence_records(path)
    return claimable, note, status


def exemption_ceiling(universe_size: int) -> int:
    """Most names that may be attributed before attribution is itself a failure.

    An exemption list is structurally a way to switch the freshness check off. A real
    provider outage looks exactly like a large exhaustion list, so bound it: excusing
    more than 5% of the pool (floor 5 names, for small universes) is treated as the
    evidence artifact being used to suppress an outage.
    """
    return max(5, int(universe_size * 0.05))


# ---------------------------------------------------------------- per-symbol verdict


def classify_stale_symbol(
    symbol: str,
    *,
    live_last: date | None,
    stage_last: date | None,
    cutoff: date,
    tolerance_days: int,
    as_of: date,
    evidence: dict[str, Any] | None,
    held_qty: float,
    open_orders: int,
    registered_in: Sequence[str],
    max_evidence_age_days: int = MAX_EVIDENCE_AGE_DAYS,
) -> tuple[str, str]:
    """Classify one non-fresh universe symbol. Pure: no I/O, provider or store.

    Two distinct reasons a symbol can never be made fresh by this provider, and the
    alternate source is what tells them apart:

    ``PROVIDER_EXHAUSTED``    the instrument stopped trading — the alternate source
                              stops too (a delisting, merger or rename).
    ``PROVIDER_NOT_COVERED``  the instrument trades normally but is outside this
                              provider's subscription — the alternate source is current
                              (e.g. ETFs under a Core US Equities plan that excludes the
                              fund price dataset).

    Everything else is ``FAILED_OR_UNEXPLAINED``.

    ⚠ "the provider returned nothing newer" is NOT sufficient on its own — it equally
    describes a transient outage, a malformed response, an omitted request, an
    entitlement problem or a symbol-specific ingestion bug. Every condition must hold in
    the same governed run; anything unproven fails closed.

    ``evidence`` supplies only what adjudication cannot observe for itself: the
    per-symbol request outcome and an independent lifecycle signal. Frontiers, holdings
    and registration are recomputed by the caller and cross-checked here, never taken on
    trust.

    ⚠ **The corroboration block is provenance, not a live signal.** It records what the
    alternate source said at ``evidence["adjudicated_at_utc"]`` and nothing more. Its
    dates are therefore judged against the cutoff in force AT THAT MOMENT
    (``observed_on - tolerance_days``), never against the caller's current ``cutoff``,
    which advances with the store frontier. ``as_of`` and ``max_evidence_age_days``
    bound how long that past observation may be relied upon; past the bound the symbol
    fails with an explicit *expired, regenerate* reason. This is the fourth asymmetry,
    closed 2026-08-19: an observation compared against a standard that moved after it
    was taken is an anachronism, and it silently converted ten correctly-attributed
    names into ``FAILED_OR_UNEXPLAINED`` on 2026-08-18 while blaming the alternate
    source. Static evidence fields are RETAINED for audit and history — the fix changes
    what classification *consumes*, never what the artifact *keeps*.

    A caller assessing a single store (the watchdog, which has no staging copy) passes
    the same value for ``live_last`` and ``stage_last``. The frontier-equality rule then
    holds trivially, which is correct: there is no pending swap to disprove.
    """
    if stage_last is not None and stage_last >= cutoff:
        return FRESH, "stage frontier is within tolerance"

    # --- the request itself must be proven to have happened and succeeded ---
    if not evidence:
        return FAILED_OR_UNEXPLAINED, "no exhaustion evidence supplied"
    if str(evidence.get("symbol", "")).strip().upper() != symbol:
        return FAILED_OR_UNEXPLAINED, "evidence symbol mismatch"
    if evidence.get("requested") is not True:
        return FAILED_OR_UNEXPLAINED, "symbol was not requested from the provider"
    if evidence.get("request_status") != "ok":
        return FAILED_OR_UNEXPLAINED, f"provider request status {evidence.get('request_status')!r}"
    rows = evidence.get("provider_rows_after_live_frontier")
    if rows is None:
        return FAILED_OR_UNEXPLAINED, "provider row count after frontier not reported"
    if rows != 0:
        return (
            FAILED_OR_UNEXPLAINED,
            f"provider returned {rows} newer row(s); ingestion missed them",
        )
    if stage_last != live_last:
        return FAILED_OR_UNEXPLAINED, f"staging frontier {stage_last} != live {live_last}"

    # --- an independent source must be reachable and current ---------------
    #
    # ⚠ The corroboration block is a RECORD OF A PAST OBSERVATION, not a live feed: the
    # alternate source was queried once, at generation time, and the answer was frozen
    # into the artifact. Judging that frozen answer against TODAY's ``cutoff`` — which
    # advances with the store frontier — is an anachronism, and it is what broke the
    # 2026-08-18/19 refreshes: nothing about the observation changed, but the cutoff
    # walked past it and every attributed name flipped to FAILED_OR_UNEXPLAINED at once,
    # with a reason that blamed the alternate source instead of the expiry. A stale
    # observation must expire LOUDLY and say so; it must never decay into a verdict.
    #
    # So: currency is judged against the cutoff IN FORCE WHEN THE OBSERVATION WAS MADE,
    # and the observation's age is bounded separately and explicitly. The static fields
    # stay exactly where they are — they remain the provenance of what was seen, when,
    # and under which authorization; they simply stop being read as a live signal.
    corr = evidence.get("corroboration") or {}
    for field in ("source", "control_symbol", "control_last_date"):
        if not corr.get(field):
            return FAILED_OR_UNEXPLAINED, f"corroboration missing {field}"

    observed_on = _observed_on(evidence.get("adjudicated_at_utc"))
    if observed_on is None:
        # Without an observation time the frozen dates cannot be interpreted at all:
        # there is no way to tell a fresh probe from a year-old one.
        return FAILED_OR_UNEXPLAINED, "corroboration records no observation time"
    if observed_on > as_of:
        return (
            FAILED_OR_UNEXPLAINED,
            f"corroboration observed {observed_on}, after the run date {as_of}",
        )
    age_days = (as_of - observed_on).days
    if age_days > max_evidence_age_days:
        return (
            FAILED_OR_UNEXPLAINED,
            f"corroboration evidence expired: observed {observed_on}, {age_days}d old "
            f"(limit {max_evidence_age_days}d) — regenerate the evidence artifact",
        )

    #: The cutoff that applied when the observation was made — the only standard it can
    #: fairly be held to.
    observed_cutoff = observed_on - timedelta(days=tolerance_days)

    c_ctl = _as_date(corr["control_last_date"])
    if c_ctl is None or c_ctl < observed_cutoff:
        # A stale control proves the alternate path was broken AT OBSERVATION TIME, not
        # that the subject symbol is dead. Without it every symbol would look
        # attributable during an outage of the corroborating source.
        return (
            FAILED_OR_UNEXPLAINED,
            f"corroboration control was not current when observed on {observed_on}; "
            "alternate source unproven",
        )
    c_last = _as_date(corr.get("last_date"))

    alive_elsewhere = c_last is not None and c_last >= observed_cutoff

    # --- operational requirements -----------------------------------------
    # A held name needs a continuing valuation and exit path. That is satisfied only
    # when the alternate source is currently pricing it.
    if (held_qty or open_orders) and not alive_elsewhere:
        need = f"held qty {held_qty}" if held_qty else f"{open_orders} open order(s)"
        return FAILED_OR_UNEXPLAINED, f"{need} with no proven alternate price source"
    if registered_in and not alive_elsewhere:
        return (
            FAILED_OR_UNEXPLAINED,
            f"registered by {sorted(registered_in)} with no alternate source",
        )

    if alive_elsewhere:
        if live_last is not None:
            # It once had provider history and the provider stopped while the instrument
            # kept trading — that is a coverage change, not a dead name, and it deserves
            # a look rather than a silent pass.
            return FAILED_OR_UNEXPLAINED, (
                f"provider stopped at {live_last} but {corr['source']} is current to {c_last}: "
                "coverage regression, not exhaustion"
            )
        return PROVIDER_NOT_COVERED, (
            f"outside provider coverage; trades normally — {corr['source']} current to {c_last}"
        )

    if live_last is None:
        return FAILED_OR_UNEXPLAINED, "no history in either source; symbol unverifiable"
    if live_last >= cutoff:
        return FAILED_OR_UNEXPLAINED, "live frontier is not actually stale"
    return PROVIDER_EXHAUSTED, (
        f"ceased trading: provider last {live_last}, {corr['source']} last {c_last}, "
        f"control {corr['control_symbol']} current to {c_ctl}"
    )


# ------------------------------------------------------------------- whole-run result


def adjudicate(
    universe: Sequence[str],
    *,
    stage_effective: dict[str, Any],
    live_effective: dict[str, Any],
    non_fresh: Sequence[str],
    cutoff: date,
    tolerance_days: int,
    as_of: date,
    evidence: dict[str, dict[str, Any]],
    operational: dict[str, dict[str, Any]],
    max_evidence_age_days: int = MAX_EVIDENCE_AGE_DAYS,
) -> dict[str, Any]:
    """Adjudicate every non-fresh name and compute the run's coverage figures.

    ``non_fresh`` is supplied by the caller because each caller measures it against its
    own store (staging for the verifier, live for the watchdog); everything downstream
    of that measurement is decided here so the two cannot diverge.

    ``tolerance_days`` and ``as_of`` are passed through to
    :func:`classify_stale_symbol` so a frozen corroboration observation is judged
    against the cutoff of its own moment and its age is bounded explicitly.
    """
    buckets: dict[str, list[str]] = {
        PROVIDER_EXHAUSTED: [],
        PROVIDER_NOT_COVERED: [],
        FAILED_OR_UNEXPLAINED: [],
    }
    records: list[dict[str, Any]] = []
    for sym in sorted(non_fresh):
        facts = operational.get(sym, {})
        verdict, reason = classify_stale_symbol(
            sym,
            live_last=_as_date(live_effective.get(sym)),
            stage_last=_as_date(stage_effective.get(sym)),
            cutoff=cutoff,
            tolerance_days=tolerance_days,
            as_of=as_of,
            max_evidence_age_days=max_evidence_age_days,
            evidence=evidence.get(sym),
            held_qty=float(facts.get("held_qty") or 0),
            open_orders=int(facts.get("open_orders") or 0),
            registered_in=facts.get("registered_in") or [],
        )
        buckets[verdict].append(sym)
        records.append(
            {
                "symbol": sym,
                "classification": verdict,
                "reason": reason,
                "live_effective_last": str(live_effective.get(sym)),
                "stage_effective_last": str(stage_effective.get(sym)),
                "held_qty": facts.get("held_qty", 0),
                "open_orders": facts.get("open_orders", 0),
                "registered_in": facts.get("registered_in") or [],
                "evidence": evidence.get(sym),
            }
        )

    total = len(universe)
    attributed = sorted(buckets[PROVIDER_EXHAUSTED] + buckets[PROVIDER_NOT_COVERED])
    notes: list[str] = []
    problems: list[str] = []

    # Attribution above the ceiling is voided ENTIRELY rather than trimmed: a partial
    # exemption chosen by sort order would be arbitrary, and the condition being
    # detected is "this artifact is excusing too much", not "these particular names".
    ceiling = exemption_ceiling(total)
    if len(attributed) > ceiling:
        problems.append(
            f"DATA_EXEMPTION_IMPLAUSIBLE: {len(attributed)} of {total} universe names are "
            f"adjudicated provider-exhausted/not-covered, above the {ceiling} ceiling - that "
            "is too much of the pool to excuse, and the evidence artifact is being used to "
            "suppress a real outage; NOTHING was attributed for this run"
        )
        for sym in attributed:
            buckets[FAILED_OR_UNEXPLAINED].append(sym)
            for rec in records:
                if rec["symbol"] == sym:
                    rec["classification"] = FAILED_OR_UNEXPLAINED
                    rec["reason"] = "attribution voided: exemption ceiling exceeded"
        buckets[PROVIDER_EXHAUSTED], buckets[PROVIDER_NOT_COVERED] = [], []
        attributed = []
        buckets[FAILED_OR_UNEXPLAINED].sort()

    assessable = [t for t in universe if t not in set(attributed)]
    fresh_syms = sorted(set(universe) - set(non_fresh))
    covered = len([t for t in assessable if t not in set(non_fresh)])

    if universe and not assessable:
        problems.append(
            "DATA_PER_NAME_UNASSESSABLE: every universe name is attributed, so per-name "
            "freshness measured nothing at all - an exemption list that covers the whole "
            "pool is a suppressed check, not a healthy store"
        )
    if attributed:
        notes.append(
            f"DATA_EXEMPT_ADJUDICATED: {len(attributed)} of {total} universe names excluded "
            "from per-name freshness as adjudicated provider-exhausted/not-covered"
        )

    return {
        "universe_size": total,
        "assessable": assessable,
        "assessable_count": len(assessable),
        "attributed": attributed,
        "attributed_count": len(attributed),
        "exemption_ceiling": ceiling,
        "fresh_count": len(fresh_syms),
        "covered": covered,
        # The honest, evidence-blind figure. Reported ALWAYS so attribution can never
        # hide how much of the pool the provider actually delivered. Never gated on.
        "raw_coverage": (len(fresh_syms) / total) if total else 0.0,
        "provider_exhausted_symbols": buckets[PROVIDER_EXHAUSTED],
        "provider_not_covered_symbols": buckets[PROVIDER_NOT_COVERED],
        "failed_or_unexplained_symbols": buckets[FAILED_OR_UNEXPLAINED],
        "failed_or_unexplained_count": len(buckets[FAILED_OR_UNEXPLAINED]),
        "notes": notes,
        "problems": problems,
        "records": records,
    }


def gating_coverage(result: dict[str, Any]) -> float:
    """THE coverage figure. The only one any gate may compare against a threshold.

    **Frozen semantics:** ``covered / assessable``, where ``assessable`` is the universe
    minus attributed names, and ``covered`` counts assessable names that are fresh.

    An attributed name leaves the denominator entirely — it neither counts against the
    pool nor pads it. The alternatives were both rejected: counting it as *uncovered*
    (the refresh verifier's old behaviour) asks a name to satisfy a threshold it can
    never satisfy, which is what froze the live store from 2026-08-11; counting it as
    *covered* would let a growing exemption list manufacture a passing grade. Measuring
    only what is measurable is the honest reading, and the exemption ceiling is what
    stops the denominator being hollowed out.

    An empty assessable set returns 0.0 — nothing was measured, which is a failure, not
    a vacuous pass. :func:`adjudicate` raises ``DATA_PER_NAME_UNASSESSABLE`` alongside.
    """
    assessable = result.get("assessable_count") or 0
    if not assessable:
        return 0.0
    return result["covered"] / assessable


# --------------------------------------------------------------- operational facts


def operational_facts(app_db: str | Path, universe: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Held quantity, open orders and registration per symbol, read from the app DB.

    Recomputed rather than accepted from the evidence artifact: a stale or crafted
    file must not be able to declare a held name unheld and so write it off.
    """
    out: dict[str, dict[str, Any]] = {
        s: {"held_qty": 0.0, "open_orders": 0, "registered_in": []} for s in universe
    }
    con = sqlite3.connect(f"file:{app_db}?mode=ro", uri=True)
    try:
        for tkr, qty in con.execute(
            "SELECT sym.ticker, SUM(p.qty) FROM positions p "
            "JOIN symbols sym ON sym.id = p.symbol_id WHERE p.qty <> 0 GROUP BY sym.ticker"
        ):
            if tkr in out:
                out[tkr]["held_qty"] = float(qty or 0)
        try:
            for tkr, n in con.execute(
                "SELECT sym.ticker, COUNT(*) FROM orders o JOIN symbols sym ON sym.id = o.symbol_id "
                "WHERE o.status NOT IN ('FILLED','CANCELED','EXPIRED','REJECTED') GROUP BY sym.ticker"
            ):
                if tkr in out:
                    out[tkr]["open_orders"] = int(n or 0)
        except sqlite3.Error:  # pragma: no cover - orders schema drift
            pass
        for sid, status, raw in con.execute("SELECT id, status, symbols_json FROM strategies"):
            try:
                syms = json.loads(raw or "[]")
            except (TypeError, ValueError):
                continue
            if not isinstance(syms, list):
                continue
            for s in syms:
                key = str(s).strip().upper()
                if key in out:
                    out[key]["registered_in"].append(f"{sid}:{status}")
    finally:
        con.close()
    return out
