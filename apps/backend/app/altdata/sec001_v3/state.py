"""Resumable, deterministic crawl state.

The crawl is long (1,167 permanent identities x 26 years of filings) and it can be stopped
by a 403 at any point. Three properties follow from that, and this module exists to hold
all three in one place:

**Deterministic order.** Work units are sorted by ``(cik, ticker)`` and that order does not
depend on dict iteration, on the order records appeared in the PIT-200 file, or on the
filesystem. Two runs over the same population visit the same identities in the same
sequence, so "resumed at unit 431" means the same thing in both.

**Append-only progress.** Completion is recorded as a JSONL line per finished unit, flushed
before the next unit starts. A crawl killed by ``SIGKILL`` loses at most the unit in flight,
and never rewrites history — the same reason the platform's audit log is append-only.

**Resume is explicit and time-gated.** After a halt, ``can_resume`` is false until the
cooldown has elapsed *and* the caller passes ``resume=True``. There is no automatic resume
and no flag that shortens the cooldown, because the whole point of a 403 halt is that a
human decides whether it is safe to talk to SEC again.

A unit that is recorded complete is never re-fetched. That is what makes resumption cheap,
and it is also why ``mark_done`` is called only after a unit's output has been written.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.evidence import utc_now_iso
from app.altdata.sec001_v3.forbidden import append_jsonl, assert_dataclass_clean, dump_json


@dataclass(frozen=True, order=True)
class WorkUnit:
    """One permanent identity to crawl. ``order=True`` gives the deterministic sort."""

    cik: int
    ticker: str
    permaticker: int | None = None

    @property
    def key(self) -> str:
        return f"{self.cik:010d}:{self.ticker}"


@dataclass(frozen=True)
class UnitResult:
    """What one completed unit produced. Facts only — no coverage quantity."""

    unit_key: str
    cik: int
    ticker: str
    completed_utc: str
    filings_seen: int
    observations: int
    observations_with_sic: int
    missing_sic: int
    segments: int
    conflicts: int
    requests_issued: int
    #: observations whose SEC header could not be completed within the frozen cap. These
    #: are OUR acquisition failures and must never be counted as evidentiary absence.
    acquisition_header_incomplete: int = 0


assert_dataclass_clean(UnitResult)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@dataclass
class CrawlState:
    """On-disk crawl state rooted at ``root``."""

    root: Path
    done: dict[str, UnitResult] = field(default_factory=dict)
    halt: dict[str, object] | None = None

    # -- paths -------------------------------------------------------------------------

    @property
    def progress_path(self) -> Path:
        return self.root / "crawl_progress.jsonl"

    @property
    def halt_path(self) -> Path:
        return self.root / "crawl_halt.json"

    # -- load / save -------------------------------------------------------------------

    @classmethod
    def load(cls, root: Path) -> CrawlState:
        root.mkdir(parents=True, exist_ok=True)
        state = cls(root=root)
        if state.progress_path.exists():
            with state.progress_path.open("rb") as fh:
                for raw in fh:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        # A torn final line is the signature of a hard kill mid-flush.
                        # Everything before it is intact; that unit is simply re-crawled.
                        continue
                    result = UnitResult(**record)
                    state.done[result.unit_key] = result
        if state.halt_path.exists():
            state.halt = json.loads(state.halt_path.read_text(encoding="utf-8"))
        return state

    # -- progress ----------------------------------------------------------------------

    def is_done(self, unit: WorkUnit) -> bool:
        return unit.key in self.done

    def mark_done(self, result: UnitResult) -> None:
        """Record a finished unit. Call only after its output is on disk."""
        append_jsonl(result, self.progress_path)
        self.done[result.unit_key] = result

    def pending(self, units: list[WorkUnit]) -> list[WorkUnit]:
        """Units still to crawl, in deterministic order."""
        return [u for u in sorted(units) if not self.is_done(u)]

    # -- halt / resume -----------------------------------------------------------------

    def record_halt(self, *, status: int, uri: str, completed: int, total: int) -> None:
        now = datetime.now(UTC)
        self.halt = {
            "crawl_id": policy.CRAWL_ID,
            "halted_utc": utc_now_iso(),
            "http_status": status,
            "uri": uri,
            "cooldown_seconds": policy.HALT_COOLDOWN_SECONDS,
            "resume_allowed_after_utc": (
                now + timedelta(seconds=policy.HALT_COOLDOWN_SECONDS)
            ).isoformat().replace("+00:00", "Z"),
            "units_completed": completed,
            "units_total": total,
            "resume_requires": "explicit resume=True after the cooldown; no automatic retry",
        }
        dump_json(self.halt, self.halt_path)

    @property
    def is_halted(self) -> bool:
        return self.halt is not None

    def resume_blocked_reason(self, *, resume: bool, now: datetime | None = None) -> str | None:
        """``None`` if the crawl may proceed; otherwise why it may not.

        Returns a reason rather than a bool so the caller can log *which* condition held.
        """
        if self.halt is None:
            return None
        if not resume:
            return (
                f"crawl is halted (HTTP {self.halt.get('http_status')} at "
                f"{self.halt.get('halted_utc')}); pass resume=True to continue explicitly"
            )
        allowed_after = str(self.halt.get("resume_allowed_after_utc") or "")
        if not allowed_after:
            return "halt record has no resume_allowed_after_utc; refusing to resume"
        current = now or datetime.now(UTC)
        if current < _parse_iso(allowed_after):
            return (
                f"cooldown has not elapsed: resume allowed after {allowed_after}, "
                f"now {current.isoformat()}"
            )
        return None

    def clear_halt(self) -> None:
        """Clear the halt once a resume has been authorised. Keeps the record as evidence."""
        if self.halt_path.exists():
            archived = self.root / f"crawl_halt.resumed.{utc_now_iso().replace(':', '')}.json"
            self.halt_path.replace(archived)
        self.halt = None
