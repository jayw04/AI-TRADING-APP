"""Base-corpus facts: measured from the bound corpus, bound to the countersigned manifest.

Three values were declared as module constants in the delta builders —
``BASE_COVERAGE_THROUGH``, ``BASE_TICKERS_ROWS`` and ``BASE_MAX_LASTPRICEDATE``. They describe the
base corpus, and the base corpus CHANGES when a delta is committed. A declared value that describes a
moving thing is stale the moment the thing moves, and nothing in the pipeline notices: the delta
builds, hashes, and verifies against its own declaration.

⚠ The correction is not merely "measure instead of declare". ``BASE_COVERAGE_THROUGH`` named the
coverage of the base **before any delta**. The lower bound of a NEW delta is the coverage of the
corpus as it now stands — base PLUS every committed delta, which is
:attr:`CorpusManifest.coverage_through`. Those two coincided exactly once, for the first governed
session (2026-07-27), when the manifest carried no prior delta. They diverge for every session after
it: building 2026-07-28 against ``base_coverage_through`` would open the window at 2026-07-24 and
re-ingest three sessions the corpus already holds.

So the bound lower edge is the manifest's ``coverage_through``, cross-checked against what the store
actually contains, and the run refuses on any disagreement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.validation.governed_corpus import CorpusManifest


class BaseFactsError(RuntimeError):
    """The base corpus, its manifest, and the requested session do not agree.

    FAILS CLOSED in every case. Each condition below means the delta about to be built would be bounded
    against something other than the corpus it will be appended to.
    """


@dataclass(frozen=True)
class MeasuredBase:
    """What the bound corpus actually contains, read rather than declared."""
    corpus_path: str
    sep_coverage_through: date
    tickers_rows: int
    tickers_max_lastpricedate: date | None

    def evidence(self) -> dict[str, Any]:
        return {
            "corpus_path": self.corpus_path,
            "measured_sep_coverage_through": self.sep_coverage_through.isoformat(),
            "measured_tickers_rows": self.tickers_rows,
            "measured_tickers_max_lastpricedate": (
                self.tickers_max_lastpricedate.isoformat()
                if self.tickers_max_lastpricedate else None),
        }


def load_corpus_manifest(path: str | Path) -> CorpusManifest:
    """Parse the countersigned corpus manifest through the SAME typed contract the runtime reads.

    Deliberately not a bespoke reader: the build tools and the session path must agree on what the
    manifest says, and the only way to guarantee that is to share the parser rather than the format.
    """
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BaseFactsError(f"the corpus manifest at {p} cannot be read: {exc}") from exc
    return CorpusManifest.from_payload(payload)


def measure_base(corpus_path: str | Path) -> MeasuredBase:
    """Measure the base facts from the bound corpus, read-only."""
    import duckdb

    con = duckdb.connect(str(corpus_path), read_only=True)
    try:
        sep_max = con.execute("SELECT max(date) FROM sep").fetchone()[0]
        tickers_rows = int(con.execute("SELECT count(*) FROM tickers").fetchone()[0])
        tickers_max = con.execute("SELECT max(lastpricedate) FROM tickers").fetchone()[0]
    finally:
        con.close()
    if sep_max is None:
        raise BaseFactsError(f"the corpus at {corpus_path} holds no SEP rows; it cannot bound a delta")
    return MeasuredBase(
        corpus_path=str(corpus_path),
        sep_coverage_through=_as_date(sep_max, "sep.date"),
        tickers_rows=tickers_rows,
        tickers_max_lastpricedate=_as_date(tickers_max, "tickers.lastpricedate") if tickers_max else None,
    )


def _as_date(value: Any, what: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise BaseFactsError(f"{what} is not a date: {value!r}") from exc


def bind_delta_lower_bound(manifest: CorpusManifest, measured: MeasuredBase, *,
                           session: date) -> date:
    """Return the bound lower edge of the delta window, or refuse.

    The returned date is the corpus's CURRENT coverage — base plus every committed delta. The delta
    about to be built covers ``(returned, session]`` and nothing else.
    """
    bound = manifest.coverage_through

    if measured.sep_coverage_through != bound:
        raise BaseFactsError(
            f"the bound corpus carries SEP through {measured.sep_coverage_through.isoformat()} but "
            f"the manifest declares coverage through {bound.isoformat()} "
            f"(base {manifest.base_coverage_through.isoformat()} + {len(manifest.deltas)} delta(s)). "
            f"The store and its manifest describe different corpora; a delta bounded against either "
            f"one would be wrong about the other.")

    if session <= bound:
        raise BaseFactsError(
            f"the requested session {session.isoformat()} is not later than the corpus coverage "
            f"{bound.isoformat()}. A delta at or before existing coverage is a historical correction, "
            f"which requires a new corpus version rather than an append.")

    return bound


def require_delta_window(lower: date, session: date, observed: list[str]) -> None:
    """Refuse unless every observed delta date lies in the half-open window ``(lower, session]``."""
    bad = [d for d in observed if not (lower.isoformat() < d <= session.isoformat())]
    if bad:
        raise BaseFactsError(
            f"the delta carries {len(bad)} date(s) outside the governed window "
            f"({lower.isoformat()}, {session.isoformat()}]: {sorted(set(bad))[:10]}")


def bind_tickers_base(manifest: CorpusManifest, measured: MeasuredBase) -> None:
    """Refuse unless the measured TICKERS census matches the countersigned TICKERS manifest."""
    declared_rows = manifest.tickers.rows
    if measured.tickers_rows != declared_rows:
        raise BaseFactsError(
            f"the bound corpus holds {measured.tickers_rows:,} TICKERS rows but the countersigned "
            f"TICKERS manifest declares {declared_rows:,}; the base census the refresh is judged "
            f"against is not the base actually loaded.")

    declared_cutoff = manifest.tickers.coverage_cutoff
    if measured.tickers_max_lastpricedate != declared_cutoff:
        raise BaseFactsError(
            f"the bound corpus carries max(lastpricedate) "
            f"{measured.tickers_max_lastpricedate.isoformat() if measured.tickers_max_lastpricedate else 'NULL'} "
            f"but the countersigned TICKERS manifest declares coverage cutoff "
            f"{declared_cutoff.isoformat()}.")
