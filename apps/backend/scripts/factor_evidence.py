"""Regenerate the factor-store exhaustion evidence artifact from OBSERVED facts.

WHY THIS EXISTS. ``_factor_exhaustion_evidence.json`` is a control the refresh verifier and
the readiness watchdog both consume, and until this script existed **nothing in the
repository wrote it**. The production artifact was hand-built once, on 2026-08-11, with
eleven records. Two consequences followed, and both reached the live book:

* **A name that goes attributable-stale after the artifact was written has no record**, so it
  adjudicates ``FAILED_OR_UNEXPLAINED`` and the staging→live swap aborts. ``EA`` is in the
  artifact because a human added it on 2026-08-17. ``WBS`` is the next name: it halted the
  06:00 ET refresh on 2026-08-25, 08-26 and 08-27, freezing the live store at SEP
  ``2026-08-21``. There would have been another after WBS.
* **Every attribution expires at once.** ``MAX_EVIDENCE_AGE_DAYS`` is 30 and all eleven
  records carry the same ``2026-08-11`` observation, so on ``2026-09-10`` the refresh begins
  failing on eleven names rather than one. A hand-built artifact has no cadence, so this is
  a cliff rather than a slope.

An adjudication control whose input is refreshed by remembering to refresh it is a control
with a human in the hot path of every market day. This script removes that.

WHAT IT DOES **NOT** DO. It does not decide anything. It writes down what was observed, and
the classification it records is computed by calling
:func:`factor_adjudication.classify_stale_symbol` — the same function, with the same
operational facts, that the verifier will run again over the same record moments later. The
recorded claim is therefore REDUNDANT rather than authoritative: the verifier's own
re-derivation is what gates the swap, and
``test_generator_claim_never_changes_the_verifier_verdict`` pins that the artifact cannot
talk the gate into anything.

That matters, because "generate the exemptions automatically" is one careless step from
"switch the freshness check off". Four properties keep it honest, and none of them is new
policy — they are the rules :mod:`factor_adjudication` already enforces, now fed observations
instead of recollections:

1. **Only observations are written.** ``requested`` comes from the universe file actually
   handed to the ingest, ``request_status`` from that ingest's exit, and
   ``provider_rows_after_live_frontier`` is COUNTED in the staging store the provider just
   filled. Nothing is asserted that was not measured on this run.
2. **Corroboration is a live probe with a control.** The alternate source is queried for the
   symbol *and* for a control symbol on the same call. A stale control means the alternate
   path was broken when observed, and the shared rule then refuses every attribution that
   depended on it — so an outage of the corroborating source cannot manufacture exemptions.
3. **Attribution stays bounded.** :func:`factor_adjudication.exemption_ceiling` still voids
   the whole run's attribution above 5% of the pool. Automating the writer does not raise the
   ceiling, and a provider outage still looks like — and is treated as — an outage.
4. **A name the rule refuses is written down as refused.** The record is still emitted, with
   ``generator_derived_classification`` naming the refusal, so
   :func:`factor_adjudication.diagnose_unexplained` can tell an operator that this symbol is a
   real finding rather than a missing record. Regeneration will not clear it, and the abort
   message says so.

⚠ **This script never writes to the live store and never promotes anything.** It writes one
JSON artifact, atomically. The swap remains gated by ``scripts/factor_refresh.py verify``,
which re-derives every verdict from scratch.

Usage (inside the one-off refresh container, between ingest and verify)::

    python scripts/factor_evidence.py generate \
        --live /app/data/factor_data.duckdb \
        --stage /app/data/factor_data.staging.duckdb \
        --universe /app/data/_factor_refresh_universe.txt \
        --app-db /app/data/workbench.sqlite \
        --out /app/data/_factor_exhaustion_evidence.json

Exit codes: ``0`` the artifact was written; ``1`` it was not. A non-zero exit must NOT abort
the refresh on its own — the verifier is the gate, and it fails closed on a stale artifact
anyway. See ``deploy/aws/factor-refresh.sh``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

# The shared adjudication implementation, resolved from THIS tree. Same arrangement as
# scripts/factor_refresh.py: one rule, imported rather than restated. A second reading of the
# evidence rules living in the writer is how the writer and the gate come to disagree about
# what the artifact means.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from factor_adjudication import (  # noqa: E402
    ATTRIBUTED,
    FAILED_OR_UNEXPLAINED,
    MAX_EVIDENCE_AGE_DAYS,
    classify_stale_symbol,
    exemption_ceiling,
    operational_facts,
)

#: Schema version of the artifact this writer emits. Bumped from the hand-built documents,
#: which carried none. The readers do not gate on it — they gate on the FIELDS, which are
#: unchanged — but an artifact that cannot say which writer produced it cannot be audited.
SCHEMA_VERSION = 2

#: Default control symbol for the corroboration probe. A liquid, continuously-listed name: if
#: the alternate source cannot price THIS, the alternate source is down, and no attribution
#: taken during that window may be relied upon.
DEFAULT_CONTROL_SYMBOL = "SPY"

#: How far back the alternate-source probe looks for a last trading date. Long enough to span
#: a holiday-shortened week plus the freshness tolerance, short enough that a long-dead name
#: returns nothing rather than a years-old bar.
PROBE_LOOKBACK_DAYS = 21

#: Matches ``DEFAULT_MAX_LAG_DAYS`` in ``scripts/factor_refresh.py`` and
#: ``app/strategies/factor_readiness.py``. A liquid ranked name trades every session.
DEFAULT_MAX_LAG_DAYS = 4


class EvidenceError(RuntimeError):
    """Generation could not be completed. Never raised past :func:`main`."""


# --------------------------------------------------------------------------- store reads


def _duck(path: str | Path):
    import duckdb

    return duckdb.connect(str(path), read_only=True)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def effective_last_by_symbol(store: str | Path, universe: Sequence[str]) -> dict[str, date | None]:
    """Per-symbol effective frontier: ``min(max(sep.date), tickers.lastpricedate)``.

    The EARLIER of the two, deliberately and in agreement with every other component that
    computes this. A name with current prices but a lagging ``lastpricedate`` is dropped from
    the ranking pool outright by ``dollar_volume_universe`` — strictly worse than being ranked
    on old data — so it must not read as fresh here either.
    """
    if not universe:
        return {}
    con = _duck(store)
    try:
        placeholders = ",".join("?" * len(universe))
        sep_rows = con.execute(
            f"SELECT ticker, max(date) FROM sep WHERE ticker IN ({placeholders}) GROUP BY ticker",  # noqa: S608
            list(universe),
        ).fetchall()
        try:
            lpd_rows = con.execute(
                f"SELECT ticker, lastpricedate FROM tickers WHERE ticker IN ({placeholders})",  # noqa: S608
                list(universe),
            ).fetchall()
        except Exception:  # noqa: BLE001 - tickers table absent in a bare fixture store
            lpd_rows = []
    finally:
        con.close()

    sep_max = {t: _as_date(v) for t, v in sep_rows if v is not None}
    lpd_max = {t: _as_date(v) for t, v in lpd_rows if v is not None}
    out: dict[str, date | None] = {}
    for ticker in universe:
        parts = [d for d in (sep_max.get(ticker), lpd_max.get(ticker)) if d is not None]
        out[ticker] = min(parts) if parts else None
    return out


def rows_after(store: str | Path, symbol: str, frontier: date | None) -> int:
    """How many SEP rows the provider delivered for ``symbol`` strictly after ``frontier``.

    This is the measured form of "the provider returned nothing newer". It is counted in the
    STAGING store, which the ingest has just filled from the provider, so a non-zero count
    means the provider did have newer data and something downstream of the request dropped
    it — which the shared rule treats as an ingestion miss, never as exhaustion.

    A ``None`` frontier means the symbol has no live history at all; every staged row is then
    "after" it.
    """
    con = _duck(store)
    try:
        if frontier is None:
            row = con.execute("SELECT count(*) FROM sep WHERE ticker = ?", [symbol]).fetchone()
        else:
            row = con.execute(
                "SELECT count(*) FROM sep WHERE ticker = ? AND date > ?", [symbol, frontier]
            ).fetchone()
    finally:
        con.close()
    return int(row[0] or 0) if row else 0


# ----------------------------------------------------------------- corroboration probe


class CorroborationProbe:
    """An independent source of "is this instrument still trading?".

    Deliberately a tiny interface — one method and a name — because the ONLY thing
    adjudication needs from an alternate source is a last trading date, and a richer seam
    would invite the writer to start forming opinions. Implementations must return ``None``
    for a symbol the source has no recent data for, and must never raise: a probe that
    explodes takes out the generator, and the generator running is what keeps the artifact
    current.
    """

    source = "unset"

    def last_trading_dates(self, symbols: Sequence[str]) -> dict[str, date | None]:
        raise NotImplementedError


class AlpacaBarsProbe(CorroborationProbe):
    """Alternate source = Alpaca daily bars, read over the market-data REST API.

    Alpaca is genuinely independent of Sharadar: different vendor, different entitlement,
    different ingestion path. That independence is the whole value — a name absent from both
    is dead, and a name current at Alpaca but absent from Sharadar is a coverage question
    rather than a lifecycle one, which is exactly the distinction
    :func:`classify_stale_symbol` draws.

    Read-only market data. This makes no trading call, imports no trading SDK, and touches
    neither the order path nor the risk engine.
    """

    source = "alpaca"

    def __init__(self, *, lookback_days: int = PROBE_LOOKBACK_DAYS, timeout_s: float = 20.0):
        self._lookback_days = lookback_days
        self._timeout_s = timeout_s

    def last_trading_dates(self, symbols: Sequence[str]) -> dict[str, date | None]:
        out: dict[str, date | None] = {s: None for s in symbols}
        if not symbols:
            return out
        try:
            import httpx

            from app.brokers.alpaca.credentials import load_credentials
            from app.utils.tls_trust import enable_os_trust_store

            enable_os_trust_store()  # ADR 0017; a no-op on the box
            creds = load_credentials()
            base = os.environ.get("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets").rstrip("/")
            start = (datetime.now(UTC).date() - timedelta(days=self._lookback_days)).isoformat()
            headers = {
                "APCA-API-KEY-ID": creds.api_key,
                "APCA-API-SECRET-KEY": creds.api_secret,
            }
            # Batched, paginated. `sort=desc` is NOT used: we want every symbol's newest bar,
            # and the response is grouped by symbol, so one pass over all pages is simplest
            # and cannot silently truncate a symbol whose bars sort late.
            page_token: str | None = None
            with httpx.Client(timeout=self._timeout_s) as client:
                while True:
                    params: dict[str, Any] = {
                        "symbols": ",".join(sorted(symbols)),
                        "timeframe": "1Day",
                        "start": start,
                        "limit": 10000,
                        "adjustment": "raw",
                    }
                    if page_token:
                        params["page_token"] = page_token
                    resp = client.get(f"{base}/v2/stocks/bars", params=params, headers=headers)
                    resp.raise_for_status()
                    body = resp.json()
                    for symbol, bars in (body.get("bars") or {}).items():
                        for bar in bars or []:
                            stamp = _as_date(bar.get("t"))
                            if stamp is None:
                                continue
                            current = out.get(symbol.upper())
                            if current is None or stamp > current:
                                out[symbol.upper()] = stamp
                    page_token = body.get("next_page_token")
                    if not page_token:
                        break
        except Exception as exc:  # noqa: BLE001 - a dead probe must not kill the generator
            # Returning all-None is the fail-CLOSED outcome, not a fail-open one: with no
            # corroboration the shared rule attributes nothing, including the control, so the
            # artifact this run produces excuses no name at all.
            print(f"corroboration probe FAILED ({type(exc).__name__}: {exc}) - no attributions")
        return out


class StaticProbe(CorroborationProbe):
    """A probe over a caller-supplied mapping. For tests and for offline reruns."""

    def __init__(self, mapping: dict[str, date | None], *, source: str = "static"):
        self._mapping = {k.upper(): v for k, v in mapping.items()}
        self.source = source

    def last_trading_dates(self, symbols: Sequence[str]) -> dict[str, date | None]:
        return {s: self._mapping.get(s.upper()) for s in symbols}


# ------------------------------------------------------------------ document construction


def build_evidence_document(
    *,
    non_fresh: Sequence[str],
    live_effective: dict[str, date | None],
    stage_effective: dict[str, date | None],
    rows_after_frontier: dict[str, int],
    corroborated: dict[str, date | None],
    control_symbol: str,
    control_last_date: date | None,
    corroboration_source: str,
    requested: dict[str, bool],
    request_status: dict[str, str],
    operational: dict[str, dict[str, Any]],
    universe_size: int,
    cutoff: date,
    tolerance_days: int,
    as_of: date,
    observed_at: datetime,
    max_evidence_age_days: int = MAX_EVIDENCE_AGE_DAYS,
) -> dict[str, Any]:
    """Assemble the artifact. PURE: no store, no network, no clock.

    Every argument is an observation the caller made on this run. Nothing is inferred and
    nothing is carried over from a previous artifact — a regenerated document that inherited
    yesterday's corroboration would reintroduce, silently, the exact staleness this script
    exists to end.

    The recorded ``expected_classification`` is produced by calling the shared rule over the
    record being written, with the operational facts recomputed from the app DB. It is a
    convenience for the reader and a filter for :func:`factor_adjudication.load_evidence`; it
    is not trusted by anything, because the verifier re-derives it.
    """
    observed_stamp = observed_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    records: list[dict[str, Any]] = []
    counts = {"attributed": 0, "refused": 0}

    for symbol in sorted({str(s).strip().upper() for s in non_fresh if str(s).strip()}):
        corr_last = corroborated.get(symbol)
        record: dict[str, Any] = {
            "symbol": symbol,
            # Observations. Each of these is a MEASURED fact from this run; see the module
            # docstring for where each one comes from.
            "requested": bool(requested.get(symbol, False)),
            "request_status": request_status.get(symbol, "unknown"),
            "provider_rows_after_live_frontier": int(rows_after_frontier.get(symbol, 0)),
            "live_effective_last": (
                live_effective.get(symbol).isoformat()  # type: ignore[union-attr]
                if live_effective.get(symbol)
                else None
            ),
            "stage_effective_last": (
                stage_effective.get(symbol).isoformat()  # type: ignore[union-attr]
                if stage_effective.get(symbol)
                else None
            ),
            # The instant the corroboration below was observed. classify_stale_symbol judges
            # the frozen dates against the cutoff in force AT THIS MOMENT, and bounds how long
            # they may be relied upon, so this field is load-bearing rather than decorative.
            "adjudicated_at_utc": observed_stamp,
            "corroboration": {
                "source": corroboration_source,
                "last_date": corr_last.isoformat() if corr_last else None,
                "control_symbol": control_symbol,
                "control_last_date": (control_last_date.isoformat() if control_last_date else None),
            },
        }

        facts = operational.get(symbol, {})
        verdict, reason = classify_stale_symbol(
            symbol,
            live_last=live_effective.get(symbol),
            stage_last=stage_effective.get(symbol),
            cutoff=cutoff,
            tolerance_days=tolerance_days,
            as_of=as_of,
            evidence=record,
            held_qty=float(facts.get("held_qty") or 0),
            open_orders=int(facts.get("open_orders") or 0),
            registered_in=facts.get("registered_in") or [],
            max_evidence_age_days=max_evidence_age_days,
        )
        # Recorded under a name that cannot be mistaken for an input. The rule will run again
        # in the verifier; if these two ever disagree, the verifier wins by construction and
        # the disagreement is itself the finding.
        record["generator_derived_classification"] = verdict
        record["generator_derived_reason"] = reason
        record["expected_classification"] = verdict
        if verdict in ATTRIBUTED:
            counts["attributed"] += 1
        else:
            counts["refused"] += 1
        records.append(record)

    ceiling = exemption_ceiling(universe_size)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": "factor_exhaustion_evidence",
        "generated_at_utc": observed_stamp,
        "generator": {
            "implementation": "apps/backend/scripts/factor_evidence.py",
            "mode": "observed",
            "note": (
                "Every field is measured on the run that wrote this file. The recorded "
                "classification is re-derived by scripts/factor_refresh.py verify and is not "
                "trusted here."
            ),
        },
        "as_of": as_of.isoformat(),
        "cutoff": cutoff.isoformat(),
        "tolerance_days": tolerance_days,
        "max_evidence_age_days": max_evidence_age_days,
        "expires_on": (as_of + timedelta(days=max_evidence_age_days)).isoformat(),
        "corroboration_source": corroboration_source,
        "control_symbol": control_symbol,
        "control_last_date": control_last_date.isoformat() if control_last_date else None,
        "universe_size": universe_size,
        "exemption_ceiling": ceiling,
        "counts": {
            "non_fresh": len(records),
            "attributed": counts["attributed"],
            "refused": counts["refused"],
        },
        # A generated artifact that would already blow the ceiling is reported here so the
        # operator sees it in the file rather than only in tomorrow's abort. It is NOT
        # enforced here — adjudicate() voids attribution above the ceiling, and that decision
        # stays in one place.
        "ceiling_exceeded": counts["attributed"] > ceiling,
        "symbols": records,
    }


def write_atomic(path: str | Path, document: dict[str, Any]) -> str:
    """Write the artifact atomically. Returns the sha256 of the bytes written.

    Temp file in the SAME directory, fsynced, then renamed — the arrangement
    ``factor-freshness.sh`` uses for the readiness verdict, for the same reason: a reader
    that catches a half-written document classifies it UNREADABLE, and under the readers'
    fail-closed contract that is a refresh abort and a trading halt. The destination is never
    opened for writing.
    """
    import hashlib

    dest = Path(path)
    payload = json.dumps(document, indent=2, sort_keys=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    with contextlib.suppress(OSError):
        dir_fd = os.open(str(dest.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------ driver


def generate(
    *,
    live_path: str | Path,
    stage_path: str | Path,
    universe: Sequence[str],
    app_db: str | Path | None,
    probe: CorroborationProbe,
    control_symbol: str = DEFAULT_CONTROL_SYMBOL,
    max_lag_days: int = DEFAULT_MAX_LAG_DAYS,
    as_of: date | None = None,
    now: datetime | None = None,
    ingest_status: str = "ok",
    max_evidence_age_days: int = MAX_EVIDENCE_AGE_DAYS,
) -> dict[str, Any]:
    """Observe, then build. Returns the artifact document; writes nothing.

    ``ingest_status`` is the exit condition of the ingest that filled the staging store, and
    is recorded per symbol as ``request_status``. It is a caller-supplied fact rather than
    something inferred here, because this script does not run the ingest and must not pretend
    to know how it went. Anything other than ``"ok"`` makes every record fail closed under the
    shared rule.
    """
    now = now or datetime.now(UTC)
    universe = [str(s).strip().upper() for s in universe if str(s).strip()]
    if not universe:
        raise EvidenceError("refresh universe is empty - nothing to observe")

    stage_effective = effective_last_by_symbol(stage_path, universe)
    frontiers = [d for d in stage_effective.values() if d is not None]
    if not frontiers:
        raise EvidenceError("staging store reports no frontier for any universe name")
    frontier = max(frontiers)
    cutoff = frontier - timedelta(days=max_lag_days)
    as_of = as_of or frontier

    non_fresh = sorted(
        s
        for s in universe
        if stage_effective.get(s) is None or stage_effective[s] < cutoff  # type: ignore[operator]
    )
    live_effective = effective_last_by_symbol(live_path, non_fresh) if non_fresh else {}

    # The control is probed on the SAME call as the subjects, so a source outage cannot
    # produce a current control and stale subjects.
    probe_symbols = sorted({*non_fresh, control_symbol.upper()})
    probed = probe.last_trading_dates(probe_symbols)
    control_last = probed.get(control_symbol.upper())

    operational: dict[str, dict[str, Any]] = {}
    if app_db and Path(app_db).exists():
        # Recomputed, never taken from the previous artifact: a held or registered name must
        # not be writable-off by a file.
        operational = operational_facts(app_db, non_fresh)

    return build_evidence_document(
        non_fresh=non_fresh,
        live_effective=live_effective,
        stage_effective={s: stage_effective.get(s) for s in non_fresh},
        rows_after_frontier={
            s: rows_after(stage_path, s, live_effective.get(s)) for s in non_fresh
        },
        corroborated={s: probed.get(s) for s in non_fresh},
        control_symbol=control_symbol.upper(),
        control_last_date=control_last,
        corroboration_source=probe.source,
        # Membership of the universe file IS the request: it is the exact list handed to
        # ingest_sharadar.py --tickers-file on this run.
        requested=dict.fromkeys(non_fresh, True),
        request_status=dict.fromkeys(non_fresh, ingest_status),
        operational=operational,
        universe_size=len(universe),
        cutoff=cutoff,
        tolerance_days=max_lag_days,
        as_of=as_of,
        observed_at=now,
        max_evidence_age_days=max_evidence_age_days,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)

    g = sub.add_parser("generate", help="observe and write the evidence artifact")
    g.add_argument("--live", required=True, help="the LIVE factor store (frontier reference)")
    g.add_argument("--stage", required=True, help="the STAGING store the ingest just filled")
    g.add_argument("--universe", required=True, help="the refresh universe file")
    g.add_argument("--app-db", default="/app/data/workbench.sqlite")
    g.add_argument("--out", required=True)
    g.add_argument("--control-symbol", default=DEFAULT_CONTROL_SYMBOL)
    g.add_argument("--max-lag-days", type=int, default=DEFAULT_MAX_LAG_DAYS)
    g.add_argument(
        "--ingest-status",
        default="ok",
        help="the exit condition of the ingest that filled --stage. Anything but 'ok' makes "
        "every record fail closed.",
    )
    g.add_argument(
        "--offline",
        action="store_true",
        help="skip the alternate-source probe. Produces an artifact that attributes NOTHING; "
        "for rehearsal only, never for a run whose output gates a swap.",
    )

    args = ap.parse_args(argv)
    try:
        universe = [
            line.strip()
            for line in Path(args.universe).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        probe: CorroborationProbe = (
            StaticProbe({}, source="offline") if args.offline else AlpacaBarsProbe()
        )
        doc = generate(
            live_path=args.live,
            stage_path=args.stage,
            universe=universe,
            app_db=args.app_db,
            probe=probe,
            control_symbol=args.control_symbol,
            max_lag_days=args.max_lag_days,
            ingest_status=args.ingest_status,
        )
        digest = write_atomic(args.out, doc)
        counts = doc["counts"]
        print(
            f"evidence: {counts['non_fresh']} non-fresh, {counts['attributed']} attributable, "
            f"{counts['refused']} refused (ceiling {doc['exemption_ceiling']}), "
            f"control {doc['control_symbol']} last {doc['control_last_date']}"
        )
        print(f"evidence: wrote {args.out} sha256={digest} expires_on={doc['expires_on']}")
        refused = [
            r["symbol"]
            for r in doc["symbols"]
            if r["generator_derived_classification"] == FAILED_OR_UNEXPLAINED
        ]
        if refused:
            # Named here so the refresh log carries the finding even when the operator only
            # reads this step's output. The verifier will abort on these; that is correct.
            print(f"evidence: REFUSED (will fail verification): {refused[:12]}")
        return 0
    except Exception as exc:  # noqa: BLE001 - the caller must not be taken out by this step
        print(f"EVIDENCE_FAILED: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
