"""The ONE derivation of the governed price-history quarantine (owner ruling 2026-07-31).

## Why this module exists

`corpus_manifest_v2.json` carries a countersigned `governed_quarantine` block naming the permanent
identities whose price history the Layer 2 vintage withholds. Nothing in `app/validation` read it.
The production session path therefore had no notion of a quarantine at all, and the Phase C readiness
runner carried its own literal instead::

    QUARANTINED_IDENTITIES = frozenset({"167284", "642054"})

The two agreed. They agreed BY COINCIDENCE — a constant in a script happened to match a block in a
countersigned artifact, and nothing checked that it still did. A parity test written against that
arrangement would have passed while proving nothing, which is the same defect Amendment 2 removed from
the session runner ("there is no EXPECTED_COUNTS and no fallback") wearing different clothes.

So there is one derivation, it is manifest-driven, and both consumers call it. A parity test over two
independent calls of ONE derivation from ONE countersigned source has content; a parity test over two
literals does not.

## What is derived from where — and what is never derived

Everything the policy asserts comes from bytes that the countersignature transitively binds:

  * permanent identities, descriptive tickers, the anomaly class and the governing wording —
    the manifest's own `governed_quarantine` block;
  * the governed movement dates — the `shop_tln_quarantine` evidence artifact, which the manifest
    pins by sha256 and which is re-hashed here before a single field is read;
  * the governed factor types — CLASSIFIED from the ratios the same artifact preserved verbatim,
    using the `FactorKind` semantics the verifier itself uses. They are NOT re-measured from the
    store: a policy that read the store would be describing the data it is supposed to govern.

⚠ The identity↔ticker pairing is the one thing the governed artifacts do not state directly: the
manifest lists `names` and `permanent_identities` as parallel sequences and the evidence artifact keys
its records by ticker. The pairing is therefore taken from the manifest's declared order and then
PROVED at the point it matters — a measured movement carries both its ticker and its permanent
identity, resolved from the store, and readiness refuses unless the pair matches the policy. A wrong
pairing cannot pass; it can only refuse.

## What the policy is not

It confers nothing. It does not mark a movement explained, reconciled, or price-adjustment-verified,
and it never says the quarantined names are decision-irrelevant — the manifest states in as many words
that they are decision-relevant in the raw construction. What it does is delimit, in advance and under
countersignature, exactly which unexplained movements a session may DISCLOSE rather than refuse. One
movement outside that delimitation is a refusal.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.validation.adjustment_verifier import FactorKind
from app.validation.forward_window import IntegrityStop
from app.validation.governed_corpus import (
    CorpusConstructionError,
    Layer2Countersignature,
    NormalizedCorpusConstruction,
    canonical_json,
    read_pinned_artifact,
)

#: The logical name, in the manifest's `artifacts` block, of the evidence this policy reads.
QUARANTINE_EVIDENCE_ARTIFACT = "shop_tln_quarantine"

POLICY_SCHEMA_VERSION = "GOVERNED_QUARANTINE_POLICY_v1.0"


class GovernedQuarantineError(IntegrityStop):
    """The governed quarantine could not be derived from the countersigned construction.

    FAILS CLOSED. There is no fallback and no default policy: a session that cannot establish which
    movements are governed cannot tell a disclosed limitation from an undetected data defect.
    """


@dataclass(frozen=True)
class QuarantinedMovement:
    """One factor movement the countersigned construction governs.

    Keyed on the PERMANENT identity. `ticker` is descriptive metadata carried so the evidence reads
    for a human and so the identity↔ticker pairing is checkable against the measurement; it is never
    the key, because a ticker is reused across issuers and the quarantine is about a lineage.
    """
    permanent_identity: str
    ticker: str
    session_date: date
    factor: FactorKind

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.permanent_identity, self.session_date.isoformat(), str(self.factor))

    def to_open_provenance(self) -> dict[str, Any]:
        return {"permanent_identity": self.permanent_identity, "ticker": self.ticker,
                "session_date": self.session_date.isoformat(), "factor": str(self.factor)}


@dataclass(frozen=True)
class GovernedQuarantinePolicy:
    """The immutable quarantine policy both readiness and session composition consume.

    ⚠ `policy_sha256` is over the canonical serialization of everything below, so two derivations
    agree on the digest only if they agree on every field. It is the single value a parity check can
    compare, and the single value a consumer can be bound to.
    """
    permanent_identities: frozenset[str]
    descriptive_tickers: dict[str, str]              # permanent identity -> ticker
    anomaly_class: str
    quarantine_kind: str
    permanent_universe_removal: bool
    movements: tuple[QuarantinedMovement, ...]
    quarantine_evidence_sha256: str
    corpus_manifest_sha256: str
    countersignature_sidecar_sha256: str
    #: The manifest's own wording, carried rather than paraphrased. `must_not_say` is the statement
    #: the record is forbidden to make about these names, and it is kept beside the claim so a reader
    #: of the evidence sees the prohibition next to what it prohibits.
    statement: tuple[str, ...]
    must_not_say: str
    policy_sha256: str

    @property
    def movement_keys(self) -> frozenset[tuple[str, str, str]]:
        return frozenset(m.key for m in self.movements)

    @property
    def governed_movement_dates(self) -> tuple[str, ...]:
        return tuple(sorted({m.session_date.isoformat() for m in self.movements}))

    @property
    def governed_factor_types(self) -> tuple[str, ...]:
        return tuple(sorted({str(m.factor) for m in self.movements}))

    def covers(self, permanent_identity: Any, session_date: Any, factor: Any) -> bool:
        """Whether ONE measured movement is governed — identity, date AND factor, all three.

        Identity alone is not enough: a governed quarantine that admitted any movement on a
        quarantined name would tolerate a split appearing on a lineage the countersignature examined
        only for a dividend-factor anomaly.
        """
        return (str(permanent_identity), str(session_date), str(factor)) in self.movement_keys

    def to_open_provenance(self) -> dict[str, Any]:
        return _policy_payload(
            permanent_identities=self.permanent_identities,
            descriptive_tickers=self.descriptive_tickers,
            anomaly_class=self.anomaly_class,
            quarantine_kind=self.quarantine_kind,
            permanent_universe_removal=self.permanent_universe_removal,
            movements=self.movements,
            quarantine_evidence_sha256=self.quarantine_evidence_sha256,
            corpus_manifest_sha256=self.corpus_manifest_sha256,
            countersignature_sidecar_sha256=self.countersignature_sidecar_sha256,
            statement=self.statement,
            must_not_say=self.must_not_say,
        ) | {"policy_sha256": self.policy_sha256}


def _policy_payload(**fields: Any) -> dict[str, Any]:
    """The canonical policy body — the bytes `policy_sha256` is taken over.

    ⚠ `policy_sha256` is deliberately NOT part of it. A digest cannot cover itself, and a payload that
    carried a placeholder would make the digest depend on the placeholder.
    """
    movements: tuple[QuarantinedMovement, ...] = fields["movements"]
    return {
        "kind": "governed_quarantine_policy",
        "policy_schema_version": POLICY_SCHEMA_VERSION,
        "anomaly_class": fields["anomaly_class"],
        "quarantine_kind": fields["quarantine_kind"],
        "permanent_universe_removal": bool(fields["permanent_universe_removal"]),
        "permanent_identities": sorted(fields["permanent_identities"]),
        "descriptive_tickers": dict(sorted(fields["descriptive_tickers"].items())),
        "governed_movements": [m.to_open_provenance()
                               for m in sorted(movements, key=lambda m: m.key)],
        "governed_movement_dates": sorted({m.session_date.isoformat() for m in movements}),
        "governed_factor_types": sorted({str(m.factor) for m in movements}),
        "quarantine_evidence_sha256": fields["quarantine_evidence_sha256"],
        "corpus_manifest_sha256": fields["corpus_manifest_sha256"],
        "countersignature_sidecar_sha256": fields["countersignature_sidecar_sha256"],
        "statement": list(fields["statement"]),
        "must_not_say": fields["must_not_say"],
    }


def governed_quarantine_policy(
    normalized: NormalizedCorpusConstruction,
    countersignature: Layer2Countersignature | None,
    *,
    governed_root: Path,
) -> GovernedQuarantinePolicy:
    """Derive the quarantine policy from the countersigned construction. The ONE derivation.

    ⚠ Both sides call this: the Phase C readiness runner and production session composition. A second
    derivation — or a literal on either side — is how the two come to disagree without anything
    noticing, which is exactly what happened to `QUARANTINED_IDENTITIES`.

    `governed_root` is the directory the construction's evidence artifacts were installed into. The
    FILENAME is not supplied by the caller: it comes from the manifest's own `artifacts` block, and the
    file is re-hashed against the digest the manifest pins before anything in it is read. A caller can
    therefore point this at a governed directory, but not at a file of its choosing.
    """
    if countersignature is None:
        raise GovernedQuarantineError(
            "the governed quarantine was requested without a countersignature; the identities and "
            "movements a session may disclose are exactly what governance approved, and an "
            "uncountersigned construction approves nothing")
    if countersignature.corpus_manifest_sha256 != normalized.corpus_manifest_sha256:
        raise GovernedQuarantineError(
            f"the countersignature binds corpus manifest "
            f"{countersignature.corpus_manifest_sha256[:16]}… but the quarantine is being derived "
            f"from {normalized.corpus_manifest_sha256[:16]}…; a quarantine approved for one "
            f"construction governs no other")

    declaration = normalized.governed_quarantine
    if declaration is None:
        raise GovernedQuarantineError(
            "the governed construction declares no governed_quarantine block, so no movement is "
            "authorized to be disclosed rather than refused")

    try:
        raw, evidence_sha = read_pinned_artifact(
            normalized, QUARANTINE_EVIDENCE_ARTIFACT, governed_root=Path(governed_root))
    except CorpusConstructionError as exc:
        raise GovernedQuarantineError(
            f"the governed quarantine evidence could not be established: {exc}") from exc
    payload = _decode(raw)
    movements = _movements(payload, declaration)

    body = _policy_payload(
        permanent_identities=declaration.permanent_identities,
        descriptive_tickers=declaration.descriptive_tickers,
        anomaly_class=declaration.anomaly_class,
        quarantine_kind=declaration.quarantine_kind,
        permanent_universe_removal=declaration.permanent_universe_removal,
        movements=movements,
        quarantine_evidence_sha256=evidence_sha,
        corpus_manifest_sha256=normalized.corpus_manifest_sha256,
        countersignature_sidecar_sha256=countersignature.countersignature_sha256,
        statement=declaration.statement,
        must_not_say=declaration.must_not_say,
    )
    return GovernedQuarantinePolicy(
        permanent_identities=declaration.permanent_identities,
        descriptive_tickers=dict(declaration.descriptive_tickers),
        anomaly_class=declaration.anomaly_class,
        quarantine_kind=declaration.quarantine_kind,
        permanent_universe_removal=declaration.permanent_universe_removal,
        movements=movements,
        quarantine_evidence_sha256=evidence_sha,
        corpus_manifest_sha256=normalized.corpus_manifest_sha256,
        countersignature_sidecar_sha256=countersignature.countersignature_sha256,
        statement=declaration.statement,
        must_not_say=declaration.must_not_say,
        policy_sha256=hashlib.sha256(canonical_json(body)).hexdigest())


def _decode(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GovernedQuarantineError(
            f"the governed quarantine evidence is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise GovernedQuarantineError("the governed quarantine evidence is not an object")
    return payload


def _movements(payload: dict[str, Any], declaration: Any) -> tuple[QuarantinedMovement, ...]:
    """The governed movements: one per (identity, anomalous session), with the factor CLASSIFIED.

    The evidence artifact states the anomalous sessions per ticker and preserves the source rows
    verbatim, each carrying the two factor ratios. The factor kind is read off those preserved ratios
    with the same rule the verifier applies — a leg that did not move is recorded as exactly 1.0, and
    anything else is a movement on that leg.
    """
    quarantined = payload.get("quarantined")
    if not isinstance(quarantined, dict) or not quarantined:
        raise GovernedQuarantineError(
            "the governed quarantine evidence names no quarantined sessions; a quarantine that "
            "covers no movement authorizes no disclosure")
    records = payload.get("anomaly_records")
    if not isinstance(records, dict):
        raise GovernedQuarantineError(
            "the governed quarantine evidence carries no anomaly_records, so the factor each "
            "governed movement sits on cannot be established")

    declared = set(declaration.descriptive_tickers.values())
    if set(quarantined) != declared:
        raise GovernedQuarantineError(
            f"the corpus manifest declares the quarantine over {sorted(declared)} but the evidence "
            f"artifact covers {sorted(quarantined)}; the block and the artifact it pins describe "
            f"different quarantines")

    by_ticker = {ticker: identity for identity, ticker in declaration.descriptive_tickers.items()}
    out: list[QuarantinedMovement] = []
    for ticker in sorted(quarantined):
        sessions = quarantined[ticker]
        if not isinstance(sessions, list) or not sessions:
            raise GovernedQuarantineError(
                f"the governed quarantine evidence records no anomalous session for {ticker}")
        rows = _preserved_rows(records, ticker)
        for raw in sessions:
            try:
                when = date.fromisoformat(str(raw))
            except ValueError as exc:
                raise GovernedQuarantineError(
                    f"the governed quarantine evidence records {raw!r} as an anomalous session for "
                    f"{ticker}, which is not a date") from exc
            out.append(QuarantinedMovement(
                permanent_identity=by_ticker[ticker], ticker=ticker, session_date=when,
                factor=_factor_of(rows, ticker=ticker, when=when)))
    return tuple(sorted(out, key=lambda m: m.key))


def _preserved_rows(records: dict[str, Any], ticker: str) -> dict[str, dict[str, Any]]:
    record = records.get(ticker)
    if not isinstance(record, dict):
        raise GovernedQuarantineError(
            f"the governed quarantine evidence carries no anomaly record for {ticker}")
    rows = record.get("rows_preserved_verbatim")
    if not isinstance(rows, list) or not rows:
        raise GovernedQuarantineError(
            f"the anomaly record for {ticker} preserves no source rows, so the factor its movements "
            f"sit on cannot be read")
    return {str(r.get("date")): r for r in rows if isinstance(r, dict)}


def _factor_of(rows: dict[str, dict[str, Any]], *, ticker: str, when: date) -> FactorKind:
    """Classify ONE preserved row onto a governed factor.

    ⚠ Exact comparison against 1.0 is deliberate and is not a tolerance decision. The preserved rows
    record an unmoved leg as exactly 1.0, so "not 1.0" is the artifact's own statement that the leg
    moved. Using a band here would let the policy disagree with the verifier about which leg an
    anomaly sits on — and the two disagreeing is a refusal, never a reconciliation.
    """
    row = rows.get(when.isoformat())
    if row is None:
        raise GovernedQuarantineError(
            f"the governed quarantine evidence names {when.isoformat()} as anomalous for {ticker} "
            f"but preserves no source row for that session")
    dividend = _ratio(row.get("dividend_factor_ratio"), ticker=ticker, when=when,
                      leg="dividend_factor_ratio")
    split = _ratio(row.get("split_factor_ratio"), ticker=ticker, when=when, leg="split_factor_ratio")
    div_moved = dividend != 1.0
    split_moved = split != 1.0
    if div_moved and split_moved:
        return FactorKind.COMBINED
    if div_moved:
        return FactorKind.DIVIDEND
    if split_moved:
        return FactorKind.SPLIT
    raise GovernedQuarantineError(
        f"the governed quarantine evidence names {ticker} {when.isoformat()} as anomalous but its "
        f"preserved row shows neither factor moving; a quarantine cannot govern a movement the "
        f"evidence does not show")


def _ratio(value: Any, *, ticker: str, when: date, leg: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise GovernedQuarantineError(
            f"the preserved row for {ticker} {when.isoformat()} carries no numeric {leg}, so the "
            f"factor the movement sits on cannot be established")
    return float(value)


__all__ = [
    "POLICY_SCHEMA_VERSION",
    "QUARANTINE_EVIDENCE_ARTIFACT",
    "GovernedQuarantineError",
    "GovernedQuarantinePolicy",
    "QuarantinedMovement",
    "governed_quarantine_policy",
]
