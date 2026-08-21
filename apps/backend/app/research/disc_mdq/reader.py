"""Read-only MDQ corpus reader, constrained by an AuthorizedScope.

Design guarantee: this reader cannot be constructed without a scope, and it
drops non-authorized rows **inside the parse loop**, before they are assembled
into an observation or returned to a caller. There is no code path that
materialises the full corpus and filters afterwards, and no flag that widens the
scope at read time.

It reads **frozen partitions only** (manifest present) and verifies every file
against the manifest before parsing, so a silently mutated corpus fails closed
rather than producing quietly-wrong features.

Since the discovery ledger landed, the same guarantee holds for the *record* of
the read: the reader cannot be constructed without an initialised
:class:`~app.research.disc_mdq.ledger.DiscoveryLedger`, and a ledger cannot be
initialised without a verified :class:`~app.research.disc_mdq.policy.ArtifactAttestation`.
That is plan v0.13 section 4.10.7 items 10-12 — the first exploratory read is
impossible unless ledger initialisation succeeds, the holdout artifact and the
universe pin both verify before a partition is opened, and failure is
fail-closed rather than a warning.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import structlog

from app.research.capture.store import CaptureStore, PartitionRef
from app.research.disc_mdq.ledger import DiscoveryLedger
from app.research.disc_mdq.policy import AuthorizedScope, UnauthorizedReadError
from app.research.disc_mdq.spec import READER_VERSION

logger = structlog.get_logger(__name__)


class MdqReaderError(RuntimeError):
    """Base class for reader failures."""


class PartitionNotFrozenError(MdqReaderError):
    """The partition has no manifest, so it is still being written."""


class PartitionIntegrityError(MdqReaderError):
    """The partition does not match its manifest."""


class UnledgeredReadError(MdqReaderError):
    """A read was attempted without a ledger that covers this exact scope.

    Raised at construction, never at read time, so the failure lands before any
    corpus path is touched.
    """


@dataclass(frozen=True)
class QuoteObservation:
    """One paired-sampler quote snapshot for one symbol on one feed."""

    symbol: str
    feed: str
    session_date: date
    cycle_ts: datetime
    quote_ts: datetime | None
    bid: float | None
    ask: float | None
    bid_size: float | None
    ask_size: float | None
    bid_exchange: str | None = None
    ask_exchange: str | None = None
    conditions: tuple[str, ...] = ()

    @property
    def mid(self) -> float | None:
        """Midpoint, or None when the quote is not two-sided/usable."""
        if self.bid is None or self.ask is None:
            return None
        if self.bid <= 0 or self.ask <= 0 or self.ask < self.bid:
            return None
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float | None:
        """Quoted spread in basis points; None when the midpoint is unusable.

        Matches the §0.4 definition: ``10000 * (ask - bid) / mid``, undefined
        when ``mid <= 0`` or ``bid > ask``.
        """
        mid = self.mid
        if mid is None or mid <= 0:
            return None
        assert self.ask is not None and self.bid is not None
        return 10_000.0 * (self.ask - self.bid) / mid

    @property
    def quote_age_s(self) -> float | None:
        """``cycle_ts - quote_ts`` in seconds — the snapshot's own freshness."""
        if self.quote_ts is None:
            return None
        return (self.cycle_ts - self.quote_ts).total_seconds()


@dataclass(frozen=True)
class PartitionProvenance:
    """Identity of exactly what was read, for the research snapshot."""

    feed: str
    session_date: date
    manifest_sha256: str
    collector_version: str | None
    frozen_at: str | None
    universe_sha256: str | None
    file_sha256: tuple[tuple[str, str], ...]
    integrity_verified: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "feed": self.feed,
            "session_date": self.session_date.isoformat(),
            "manifest_sha256": self.manifest_sha256,
            "collector_version": self.collector_version,
            "frozen_at": self.frozen_at,
            "universe_sha256": self.universe_sha256,
            "files": [{"path": p, "sha256": h} for p, h in self.file_sha256],
            "integrity_verified": self.integrity_verified,
        }


@dataclass(frozen=True)
class ReadResult:
    """Observations plus the provenance needed to reproduce the read."""

    observations: tuple[QuoteObservation, ...]
    provenance: PartitionProvenance
    reader_version: str
    policy_version: str
    purpose: str
    scope_fingerprint: str
    rows_scanned: int
    rows_withheld: int
    #: Discovery-ledger citation for the read that produced these rows. A
    #: condition record names it, which is how "this feature was computed from
    #: that governed partition" stays checkable after the fact.
    ledger_entry_ref: str = ""

    def as_provenance_dict(self) -> dict[str, object]:
        return {
            "reader_version": self.reader_version,
            "policy_version": self.policy_version,
            "purpose": self.purpose,
            "scope_fingerprint": self.scope_fingerprint,
            "rows_scanned": self.rows_scanned,
            "rows_withheld": self.rows_withheld,
            "observations": len(self.observations),
            "partition": self.provenance.as_dict(),
            "ledger_entry_ref": self.ledger_entry_ref,
        }


def _parse_ts(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _as_str(raw: object) -> str | None:
    return raw if isinstance(raw, str) else None


def _as_float(raw: object) -> float | None:
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int | float):
        return float(raw)
    return None


class MdqFeatureReader:
    """Reads frozen MDQ partitions, restricted to a policy-authorized scope."""

    def __init__(
        self,
        store: CaptureStore,
        scope: AuthorizedScope,
        ledger: DiscoveryLedger,
        *,
        verify_integrity: bool = True,
    ) -> None:
        if not isinstance(scope, AuthorizedScope):
            raise TypeError(
                "MdqFeatureReader requires an AuthorizedScope from "
                "MdqExplorationPolicy.authorize(); it has no unrestricted mode"
            )
        if not isinstance(ledger, DiscoveryLedger):
            raise TypeError(
                "MdqFeatureReader requires an initialised DiscoveryLedger from "
                "DiscoveryLedger.open(); exploration that is not recorded is not "
                "sanctioned exploration (plan v0.13 section 4.10.7 item 10)"
            )

        # Item 11, enforced rather than assumed. The ledger's attestation is the
        # verified reading of the two governed artifacts; the scope carries the
        # identity of the quarantine it will actually enforce. If those two
        # disagree, the reader is about to embargo a different set of names from
        # the one the artifacts describe, and that is exactly the failure the
        # holdout exists to prevent.
        attested = ledger.attestation
        if scope.holdout_symbols_sha256 != attested.holdout_symbols_sha256:
            raise UnledgeredReadError(
                "the scope quarantines a different symbol set from the verified "
                f"holdout artifact: scope {scope.holdout_symbols_sha256}, artifact "
                f"{attested.holdout_symbols_sha256}"
            )
        if scope.universe_sha256 is not None and scope.universe_sha256 != attested.universe_sha256:
            raise UnledgeredReadError(
                "the scope was authorized against a different universe file from the "
                f"verified one: scope {scope.universe_sha256}, artifact "
                f"{attested.universe_sha256}"
            )

        self._store = store
        self._scope = scope
        self._ledger = ledger
        self._verify_integrity = verify_integrity

    @property
    def scope(self) -> AuthorizedScope:
        return self._scope

    @property
    def ledger(self) -> DiscoveryLedger:
        return self._ledger

    # --- integrity ----------------------------------------------------------

    def _load_manifest(self, ref: PartitionRef) -> tuple[dict[str, Any], str]:
        mpath = self._store.manifest_path(ref)
        if not mpath.exists():
            raise PartitionNotFrozenError(
                f"partition {ref.feed}/{ref.session} has no manifest; exploration reads "
                "frozen partitions only"
            )
        raw = mpath.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
        return manifest, hashlib.sha256(raw).hexdigest()

    def _provenance(self, ref: PartitionRef) -> PartitionProvenance:
        manifest, manifest_sha = self._load_manifest(ref)

        verified = False
        if self._verify_integrity:
            problems = self._store.verify(ref)
            if problems:
                raise PartitionIntegrityError(
                    f"partition {ref.feed}/{ref.session} failed verification: "
                    + "; ".join(problems)
                )
            verified = True

        files = manifest.get("files", [])
        pairs = tuple(
            (str(f.get("path")), str(f.get("sha256"))) for f in files if isinstance(f, dict)
        )
        return PartitionProvenance(
            feed=ref.feed,
            session_date=ref.session,
            manifest_sha256=manifest_sha,
            collector_version=manifest.get("collector_version"),
            frozen_at=manifest.get("frozen_at"),
            universe_sha256=manifest.get("universe_sha256"),
            file_sha256=pairs,
            integrity_verified=verified,
        )

    # --- reads --------------------------------------------------------------

    def read_quotes(self, feed: str, session_date: date) -> ReadResult:
        """Read the quote snapshots this scope authorizes for one partition.

        Raises UnauthorizedReadError when the scope authorizes no symbol on
        ``session_date`` — including every case where the date itself is
        quarantined. The partition is not opened in that case.
        """
        allowed_symbols = self._scope.symbols_for(session_date)
        if not allowed_symbols:
            raise UnauthorizedReadError(
                f"scope authorizes no symbol on {session_date} — refusing to open the "
                f"{feed} partition. If this is a holdout date, that is the control "
                "working, not a bug."
            )

        ref = PartitionRef(feed=feed, session=session_date)
        provenance = self._provenance(ref)

        path = self._store.partition_dir(ref) / "quotes" / "samples.jsonl"
        if not path.exists():
            raise MdqReaderError(f"no quote file in partition {feed}/{session_date}")

        # Recorded here — after the corpus identity is known and verified, and
        # BEFORE a single row becomes an observation. There is deliberately no
        # ordering in which bytes have been examined and the ledger does not yet
        # say so.
        ledger_entry = self._ledger.record_partition_read(
            feed=feed,
            session_date=session_date,
            scope=self._scope,
            partition=provenance.as_dict(),
        )

        observations: list[QuoteObservation] = []
        scanned = 0
        withheld = 0

        for record in self._iter_jsonl(path):
            scanned += 1
            symbol = record.get("symbol")
            if not isinstance(symbol, str):
                # feed_error rows and malformed lines carry no symbol.
                withheld += 1
                continue
            symbol = symbol.upper()

            # THE quarantine check. A row that is not authorized is dropped
            # here, before it becomes an observation — it never reaches the
            # caller, and it is never counted into any feature.
            if not self._scope.contains(symbol, session_date):
                withheld += 1
                continue

            if record.get("missing") is True:
                withheld += 1
                continue

            cycle_ts = _parse_ts(record.get("cycle_ts"))
            if cycle_ts is None:
                withheld += 1
                continue

            conditions_raw = record.get("conditions")
            conditions: tuple[str, ...] = ()
            if isinstance(conditions_raw, list):
                conditions = tuple(str(c) for c in conditions_raw)

            observations.append(
                QuoteObservation(
                    symbol=symbol,
                    feed=feed,
                    session_date=session_date,
                    cycle_ts=cycle_ts,
                    quote_ts=_parse_ts(record.get("quote_ts")),
                    bid=_as_float(record.get("bid")),
                    ask=_as_float(record.get("ask")),
                    bid_size=_as_float(record.get("bid_size")),
                    ask_size=_as_float(record.get("ask_size")),
                    bid_exchange=_as_str(record.get("bid_exchange")),
                    ask_exchange=_as_str(record.get("ask_exchange")),
                    conditions=conditions,
                )
            )

        # Belt and braces: a bug in the loop above must not be able to leak a
        # quarantined name into a result. This is cheap and it is the one
        # invariant worth asserting twice.
        leaked = {
            o.symbol for o in observations if not self._scope.contains(o.symbol, session_date)
        }
        if leaked:  # pragma: no cover - defensive
            raise UnauthorizedReadError(
                f"reader produced unauthorized symbols {sorted(leaked)}; refusing to "
                "return the result"
            )

        result = ReadResult(
            observations=tuple(observations),
            provenance=provenance,
            reader_version=READER_VERSION,
            policy_version=self._scope.policy_version,
            purpose=self._scope.purpose.value,
            scope_fingerprint=self._scope.fingerprint(),
            rows_scanned=scanned,
            rows_withheld=withheld,
            ledger_entry_ref=ledger_entry.entry_ref,
        )
        logger.info(
            "mdq_quotes_read",
            feed=feed,
            session=session_date.isoformat(),
            authorized_symbols=len(allowed_symbols),
            observations=len(observations),
            rows_scanned=scanned,
            rows_withheld=withheld,
            manifest_sha256=provenance.manifest_sha256,
            integrity_verified=provenance.integrity_verified,
            ledger_entry_ref=ledger_entry.entry_ref,
        )
        return result

    @staticmethod
    def _iter_jsonl(path: Path) -> Iterator[dict[str, object]]:
        """Stream a JSONL file, tolerating the torn final line the collector's
        append-only writer can leave behind (store.append_jsonl documents it)."""
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    yield record
