"""Governed corpora as an immutable base plus ordered, countersigned deltas (ADR 0048).

A forward-validation session must evaluate against data whose coverage reaches that session, and must
record immutably which data it used. Those two requirements pull against each other under a
whole-file countersignature: coverage has to advance daily, but the countersigned identity may not
drift. ADR 0048 resolves it by fixing an immutable base and extending it with append-only, ordered,
individually hashed deltas.

## Two identities, and why neither substitutes for the other

  * ``corpus_manifest_sha256`` — computed here — is the identity of the AUTHORIZED CONSTRUCTION: base
    identity, every ordered delta, the governing universe, and ACTIONS provenance. It proves *which
    governed construction the deployment was permitted to assemble*.

  * ``store_identity_sha256`` — computed in :mod:`app.validation.data_finality`, NOT here — is a
    streaming value-level digest of the rows a session actually consumed, re-verified after the reads
    by ``verify_store_unchanged``. It proves *the consumed dataset did not move during execution*.

They fail differently. A deployment that assembles the authorized construction and then reads against
a store mutating underneath it satisfies the first and violates the second; a deployment reading a
stable but unauthorized store does the reverse. Collapsing them leaves one of those two failures
undetectable, so this module computes the construction identity and **deliberately does not touch the
value-level digest, its timing, or its calculation**.

## Corrections are not deltas

A delta may only extend coverage forward. A "delta" landing on or before the base cutoff is refused
here rather than applied, because that is a historical amendment, and ADR 0048 (4) routes those to a
separately documented repair producing a new corpus version. The cost asymmetry is the design:
extending is cheap, amending is expensive and visible.

## Contiguity has two shapes

A session corpus is contiguous against the governed trading calendar — the caller supplies the
expected sessions, because the authoritative calendar lives in :mod:`app.validation.eval_calendar`
and this module stays free of that dependency so the contract is testable without it. A rate series
is contiguous against its own coverage: each extension resumes exactly where the previous one
stopped. Both are exact-match rules; neither tolerates a gap, a repeat, or a reordering.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.validation.forward_window import IntegrityStop
from app.validation.security_lineage import SECURITY_IDENTITY_CONTRACT

_HEX = frozenset("0123456789abcdef")

#: The governing universe the base corpus is bound to. A universe change is a new base, never a delta.
GOVERNED_UNIVERSE_SIZE = 14_150


class CorpusConstructionError(IntegrityStop):
    """The governed construction could not be established. Fails closed — no session runs."""


class DeltaChainError(CorpusConstructionError):
    """The delta chain is missing, duplicated, out of order, future-dated, unhashed, or bound to a
    different universe."""


class HistoricalAmendmentRefused(CorpusConstructionError):
    """A delta would have modified coverage at or before the base cutoff. Historical corrections
    require a new corpus version and its own countersignature (ADR 0048 (4)), never a delta."""


class FrozenArtifactDrift(CorpusConstructionError):
    """An artifact frozen by the countersigned preregistration does not hash to its pinned value."""


class ManifestIdentityConflict(CorpusConstructionError):
    """A declared identity and the identity computed from the artifacts disagree, or a required
    identity is absent."""


class Contiguity(StrEnum):
    """How a chain proves it has no holes."""
    SESSION_CALENDAR = "SESSION_CALENDAR"        # exact match against the governed trading sessions
    COVERAGE_CONTIGUOUS = "COVERAGE_CONTIGUOUS"  # each extension resumes where the previous stopped


def canonical_json(payload: Any) -> bytes:
    """Deterministic serialization. Sorted keys, no insignificant whitespace, dates as ISO strings.

    Every identity in this module is a digest over this encoding, so two deployments that assembled
    the same construction produce the same identity byte-for-byte.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str).encode("utf-8")


def _is_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and set(text) <= _HEX


def _require_sha256(value: Any, *, what: str) -> str:
    text = str(value or "").strip().lower()
    if not _is_sha256(text):
        raise DeltaChainError(f"{what} is not a sha256 digest ({value!r}); an unhashed artifact "
                              f"cannot enter a governed construction")
    return text


def file_sha256(path: Path, *, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes, streamed."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True)
class GovernedDelta:
    """One append-only extension. Session-bounded, hashed, and bound to the governing universe.

    ``coverage_through`` is recorded separately from ``session_date`` because they answer different
    questions: the session this delta belongs to, and the last date whose rows it carries. A delta
    whose coverage runs past its own session is future-dated and refused.
    """
    session_date: date
    coverage_through: date
    sha256: str                     # the delta artifact itself
    source_sha256: str              # the upstream source artifact it was ingested from
    rows: int
    retrieved_at: str               # ISO-8601 UTC, when the source was pulled
    countersignature: str           # reference to the countersigned delta manifest record
    # Bound to the base's governing universe. A rate series has no universe, so this is None there
    # rather than a placeholder digest that would look like a real binding in the identity payload.
    universe_sha256: str | None = None
    exclusions: tuple[str, ...] = ()

    def identity_payload(self) -> dict[str, Any]:
        return {
            "session_date": self.session_date.isoformat(),
            "coverage_through": self.coverage_through.isoformat(),
            "sha256": self.sha256,
            "source_sha256": self.source_sha256,
            "universe_sha256": self.universe_sha256,
            "rows": self.rows,
            "retrieved_at": self.retrieved_at,
            "countersignature": self.countersignature,
            "exclusions": list(self.exclusions),
        }

    @staticmethod
    def from_payload(payload: Any, *, index: int, require_universe: bool = True) -> GovernedDelta:
        if not isinstance(payload, dict):
            raise DeltaChainError(f"delta {index} is not an object")
        try:
            session_date = date.fromisoformat(str(payload["session_date"]))
            coverage_through = date.fromisoformat(str(payload["coverage_through"]))
        except (KeyError, ValueError) as exc:
            raise DeltaChainError(f"delta {index} has no valid session_date/coverage_through: "
                                  f"{exc}") from exc
        rows = payload.get("rows")
        if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
            raise DeltaChainError(f"delta {index} ({session_date}) records rows={rows!r}; a governed "
                                  f"delta must record a non-negative integer row count")
        retrieved_at = str(payload.get("retrieved_at", "")).strip()
        if not retrieved_at:
            raise DeltaChainError(f"delta {index} ({session_date}) records no retrieval timestamp")
        countersignature = str(payload.get("countersignature", "")).strip()
        if not countersignature:
            raise DeltaChainError(
                f"delta {index} ({session_date}) carries no countersignature reference; an "
                f"unattested delta cannot enter a governed construction")
        exclusions = payload.get("exclusions", [])
        if not isinstance(exclusions, list):
            raise DeltaChainError(f"delta {index} ({session_date}) records exclusions as "
                                  f"{type(exclusions).__name__}, not a list")
        return GovernedDelta(
            session_date=session_date,
            coverage_through=coverage_through,
            sha256=_require_sha256(payload.get("sha256"), what=f"delta {index} ({session_date})"),
            source_sha256=_require_sha256(payload.get("source_sha256"),
                                          what=f"delta {index} ({session_date}) source"),
            universe_sha256=(_require_sha256(payload.get("universe_sha256"),
                                             what=f"delta {index} ({session_date}) universe")
                             if require_universe else None),
            rows=rows,
            retrieved_at=retrieved_at,
            countersignature=countersignature,
            exclusions=tuple(str(x) for x in exclusions),
        )


def validate_delta_chain(
    *,
    base_coverage_through: date,
    base_universe_sha256: str | None,
    deltas: tuple[GovernedDelta, ...],
    observation_session: date,
    contiguity: Contiguity,
    expected_sessions: tuple[date, ...] | None = None,
) -> None:
    """Refuse a chain that is missing, duplicated, out of order, future-dated, unhashed, amending
    history, or bound to a different universe. Returns None; raises on any violation.

    ``expected_sessions`` is required for :attr:`Contiguity.SESSION_CALENDAR` and must be the ordered
    governed sessions strictly after ``base_coverage_through`` through ``observation_session``. It is
    supplied by the caller so that the authoritative calendar stays in one module.
    """
    previous_coverage = base_coverage_through
    seen: set[date] = set()

    for index, delta in enumerate(deltas):
        # history is never rewritten through this path
        if delta.session_date <= base_coverage_through:
            raise HistoricalAmendmentRefused(
                f"delta {index} is dated {delta.session_date}, at or before the base cutoff "
                f"{base_coverage_through}; that is a historical correction, which requires a new "
                f"corpus version and its own countersignature, not a delta")
        # no duplicates, no reordering — a strictly increasing sequence excludes both
        if delta.session_date in seen:
            raise DeltaChainError(
                f"delta {index} repeats session {delta.session_date}; a session is recorded once")
        if index > 0 and delta.session_date <= deltas[index - 1].session_date:
            raise DeltaChainError(
                f"delta {index} ({delta.session_date}) does not follow delta {index - 1} "
                f"({deltas[index - 1].session_date}); the chain must be strictly increasing")
        seen.add(delta.session_date)
        # nothing may reach past the session being observed
        if delta.session_date > observation_session:
            raise DeltaChainError(
                f"delta {index} is dated {delta.session_date}, after the observed session "
                f"{observation_session}; a session may not consume future data")
        if delta.coverage_through > delta.session_date:
            raise DeltaChainError(
                f"delta {index} ({delta.session_date}) carries coverage through "
                f"{delta.coverage_through}, past its own session; the delta is future-dated")
        # the universe is the base's universe, exactly (rate series carry no universe: None skips)
        if base_universe_sha256 is not None and delta.universe_sha256 != base_universe_sha256:
            raise DeltaChainError(
                f"delta {index} ({delta.session_date}) is bound to universe "
                f"{str(delta.universe_sha256)[:16]}… but the base is bound to "
                f"{base_universe_sha256[:16]}…; a universe change is a new base, not a delta")

        if contiguity is Contiguity.COVERAGE_CONTIGUOUS:
            if delta.coverage_through <= previous_coverage:
                raise DeltaChainError(
                    f"delta {index} ends at {delta.coverage_through}, at or before the previous "
                    f"coverage {previous_coverage}; extensions must advance coverage")
            previous_coverage = delta.coverage_through

    if contiguity is Contiguity.SESSION_CALENDAR:
        if expected_sessions is None:
            raise DeltaChainError(
                "session-calendar contiguity was requested without the governed session list; the "
                "chain cannot be proven gap-free against a calendar that was not supplied")
        actual = tuple(d.session_date for d in deltas)
        if actual != tuple(expected_sessions):
            missing = sorted(set(expected_sessions) - set(actual))
            extra = sorted(set(actual) - set(expected_sessions))
            detail = []
            if missing:
                detail.append(f"missing {[d.isoformat() for d in missing]}")
            if extra:
                detail.append(f"unexpected {[d.isoformat() for d in extra]}")
            if not detail:
                detail.append("same sessions in a different order")
            raise DeltaChainError(
                f"the delta chain does not match the governed sessions through "
                f"{observation_session}: {'; '.join(detail)}")


@dataclass(frozen=True)
class CorpusManifest:
    """The authorized construction of the governing SEP/ACTIONS/TICKERS corpus for one observation.

    TICKERS joined the bound construction on 2026-07-29, by owner ruling. It is not reference trivia:
    `universe_asof` cannot resolve an eligible universe without current effective security metadata,
    so two materially different constructions — one with a stale TICKERS that yields an EMPTY universe,
    one with a current TICKERS that yields 500 names — would otherwise share the same authorized
    identity. `security_identity_contract` is bound for the same reason one step further out: it pins
    the RULE by which those rows are interpreted, so a later resolver change cannot silently
    reinterpret identical artifacts.
    """
    base_corpus_sha256: str
    base_coverage_through: date
    governed_universe_sha256: str
    governed_universe_size: int
    actions_manifest_sha256: str
    actions_authoritative: bool
    # Embedded rather than referenced by digest: a separate file would have to be declared somewhere
    # and then checked against, which is one more place for a manifest to name an artifact it did not
    # actually assemble. Embedding makes `tickers_manifest_sha256` a COMPUTED identity, exactly like
    # `corpus_manifest_sha256`, so there is no declared-vs-actual gap to police.
    tickers: TickersManifest
    tickers_authoritative: bool
    security_identity_contract: str
    deltas: tuple[GovernedDelta, ...]
    base_countersignature: str

    @property
    def tickers_manifest_sha256(self) -> str:
        return self.tickers.tickers_manifest_sha256

    def identity_payload(self) -> dict[str, Any]:
        return {
            "kind": "governed_corpus",
            "base_corpus_sha256": self.base_corpus_sha256,
            "base_coverage_through": self.base_coverage_through.isoformat(),
            "base_countersignature": self.base_countersignature,
            "governed_universe_sha256": self.governed_universe_sha256,
            "governed_universe_size": self.governed_universe_size,
            "actions_manifest_sha256": self.actions_manifest_sha256,
            "actions_authoritative": self.actions_authoritative,
            "tickers": self.tickers.identity_payload(),
            "tickers_manifest_sha256": self.tickers_manifest_sha256,
            "tickers_authoritative": self.tickers_authoritative,
            "security_identity_contract": self.security_identity_contract,
            "deltas": [d.identity_payload() for d in self.deltas],
        }

    @property
    def corpus_manifest_sha256(self) -> str:
        """The construction identity. Deterministic over base, ordered deltas, universe and ACTIONS
        provenance — ADR 0048 (6)."""
        return hashlib.sha256(canonical_json(self.identity_payload())).hexdigest()

    @property
    def ordered_delta_manifest_sha256s(self) -> tuple[str, ...]:
        return tuple(d.sha256 for d in self.deltas)

    @property
    def coverage_through(self) -> date:
        return self.deltas[-1].coverage_through if self.deltas else self.base_coverage_through

    def validate(self, *, observation_session: date,
                 expected_sessions: tuple[date, ...]) -> None:
        if not self.actions_authoritative:
            raise CorpusConstructionError(
                "the corpus manifest declares its ACTIONS dataset non-authoritative; a governed "
                "session cannot evaluate corporate actions from a store that never ingested them")
        if not self.tickers_authoritative:
            raise CorpusConstructionError(
                "the corpus manifest declares its TICKERS dataset non-authoritative; the registered "
                "universe is resolved from effective security metadata, so a session cannot rank "
                "securities it cannot identify")
        if self.security_identity_contract != SECURITY_IDENTITY_CONTRACT:
            raise CorpusConstructionError(
                f"the corpus manifest names security identity contract "
                f"{self.security_identity_contract!r} but this deployment implements "
                f"{SECURITY_IDENTITY_CONTRACT!r}; the rule by which securities are identified is part "
                f"of the authorized construction and is never assumed to match")
        self.tickers.validate()
        if self.tickers.coverage_cutoff < observation_session:
            raise CorpusConstructionError(
                f"the governed TICKERS construction is cut off at {self.tickers.coverage_cutoff} but "
                f"the session being observed is {observation_session}; effective security metadata "
                f"that stops before the session cannot establish which securities were tradeable "
                f"during it")
        if self.governed_universe_size != GOVERNED_UNIVERSE_SIZE:
            raise CorpusConstructionError(
                f"the corpus manifest declares a universe of {self.governed_universe_size}, not the "
                f"governing {GOVERNED_UNIVERSE_SIZE}; a universe change is a new base")
        validate_delta_chain(
            base_coverage_through=self.base_coverage_through,
            base_universe_sha256=self.governed_universe_sha256,
            deltas=self.deltas,
            observation_session=observation_session,
            contiguity=Contiguity.SESSION_CALENDAR,
            expected_sessions=expected_sessions,
        )

    def to_manifest_json(self) -> dict[str, Any]:
        """The on-disk form, round-tripping exactly through `from_payload`. Shared with the generator
        so there is one definition of the construction, not a producer's and a consumer's."""
        return {
            "base_corpus_sha256": self.base_corpus_sha256,
            "base_coverage_through": self.base_coverage_through.isoformat(),
            "governed_universe_sha256": self.governed_universe_sha256,
            "governed_universe_size": self.governed_universe_size,
            "actions_manifest_sha256": self.actions_manifest_sha256,
            "actions_authoritative": self.actions_authoritative,
            "tickers": self.tickers.to_manifest_json(),
            "tickers_authoritative": self.tickers_authoritative,
            "security_identity_contract": self.security_identity_contract,
            "base_countersignature": self.base_countersignature,
            "deltas": [
                {"session_date": d.session_date.isoformat(),
                 "coverage_through": d.coverage_through.isoformat(),
                 "sha256": d.sha256, "source_sha256": d.source_sha256,
                 "universe_sha256": d.universe_sha256, "rows": d.rows,
                 "retrieved_at": d.retrieved_at, "countersignature": d.countersignature,
                 "exclusions": list(d.exclusions)}
                for d in self.deltas],
        }

    @staticmethod
    def from_payload(payload: Any) -> CorpusManifest:
        if not isinstance(payload, dict):
            raise CorpusConstructionError("the corpus manifest is not an object")
        try:
            base_coverage = date.fromisoformat(str(payload["base_coverage_through"]))
        except (KeyError, ValueError) as exc:
            raise CorpusConstructionError(
                f"the corpus manifest records no valid base_coverage_through: {exc}") from exc
        raw_deltas = payload.get("deltas", [])
        if not isinstance(raw_deltas, list):
            raise CorpusConstructionError(
                f"the corpus manifest records deltas as {type(raw_deltas).__name__}, not a list")
        authoritative = payload.get("actions_authoritative")
        if authoritative is not True and authoritative is not False:
            raise CorpusConstructionError(
                f"the corpus manifest records actions_authoritative as {authoritative!r}; it must be "
                f"the JSON boolean true or false, not a value that merely reads as one")
        tickers_authoritative = payload.get("tickers_authoritative")
        if tickers_authoritative is not True and tickers_authoritative is not False:
            raise CorpusConstructionError(
                f"the corpus manifest records tickers_authoritative as {tickers_authoritative!r}; it "
                f"must be the JSON boolean true or false, not a value that merely reads as one")
        contract = str(payload.get("security_identity_contract", "")).strip()
        if not contract:
            raise CorpusConstructionError(
                "the corpus manifest names no security_identity_contract; the rule by which tickers "
                "are resolved to permanent securities is part of the authorized construction")
        size = payload.get("governed_universe_size")
        if not isinstance(size, int) or isinstance(size, bool):
            raise CorpusConstructionError(
                f"the corpus manifest records governed_universe_size as {size!r}")
        countersignature = str(payload.get("base_countersignature", "")).strip()
        if not countersignature:
            raise CorpusConstructionError(
                "the corpus manifest carries no base countersignature reference")
        return CorpusManifest(
            base_corpus_sha256=_require_sha256(payload.get("base_corpus_sha256"),
                                               what="the base corpus identity"),
            base_coverage_through=base_coverage,
            governed_universe_sha256=_require_sha256(payload.get("governed_universe_sha256"),
                                                     what="the governed universe identity"),
            governed_universe_size=size,
            actions_manifest_sha256=_require_sha256(payload.get("actions_manifest_sha256"),
                                                    what="the ACTIONS manifest identity"),
            actions_authoritative=authoritative,
            tickers=TickersManifest.from_payload(payload.get("tickers")),
            tickers_authoritative=tickers_authoritative,
            security_identity_contract=contract,
            deltas=tuple(GovernedDelta.from_payload(d, index=i) for i, d in enumerate(raw_deltas)),
            base_countersignature=countersignature,
        )


@dataclass(frozen=True)
class Dgs3moManifest:
    """The authorized construction of the risk-free series: frozen base plus ordered extensions.

    The frozen base identity is ``forward_window.DGS3MO_SNAPSHOT_SHA256`` and stays that value. It is
    never redefined as the digest of a combined file — that would convert a frozen pin into a moving
    target and destroy the property it exists to hold (ADR 0048 (11)).
    """
    base_sha256: str
    base_coverage_through: date
    extensions: tuple[GovernedDelta, ...]

    def identity_payload(self) -> dict[str, Any]:
        return {
            "kind": "dgs3mo",
            "base_sha256": self.base_sha256,
            "base_coverage_through": self.base_coverage_through.isoformat(),
            "extensions": [e.identity_payload() for e in self.extensions],
        }

    @property
    def dgs3mo_manifest_sha256(self) -> str:
        """Base plus ordered extensions — ADR 0048 (11). Distinct from the frozen base pin."""
        return hashlib.sha256(canonical_json(self.identity_payload())).hexdigest()

    @property
    def coverage_through(self) -> date:
        return self.extensions[-1].coverage_through if self.extensions else self.base_coverage_through

    def validate(self, *, observation_session: date, frozen_base_sha256: str) -> None:
        if self.base_sha256 != frozen_base_sha256:
            raise FrozenArtifactDrift(
                f"the DGS3MO manifest names base {self.base_sha256[:16]}… but the countersigned "
                f"preregistration pins {frozen_base_sha256[:16]}…; the frozen base is installed by "
                f"exact hash and never regenerated")
        validate_delta_chain(
            base_coverage_through=self.base_coverage_through,
            base_universe_sha256=None,          # a rate series is not universe-bound
            deltas=self.extensions,
            observation_session=observation_session,
            contiguity=Contiguity.COVERAGE_CONTIGUOUS,
        )

    @staticmethod
    def from_payload(payload: Any) -> Dgs3moManifest:
        if not isinstance(payload, dict):
            raise CorpusConstructionError("the DGS3MO manifest is not an object")
        try:
            base_coverage = date.fromisoformat(str(payload["base_coverage_through"]))
        except (KeyError, ValueError) as exc:
            raise CorpusConstructionError(
                f"the DGS3MO manifest records no valid base_coverage_through: {exc}") from exc
        raw = payload.get("extensions", [])
        if not isinstance(raw, list):
            raise CorpusConstructionError(
                f"the DGS3MO manifest records extensions as {type(raw).__name__}, not a list")
        return Dgs3moManifest(
            base_sha256=_require_sha256(payload.get("base_sha256"),
                                        what="the DGS3MO base identity"),
            base_coverage_through=base_coverage,
            extensions=tuple(GovernedDelta.from_payload(e, index=i, require_universe=False)
                             for i, e in enumerate(raw)),
        )


#: The governed TICKERS schema. Bumped when the selected vendor columns change, because a column set
#: is part of what the construction IS: dropping `permaticker` turns identity resolution off, and a
#: manifest that did not name its columns could not tell that from an unchanged one.
TICKERS_SCHEMA_VERSION = "TICKERS_V2_PERMATICKER"

#: The identity-bearing columns. `row_identity_sha256` digests exactly these, so a change to a
#: security's permanent id, symbol or effective interval moves the manifest identity, while a churn-y
#: descriptive field (sector reclassification, company-site URL) does not.
TICKERS_IDENTITY_COLUMNS = ("permaticker", "ticker", "firstpricedate", "lastpricedate")


def tickers_row_identity(rows: Any) -> str:
    """Digest the identity-bearing projection of the TICKERS rows.

    Sorted by permanent id then symbol so the identity is independent of row order — two deployments
    that assembled the same securities produce the same digest whatever order the vendor returned.
    """
    projected = sorted([str(r[c] if isinstance(r, dict) else r[i]) for i, c
                        in enumerate(TICKERS_IDENTITY_COLUMNS)] for r in rows)
    return hashlib.sha256(canonical_json(projected)).hexdigest()


@dataclass(frozen=True)
class TickersManifest:
    """The authorized construction of the governed TICKERS dataset (owner ruling, 2026-07-29).

    Bound by ADR 0048 as amended because `universe_asof` cannot resolve an eligible universe without
    it: a stale TICKERS yields an EMPTY universe and a current one yields 500 names, and those two
    constructions must not be able to share an authorized identity.
    """
    schema_version: str
    columns: tuple[str, ...]
    rows: int
    permanent_ids: int
    row_identity_sha256: str
    coverage_cutoff: date
    artifact_sha256: str
    source_identity: str
    countersignature: str

    def identity_payload(self) -> dict[str, Any]:
        return {
            "kind": "tickers_manifest",
            "schema_version": self.schema_version,
            "columns": list(self.columns),
            "rows": self.rows,
            "permanent_ids": self.permanent_ids,
            "row_identity_sha256": self.row_identity_sha256,
            "coverage_cutoff": self.coverage_cutoff.isoformat(),
            "artifact_sha256": self.artifact_sha256,
            "source_identity": self.source_identity,
            "countersignature": self.countersignature,
        }

    @property
    def tickers_manifest_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.identity_payload())).hexdigest()

    def validate(self) -> None:
        if self.schema_version != TICKERS_SCHEMA_VERSION:
            raise CorpusConstructionError(
                f"the TICKERS manifest declares schema {self.schema_version!r} but this deployment "
                f"implements {TICKERS_SCHEMA_VERSION!r}")
        missing = [c for c in TICKERS_IDENTITY_COLUMNS if c not in self.columns]
        if missing:
            raise CorpusConstructionError(
                f"the TICKERS manifest omits identity-bearing column(s) {missing}; without them a "
                f"security cannot be resolved to a permanent lineage")
        if self.rows <= 0 or self.permanent_ids <= 0:
            raise CorpusConstructionError(
                f"the TICKERS manifest records {self.rows} row(s) and {self.permanent_ids} permanent "
                f"id(s); an empty security master evidences no universe at all")
        if self.permanent_ids != self.rows:
            raise CorpusConstructionError(
                f"the TICKERS manifest records {self.rows} rows but only {self.permanent_ids} distinct "
                f"permanent ids; a symbol mapping to several lineages is ambiguous by construction")

    def to_manifest_json(self) -> dict[str, Any]:
        """The on-disk form, round-tripping exactly through `from_payload`.

        Generation and verification share this so a producer cannot drift from the consumer: any
        generator that writes the block by hand would be a second, unreviewed definition of what a
        TICKERS construction IS.
        """
        return {
            "schema_version": self.schema_version,
            "columns": list(self.columns),
            "rows": self.rows,
            "permanent_ids": self.permanent_ids,
            "row_identity_sha256": self.row_identity_sha256,
            "coverage_cutoff": self.coverage_cutoff.isoformat(),
            "artifact_sha256": self.artifact_sha256,
            "source_identity": self.source_identity,
            "countersignature": self.countersignature,
        }

    @staticmethod
    def from_payload(payload: Any) -> TickersManifest:
        if not isinstance(payload, dict):
            raise CorpusConstructionError("the TICKERS manifest is not an object")
        try:
            cutoff = date.fromisoformat(str(payload["coverage_cutoff"]))
        except (KeyError, ValueError) as exc:
            raise CorpusConstructionError(
                f"the TICKERS manifest records no valid coverage_cutoff: {exc}") from exc
        cols = payload.get("columns", [])
        if not isinstance(cols, list) or not cols:
            raise CorpusConstructionError(
                "the TICKERS manifest records no selected vendor columns")
        for key in ("rows", "permanent_ids"):
            if not isinstance(payload.get(key), int) or isinstance(payload.get(key), bool):
                raise CorpusConstructionError(
                    f"the TICKERS manifest records {key} as {payload.get(key)!r}")
        countersignature = str(payload.get("countersignature", "")).strip()
        if not countersignature:
            raise CorpusConstructionError("the TICKERS manifest carries no countersignature reference")
        return TickersManifest(
            schema_version=str(payload.get("schema_version", "")).strip(),
            columns=tuple(str(c) for c in cols),
            rows=int(payload["rows"]),
            permanent_ids=int(payload["permanent_ids"]),
            row_identity_sha256=_require_sha256(payload.get("row_identity_sha256"),
                                                what="the TICKERS row identity"),
            coverage_cutoff=cutoff,
            artifact_sha256=_require_sha256(payload.get("artifact_sha256"),
                                            what="the TICKERS artifact identity"),
            source_identity=str(payload.get("source_identity", "")).strip(),
            countersignature=countersignature,
        )


def _load_manifest_json(path: Path, *, what: str) -> dict:
    if not path.is_file():
        raise CorpusConstructionError(f"{what} is absent at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusConstructionError(f"{what} at {path} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise CorpusConstructionError(f"{what} at {path} is not an object")
    return payload


def load_corpus_manifest(path: Path) -> CorpusManifest:
    return CorpusManifest.from_payload(_load_manifest_json(path, what="the corpus manifest"))


def load_dgs3mo_manifest(path: Path) -> Dgs3moManifest:
    return Dgs3moManifest.from_payload(_load_manifest_json(path, what="the DGS3MO manifest"))


@dataclass(frozen=True)
class GovernedConstruction:
    """The validated construction one observation is authorized to use."""
    corpus: CorpusManifest
    dgs3mo: Dgs3moManifest
    corpus_manifest_sha256: str
    dgs3mo_manifest_sha256: str

    def to_open_provenance(self) -> dict[str, Any]:
        return {
            "base_corpus_sha256": self.corpus.base_corpus_sha256,
            "base_coverage_through": self.corpus.base_coverage_through.isoformat(),
            "ordered_delta_manifest_sha256s": list(self.corpus.ordered_delta_manifest_sha256s),
            "governed_universe_sha256": self.corpus.governed_universe_sha256,
            "governed_universe_size": self.corpus.governed_universe_size,
            "actions_manifest_sha256": self.corpus.actions_manifest_sha256,
            "tickers_manifest_sha256": self.corpus.tickers_manifest_sha256,
            "security_identity_contract": self.corpus.security_identity_contract,
            "corpus_manifest_sha256": self.corpus_manifest_sha256,
            "corpus_coverage_through": self.corpus.coverage_through.isoformat(),
            "dgs3mo_base_sha256": self.dgs3mo.base_sha256,
            "dgs3mo_manifest_sha256": self.dgs3mo_manifest_sha256,
            "dgs3mo_coverage_through": self.dgs3mo.coverage_through.isoformat(),
        }


def resolve_governed_construction(
    *,
    corpus_manifest_path: Path,
    dgs3mo_manifest_path: Path,
    dgs3mo_path: Path,
    trial_ledger_path: Path,
    frozen_dgs3mo_sha256: str,
    frozen_trial_ledger_sha256: str,
    deployment_manifest_corpus_block: Any,
    observation_session: date,
    expected_sessions: tuple[date, ...],
) -> GovernedConstruction:
    """Establish, fail-closed, which governed construction this session is authorized to consume.

    Order matters and is deliberate: the frozen artifacts are verified by exact hash BEFORE any
    manifest is trusted, because a manifest that names a drifted artifact would otherwise be validated
    against itself. Then the chains are validated, then the deployment manifest is required to agree
    with what was actually assembled.

    This function performs no data reads and never computes a value-level store identity; that stays
    with :mod:`app.validation.data_finality`, unchanged.
    """
    verify_frozen_artifact(Path(dgs3mo_path), pinned_sha256=frozen_dgs3mo_sha256,
                           what="the frozen DGS3MO base")
    verify_frozen_artifact(Path(trial_ledger_path), pinned_sha256=frozen_trial_ledger_sha256,
                           what="the governed trial ledger")

    corpus = load_corpus_manifest(Path(corpus_manifest_path))
    dgs3mo = load_dgs3mo_manifest(Path(dgs3mo_manifest_path))

    corpus.validate(observation_session=observation_session, expected_sessions=expected_sessions)
    dgs3mo.validate(observation_session=observation_session,
                    frozen_base_sha256=frozen_dgs3mo_sha256)

    if corpus.coverage_through < observation_session:
        raise CorpusConstructionError(
            f"the governed corpus reaches {corpus.coverage_through} but the session being observed is "
            f"{observation_session}; a session cannot be evaluated against data that stops before it")
    if dgs3mo.coverage_through < observation_session:
        raise CorpusConstructionError(
            f"the DGS3MO construction reaches {dgs3mo.coverage_through} but the session being observed "
            f"is {observation_session}; the risk-free series does not cover the session")

    require_declared_identities(deployment_manifest_corpus_block, computed={
        "base_corpus_sha256": corpus.base_corpus_sha256,
        "ordered_delta_manifest_sha256s": corpus.ordered_delta_manifest_sha256s,
        "governed_universe_sha256": corpus.governed_universe_sha256,
        "actions_manifest_sha256": corpus.actions_manifest_sha256,
        "tickers_manifest_sha256": corpus.tickers_manifest_sha256,
        "corpus_manifest_sha256": corpus.corpus_manifest_sha256,
    })
    declared_dgs3mo = deployment_manifest_corpus_block.get("dgs3mo_manifest_sha256")
    if declared_dgs3mo is None:
        raise ManifestIdentityConflict(
            "the deployment manifest declares no dgs3mo_manifest_sha256; the risk-free construction "
            "is part of what the deployment was authorized to assemble")
    if str(declared_dgs3mo).lower() != dgs3mo.dgs3mo_manifest_sha256:
        raise ManifestIdentityConflict(
            f"the deployment manifest declares dgs3mo_manifest_sha256 {str(declared_dgs3mo)[:16]}… "
            f"but the assembled construction is {dgs3mo.dgs3mo_manifest_sha256[:16]}…")

    return GovernedConstruction(
        corpus=corpus, dgs3mo=dgs3mo,
        corpus_manifest_sha256=corpus.corpus_manifest_sha256,
        dgs3mo_manifest_sha256=dgs3mo.dgs3mo_manifest_sha256,
    )


def verify_frozen_artifact(path: Path, *, pinned_sha256: str, what: str) -> str:
    """Install-by-exact-hash. Refuses drift rather than accepting an equivalent-looking file.

    A regenerated, normalized, reordered or reserialized copy is NOT equivalent: the preregistration
    froze these artifacts by digest, and a different digest is a different artifact regardless of how
    similar its contents look (ADR 0048 (12)).
    """
    if not path.is_file():
        raise FrozenArtifactDrift(f"{what} is absent at {path}; it is installed, never regenerated")
    actual = file_sha256(path)
    if actual != str(pinned_sha256).strip().lower():
        raise FrozenArtifactDrift(
            f"{what} at {path} hashes to {actual[:16]}… but the countersigned preregistration pins "
            f"{str(pinned_sha256)[:16]}…; a generated replacement, an empty file, a normalized CSV, a "
            f"reordered JSON or a reserialized copy is not equivalent unless its byte hash is exact")
    return actual


#: The construction identities a deployment manifest must carry — ADR 0048 (8).
#:
#: ``store_identity_sha256`` is the sixth identity ADR 0048 (8) enumerates, and it is deliberately
#: NOT in this tuple. A deployment manifest is finalized before observation #1; a store identity does
#: not exist until a session performs its reads. Requiring it here would force the generator to invent
#: one, which is precisely the "faithful attestation to hand-made evidence" the deployment-identity
#: module exists to prevent. It is instead required in OBSERVATION evidence, where it is real — see
#: :func:`require_observation_identities`. A manifest MAY still declare it (a per-session manifest
#: legitimately can), and when it does, it is verified against the session's actual value rather than
#: trusted.
REQUIRED_MANIFEST_IDENTITIES = (
    "base_corpus_sha256",
    "ordered_delta_manifest_sha256s",
    "governed_universe_sha256",
    "actions_manifest_sha256",
    "tickers_manifest_sha256",
    "corpus_manifest_sha256",
)

#: Both identities are mandatory in every observation, and neither substitutes for the other.
REQUIRED_OBSERVATION_IDENTITIES = ("corpus_manifest_sha256", "store_identity_sha256")

_IDENTITY_TOKEN = object()


class IdentitySource(StrEnum):
    """Where an identity was derived from. Carried with the value so independence is a property of
    the object rather than a claim about it."""
    GOVERNED_CONSTRUCTION_MANIFEST = "GOVERNED_CONSTRUCTION_MANIFEST"
    STREAMED_CONSUMED_ROWS = "STREAMED_CONSUMED_ROWS"


@dataclass(frozen=True)
class BoundIdentity:
    """A digest that knows how it was produced.

    Independence between the two observation identities is enforced STRUCTURALLY, by construction,
    not by comparing their values. Two SHA-256 strings being unequal proves nothing about where they
    came from: a defect that hashed two different wrappers around the same underlying declaration
    would produce unequal digests and sail through a value comparison. What must be true is that one
    is recomputed from the canonical governed construction and the other comes only from the streamed
    value-level row digest — so that is what is checked.
    """
    value: str
    source: IdentitySource

    def __post_init__(self) -> None:
        if getattr(self, "_token", None) is not _IDENTITY_TOKEN:
            raise ManifestIdentityConflict(
                "a BoundIdentity may only be produced by construction_identity() or "
                "consumed_rows_identity(); a hand-built one carries no provenance")


def _issue(value: str, source: IdentitySource) -> BoundIdentity:
    identity = BoundIdentity.__new__(BoundIdentity)
    object.__setattr__(identity, "_token", _IDENTITY_TOKEN)
    object.__setattr__(identity, "value", value)
    object.__setattr__(identity, "source", source)
    return identity


def construction_identity(manifest: CorpusManifest) -> BoundIdentity:
    """RECOMPUTED from the canonical governed construction manifest. It cannot be sourced from the
    store because nothing about the store is an input to it."""
    if not isinstance(manifest, CorpusManifest):
        raise ManifestIdentityConflict(
            f"the construction identity must be recomputed from a CorpusManifest, not from "
            f"{type(manifest).__name__}")
    return _issue(manifest.corpus_manifest_sha256, IdentitySource.GOVERNED_CONSTRUCTION_MANIFEST)


def consumed_rows_identity(finality: Any) -> BoundIdentity:
    """Taken ONLY from the existing streamed value-level row digest, off the finality evidence that
    computed it. Handing this the construction manifest is a type error, not a value that happens to
    look wrong."""
    from app.validation.data_finality import DataFinalityEvidence

    if not isinstance(finality, DataFinalityEvidence):
        raise ManifestIdentityConflict(
            f"the value-level store identity must come from DataFinalityEvidence, not from "
            f"{type(finality).__name__}; it is a property of what the session READ")
    return _issue(finality.store_identity_sha256, IdentitySource.STREAMED_CONSUMED_ROWS)


def require_declared_identities(declared: Any, *, computed: dict[str, Any]) -> dict[str, Any]:
    """Reject a deployment manifest whose corpus identities are missing or conflict with the
    identities computed from the artifacts actually installed."""
    if not isinstance(declared, dict):
        raise ManifestIdentityConflict(
            "the deployment manifest carries no corpus identity block; a session cannot record which "
            "governed construction it was authorized to use")
    # An EMPTY delta list is a legitimate construction, not a missing field: observation #1 runs on a
    # base whose coverage already reaches the session, with no deltas yet. Treating [] as absent would
    # refuse the first observation the program ever takes.
    missing = [k for k in REQUIRED_MANIFEST_IDENTITIES if declared.get(k) in (None, "")]
    if missing:
        raise ManifestIdentityConflict(
            f"the deployment manifest's corpus identity block is incomplete; missing {sorted(missing)}")

    for key in ("base_corpus_sha256", "governed_universe_sha256", "actions_manifest_sha256",
                "tickers_manifest_sha256", "corpus_manifest_sha256"):
        if not _is_sha256(declared.get(key)):
            raise ManifestIdentityConflict(
                f"the deployment manifest declares {key}={declared.get(key)!r}, which is not a "
                f"sha256 digest")
    ordered = declared.get("ordered_delta_manifest_sha256s")
    if not isinstance(ordered, list) or not all(_is_sha256(x) for x in ordered):
        raise ManifestIdentityConflict(
            "the deployment manifest declares ordered_delta_manifest_sha256s that is not a list of "
            "sha256 digests")

    conflicts = []
    for key, value in computed.items():
        if key not in declared:
            raise ManifestIdentityConflict(
                f"the deployment manifest declares no {key}, so the construction it authorized "
                f"cannot be compared with the one assembled")
        want = list(value) if isinstance(value, tuple) else value
        got = declared[key]
        if isinstance(want, str) and isinstance(got, str):
            want, got = want.lower(), got.lower()
        if want != got:
            conflicts.append(f"{key}: manifest={got!r} assembled={want!r}")
    if conflicts:
        raise ManifestIdentityConflict(
            "the deployment manifest and the assembled construction disagree — "
            + "; ".join(sorted(conflicts)))
    return dict(declared)


def require_observation_identities(evidence: Any, *, construction: BoundIdentity,
                                   consumed: BoundIdentity) -> dict[str, Any]:
    """Require BOTH identities in an observation, each matching the value its own source produced.

    They are not aliases and neither substitutes for the other (ADR 0048 (7)): the first proves which
    construction was authorized, the second proves the consumed rows did not move during execution.

    Independence is enforced by PROVENANCE, not by value. Requiring the two digests to differ would
    be the wrong proof twice over — unequal values do not establish separate derivation, and a defect
    hashing two different wrappers around one declaration would pass such a check. So each argument
    must be a `BoundIdentity` carrying the correct source, which only its own factory can issue.

    Equality of the two digests is astronomically unlikely and is RECORDED as an audit condition. It
    is not a refusal: with provenance enforced, equal values would be a coincidence rather than a
    substitution, and refusing on it would stop a governed session for the wrong reason.
    """
    if not isinstance(construction, BoundIdentity) or \
            construction.source is not IdentitySource.GOVERNED_CONSTRUCTION_MANIFEST:
        raise ManifestIdentityConflict(
            "the construction identity was not recomputed from the governed construction manifest")
    if not isinstance(consumed, BoundIdentity) or \
            consumed.source is not IdentitySource.STREAMED_CONSUMED_ROWS:
        raise ManifestIdentityConflict(
            "the value-level store identity did not come from the streamed consumed-row digest")

    if not isinstance(evidence, dict):
        raise ManifestIdentityConflict("the observation carries no identity block")
    missing = [k for k in REQUIRED_OBSERVATION_IDENTITIES if evidence.get(k) in (None, "")]
    if missing:
        raise ManifestIdentityConflict(
            f"the observation is missing {sorted(missing)}; both the construction identity and the "
            f"value-level store identity are mandatory in every observation")
    if evidence["corpus_manifest_sha256"] != construction.value:
        raise ManifestIdentityConflict(
            f"the observation declares corpus_manifest_sha256 "
            f"{str(evidence['corpus_manifest_sha256'])[:16]}… but the session assembled "
            f"{construction.value[:16]}…")
    if evidence["store_identity_sha256"] != consumed.value:
        raise ManifestIdentityConflict(
            f"the observation declares store_identity_sha256 "
            f"{str(evidence['store_identity_sha256'])[:16]}… but the session read "
            f"{consumed.value[:16]}…")

    out: dict[str, Any] = {k: str(evidence[k]) for k in REQUIRED_OBSERVATION_IDENTITIES}
    out["identity_sources"] = {"corpus_manifest_sha256": str(construction.source),
                               "store_identity_sha256": str(consumed.source)}
    if construction.value == consumed.value:
        # Recorded, never refused. Provenance already proves they were derived separately.
        out["audit_condition"] = "IDENTITIES_COINCIDENTALLY_EQUAL"
    return out
