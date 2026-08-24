"""The SEC-001 V3 classification crawl driver.

Orchestration only. Every rule it applies is declared somewhere else — fair-access policy in
``policy``, retry and halt behaviour in ``fetch``, resumability in ``state``, the emission
ban in ``forbidden``, provenance in ``spine``. The driver's job is to walk the frozen PIT-200
population in deterministic order, hand each identity to the frozen MR-002 spine, and write
what came back.

What it emits, per identity:

``raw/edgar/2026-08-24/observations/<cik>.jsonl``   one row per filing header actually read
``raw/edgar/2026-08-24/source_evidence.jsonl``      one row per HTTP attempt (see evidence.py)
``build/classification/2026-08-24/segments/<cik>.jsonl``  effective-dated SIC segments

What it does not emit, mechanically: any coverage quantity. The crawl is acquisition. The
coverage decision is a separate one-shot artifact that spends ``5b26ffa2…``, and this driver
never touches that token — it does not even read it.

The spine is called through its existing parameters. ``forms=policy.FORMS`` widens the form
set to include 20-F/40-F, and ``since=policy.CRAWL_SINCE`` extends history to 2000-01-01.
Both are registered crawl changes. No MR-002 file is modified.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.evidence import EvidenceLog, utc_now_iso
from app.altdata.sec001_v3.fetch import CrawlExhausted, CrawlHalt, PolicyFetcher
from app.altdata.sec001_v3.forbidden import append_jsonl, dump_json
from app.altdata.sec001_v3.spine import Spine
from app.altdata.sec001_v3.state import CrawlState, UnitResult, WorkUnit


class PopulationSchemaError(RuntimeError):
    """The PIT-200 population file is not in a shape the driver can read."""


class OutputPathError(RuntimeError):
    """An output path fell outside the two permitted prefixes."""


# --- output containment -------------------------------------------------------------


def assert_output_allowed(path: Path, out_root: Path) -> None:
    """Refuse to write outside ``raw/edgar/<date>/`` and ``build/classification/<date>/``.

    Checked on the resolved path, so ``../../sealed`` cannot walk out of the sandbox. The
    governed store lives under ``sealed/`` with a COMPLIANCE lock to 2033; a stray write
    there is not a bug that can be cleaned up afterwards.
    """
    resolved = path.resolve()
    root = out_root.resolve()
    if not resolved.is_relative_to(root):
        raise OutputPathError(f"{resolved} is outside the crawl output root {root}")
    relative = resolved.relative_to(root).as_posix()
    if not any(relative.startswith(p) for p in policy.ALLOWED_OUTPUT_PREFIXES):
        raise OutputPathError(
            f"{relative} is not under a permitted prefix "
            f"{policy.ALLOWED_OUTPUT_PREFIXES}"
        )
    for banned in policy.FORBIDDEN_OUTPUT_PREFIXES:
        if relative.startswith(banned):
            raise OutputPathError(f"{relative} is under the forbidden prefix {banned!r}")


# --- population ---------------------------------------------------------------------


def load_work_units(union_path: Path) -> list[WorkUnit]:
    """Read the frozen PIT-200 union into deterministically ordered work units.

    Deliberately strict. A population file that does not carry an explicit CIK per identity
    is not something to paper over with a guess — the diagnostic names the keys that *were*
    present so the mismatch is fixed once, in the open, rather than silently narrowing the
    crawl.
    """
    payload = json.loads(union_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        for key in ("identities", "permatickers", "union", "rows"):
            if isinstance(payload.get(key), list):
                records = payload[key]
                break
        else:
            raise PopulationSchemaError(
                f"{union_path}: expected a list under one of "
                f"identities/permatickers/union/rows; top-level keys were "
                f"{sorted(payload)}"
            )
    elif isinstance(payload, list):
        records = payload
    else:
        raise PopulationSchemaError(f"{union_path}: expected a list or object, got {type(payload)}")

    units: list[WorkUnit] = []
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            raise PopulationSchemaError(f"{union_path}[{i}]: expected an object, got {type(record)}")
        cik = record.get("cik")
        ticker = record.get("ticker")
        if cik is None or ticker is None:
            raise PopulationSchemaError(
                f"{union_path}[{i}]: needs both 'cik' and 'ticker'; keys present were "
                f"{sorted(record)}. If the union carries only permatickers, resolve CIKs "
                f"through the frozen crosswalk before crawling — do not infer them here."
            )
        units.append(WorkUnit(
            cik=int(cik),
            ticker=str(ticker).strip().upper(),
            permaticker=int(record["permaticker"]) if record.get("permaticker") is not None else None,
        ))

    if not units:
        raise PopulationSchemaError(f"{union_path}: population is empty")
    # Deterministic order, deduplicated on identity.
    return sorted(set(units))


# --- the crawl ------------------------------------------------------------------------


@dataclass
class CrawlOutcome:
    """Facts about how the crawl ran. No coverage quantity appears here."""

    crawl_id: str
    started_utc: str
    finished_utc: str
    units_total: int
    units_completed: int
    units_crawled_this_run: int
    observations_written: int
    segments_written: int
    requests_issued: int
    retries: int
    halted: bool
    halt_detail: str | None = None
    errors: list[str] = field(default_factory=list)


class CrawlDriver:
    """Walks the population once, resumably."""

    def __init__(
        self,
        *,
        spine: Spine,
        out_root: Path,
        fetcher: PolicyFetcher,
        state: CrawlState,
    ) -> None:
        self.spine = spine
        self.out_root = Path(out_root)
        self.fetcher = fetcher
        self.state = state

        self.raw_dir = self.out_root / policy.RAW_PREFIX
        self.build_dir = self.out_root / policy.BUILD_PREFIX
        self.obs_dir = self.raw_dir / "observations"
        self.seg_dir = self.build_dir / "segments"
        self.decision_dir = self.raw_dir / "source_decision_bytes"
        self.decision_manifest = self.raw_dir / "source_decision_bytes.jsonl"
        assert_output_allowed(self.decision_dir, self.out_root)
        assert_output_allowed(self.decision_manifest, self.out_root)
        for d in (self.obs_dir, self.seg_dir, self.decision_dir):
            assert_output_allowed(d, self.out_root)
            d.mkdir(parents=True, exist_ok=True)

    # -- per-unit ----------------------------------------------------------------------

    def _crawl_unit(self, unit: WorkUnit) -> UnitResult:
        sh = self.spine.sic_history
        self.fetcher.context = {"cik": unit.cik, "ticker": unit.ticker}
        before = self.fetcher.requests_issued

        result = sh.collect_sic_observations(
            self.fetcher, unit.cik, unit.ticker,
            since=policy.CRAWL_SINCE, forms=policy.FORMS,
        )
        built = sh.build_segments(result)

        obs_path = self.obs_dir / f"{unit.cik:010d}.jsonl"
        seg_path = self.seg_dir / f"{unit.cik:010d}.jsonl"
        assert_output_allowed(obs_path, self.out_root)
        assert_output_allowed(seg_path, self.out_root)

        # Rewritten wholesale per unit: a unit is only ever crawled once (state.is_done),
        # so there is no partial file to preserve, and a re-crawl after a torn write must
        # not append duplicates behind the earlier attempt.
        obs_path.write_bytes(b"")
        incomplete = 0
        for o in built.observations:
            record = asdict(o)
            # Acquisition provenance travels with every observation so that a machinery
            # failure can never be read as evidentiary absence. A `sic: null` carrying
            # ACQUISITION_HEADER_INCOMPLETE is OUR failure; one carrying HEADER_COMPLETE
            # or HEADER_INDEX is a fact about the filing.
            status = self.fetcher.header_status.get(o.accession, policy.ACQ_HEADER_INDEX)
            record["acquisition_status"] = status
            if status == policy.ACQ_HEADER_INCOMPLETE:
                incomplete += 1

            # Bind the observation to the exact persisted source bytes behind its decision,
            # so a later reader can reproduce the parser result without asking EDGAR again.
            decision = self.fetcher.decisions.get(o.accession)
            if decision is not None:
                decision.parser_result = "SIC" if o.sic else "NO_SIC"
                record["source_decision"] = {
                    "sha256": decision.sha256,
                    "byte_length": decision.byte_length,
                    "artifact_path": decision.artifact_path,
                    "document_complete": decision.document_complete,
                    "sec_header_open_present": decision.sec_header_open_present,
                    "sec_header_close_present": decision.sec_header_close_present,
                    "sic_field_present_anywhere": decision.sic_field_present_anywhere,
                    "sic_field_present_inside_sec_header":
                        decision.sic_field_present_inside_sec_header,
                }
                append_jsonl(asdict(decision), self.decision_manifest)
            append_jsonl(record, obs_path)
        seg_path.write_bytes(b"")
        for s in built.segments:
            append_jsonl(asdict(s), seg_path)

        return UnitResult(
            unit_key=unit.key,
            cik=unit.cik,
            ticker=unit.ticker,
            completed_utc=utc_now_iso(),
            filings_seen=len(built.observations),
            observations=len(built.observations),
            observations_with_sic=sum(1 for o in built.observations if o.sic is not None),
            missing_sic=built.missing_sic,
            segments=len(built.segments),
            conflicts=len(built.conflicts),
            requests_issued=self.fetcher.requests_issued - before,
            acquisition_header_incomplete=incomplete,
        )

    # -- the run -----------------------------------------------------------------------

    def run(self, units: list[WorkUnit], *, resume: bool = False, limit: int | None = None) -> CrawlOutcome:
        blocked = self.state.resume_blocked_reason(resume=resume)
        if blocked:
            recorded = self.state.halt.get("http_status") if self.state.halt else None
            raise CrawlHalt(
                recorded if isinstance(recorded, int) else 403,
                f"resume refused: {blocked}",
            )
        if self.state.is_halted:
            self.state.clear_halt()

        started = utc_now_iso()
        pending = self.state.pending(units)
        if limit is not None:
            pending = pending[:limit]

        crawled = 0
        observations = 0
        segments = 0
        errors: list[str] = []
        halted = False
        halt_detail: str | None = None

        try:
            for unit in pending:
                result = self._crawl_unit(unit)
                self.state.mark_done(result)
                crawled += 1
                observations += result.observations
                segments += result.segments
        except CrawlHalt as halt:
            # BaseException: not caught by the spine's fail-soft handlers, and not
            # swallowed here either — recorded, then re-raised to the operator.
            halted = True
            halt_detail = str(halt)
            self.state.record_halt(
                status=halt.status, uri=halt.uri,
                completed=len(self.state.done), total=len(units),
            )
            self._write_outcome(self._outcome(
                started, len(units), crawled, observations, segments, errors, True, halt_detail,
            ))
            raise
        except CrawlExhausted as exc:
            errors.append(str(exc))

        outcome = self._outcome(
            started, len(units), crawled, observations, segments, errors, halted, halt_detail,
        )
        self._write_outcome(outcome)
        return outcome

    def _outcome(
        self, started: str, total: int, crawled: int, observations: int,
        segments: int, errors: list[str], halted: bool, halt_detail: str | None,
    ) -> CrawlOutcome:
        return CrawlOutcome(
            crawl_id=policy.CRAWL_ID,
            started_utc=started,
            finished_utc=utc_now_iso(),
            units_total=total,
            units_completed=len(self.state.done),
            units_crawled_this_run=crawled,
            observations_written=observations,
            segments_written=segments,
            requests_issued=self.fetcher.requests_issued,
            retries=self.fetcher.retries,
            halted=halted,
            halt_detail=halt_detail,
            errors=errors,
        )

    def _write_outcome(self, outcome: CrawlOutcome) -> None:
        path = self.build_dir / "crawl_outcome.json"
        assert_output_allowed(path, self.out_root)
        dump_json(outcome, path)


def open_evidence_log(out_root: Path) -> EvidenceLog:
    path = Path(out_root) / policy.RAW_PREFIX / "source_evidence.jsonl"
    assert_output_allowed(path, Path(out_root))
    return EvidenceLog(path=path)
