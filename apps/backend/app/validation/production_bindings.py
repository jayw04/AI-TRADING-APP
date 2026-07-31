"""Forward-validation PRODUCTION data bindings (R5c) — every data input tied to a real source.

R5a proves the data is final; R5b proves the adjusted series reflects the declared actions. This module
is where those checks stop taking their inputs from a caller and start taking them from the governed
store itself:

  * `declare_action_source(store)` — the corporate-action source declaration DERIVED from the completed
    ingest artifact, never hand-written;
  * `pit_price_fn(store)` — the point-in-time price function the shadow ledger marks against;
  * `build_forward_context(...)` — the per-session `ForwardRunContext` on the frozen §0 bindings.

## Source authority is LINKED to a completed ingest execution, not asserted

`ingest_runs` records that an ingest RAN — not what it COVERED — and deriving a coverage window from
`MIN/MAX(actions.date)` would be exactly the invented coverage the governance forbids: the earliest row
present is evidence of what was loaded, not of what was requested, and on an empty table it is no
evidence at all.

A coverage row is therefore written only by `FactorDataStore.finalize_dataset_ingest`, in the same
transaction that marks the ingest complete, referencing that execution's `run_id`, with the artifact
digest computed from the artifact file itself. `declare_action_source` re-checks the whole chain and
returns a NON-authoritative declaration unless every link holds:

  * a coverage row exists for the dataset and its linked ingest run exists, matches the dataset,
    finished, and completed `ok`;
  * the recorded row count equals the run's row count and the window is not inverted;
  * the artifact digest is exactly 64 lowercase hex characters and the artifact path is recorded;
  * **the recorded artifact still exists and still hashes to that digest** — authority rests on an
    immutable artifact, so a file that was replaced, corrupted or deleted after the ingest revokes it;
  * no running or failed ingest for that dataset has started since — such a run may have mutated the
    dataset, so the earlier coverage no longer stands.

The governed store has no coverage row today (its `actions` table was never ingested), so the honest
result is "coverage unknown" and R5b's verdict stays NOT_PROVEN_INSUFFICIENT_DATA.

## Prices are point-in-time AND strict

`pit_price_fn` reads `closeadj` for the exact session only — it cannot return a later session's price
because it never queries one. But returning `None` for a missing mark is not neutral either: the ledger
would keep the sleeve at its previous mark, which is a stale valuation dressed as an absence. The
production binding is therefore `strict_pit_price_fn`, which RAISES on any missing, null or nonpositive
mark it is asked for, so a session whose held or target names cannot all be marked stops instead of
being valued on yesterday's prices.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.factor_data.store import ACTIONS_DATASET as _STORE_ACTIONS_DATASET
from app.validation.adjustment_verifier import ActionSourceDeclaration
from app.validation.forward_window import (
    BENCHMARK_COMMITS,
    DGS3MO_OBSERVATION_CUTOFF,
    EFFECTIVE_DSR_TRIAL_COUNT,
    FROZEN_CONFIG,
    ForwardRunContext,
    IntegrityStop,
)

# Re-exported from the store, which owns dataset naming. Defined in one place so the ingest that
# writes the coverage row and the consumer that reads it can never drift apart on the name.
ACTIONS_DATASET = _STORE_ACTIONS_DATASET


@dataclass(frozen=True)
class ManifestBoundAuthorityPolicy:
    """Where source authority resides for a countersigned whole-corpus reconstruction.

    ⚠⚠ THIS IS NOT A WAIVER OF SOURCE AUTHORITY. It states where authority lives for a construction
    that was assembled once, off-host, and then countersigned by digest.

    For a base-plus-delta corpus the deployment continues to ingest from artifacts it holds, so the
    recorded `artifact_path` is a runtime dependency and re-hashing it is the authority check. A Layer
    2 reconstruction is different in kind: its source ZIPs were CONSTRUCTION inputs on the build
    machine, and the governed identity of what they produced is bound by the corpus manifest and its
    countersignature. Every one of its `dataset_coverage` rows therefore records a build-machine
    filesystem path (`C:\\LLM-RAG-APP\\layer2-vintage\\...`) that cannot exist on the deployment host,
    and re-hashing it can only ever fail.

    So for a reconstruction the artifact path is demoted to audit metadata and authority is proved
    instead by: the immutable manifest, the countersignature sidecar that binds it, and the store's own
    provenance naming the SAME source vintage the manifest binds. A missing, malformed, unbound or
    mismatched provenance still refuses — the check moves, it does not weaken.

    The policy is constructed at the composition root, never here: this module is handed the conclusion
    (`the governed vintage is X`) rather than the corpus formats it would have to learn to derive it.
    """
    #: The `source_vintage_sha256` the governed manifest binds. The single value every authoritative
    #: coverage row for the dataset must name.
    source_vintage_sha256: str
    #: Recorded so the declaration can name the construction whose authority is being relied on.
    corpus_manifest_sha256: str
    countersignature_sha256: str
    construction_kind: str


@dataclass(frozen=True)
class ParsedSourceIdentity:
    """The load-bearing fields of a `dataset_coverage.source_identity`."""
    namespace: str                    # e.g. SHARADAR
    dataset: str                      # e.g. ACTIONS
    source_vintage_sha256: str


def parse_source_identity(raw: object) -> ParsedSourceIdentity | None:
    """Parse `SHARADAR/<DATASET>|key=value|…` into its two load-bearing fields, or `None`.

    ⚠ Parsed, never substring-matched, and never compared whole. The recorded string also carries
    `export_object`, `last_refreshed_time` and `reason`, which are audit metadata and legitimately
    vary; comparing the whole string would refuse on cosmetic drift, and a substring test would accept
    a partial match. So the two fields that carry meaning are extracted and compared exactly.

    Refuses (returns None) a malformed identity, a missing or duplicated required key, an absent
    dataset prefix, or a vintage that is not a sha256.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    head, *rest = text.split("|")
    if head.count("/") != 1:
        return None
    namespace, _, dataset = head.partition("/")
    if not namespace.strip() or not dataset.strip():
        return None

    seen: dict[str, str] = {}
    for field in rest:
        if "=" not in field:
            continue                    # audit metadata may be free-form; only keyed fields count
        key, _, value = field.partition("=")
        key = key.strip()
        if key in seen:
            return None                 # a duplicated key makes the binding ambiguous
        seen[key] = value.strip()

    vintage = seen.get("source_vintage_sha256", "")
    if not _is_sha256(vintage):
        return None
    return ParsedSourceIdentity(namespace=namespace.strip(), dataset=dataset.strip(),
                                source_vintage_sha256=vintage)


class BindingError(IntegrityStop):
    """A production binding could not be established from an authoritative source. Fails closed."""


def declare_action_source(
    store: Any,
    *,
    dataset: str = ACTIONS_DATASET,
    authority_policy: ManifestBoundAuthorityPolicy | None = None,
) -> ActionSourceDeclaration:
    """Derive the corporate-action source declaration from the store's own ingest provenance.

    Authoritative ONLY when a completed ingest recorded its coverage window and artifact identity AND
    that artifact still hashes to the recorded digest. No record → `authoritative=False` with no
    coverage, which is the truthful state of a store whose ACTIONS dataset was never ingested (the
    governed store today). The returned identity carries the artifact digest and the ingest run id, so
    a later verification cannot be re-read against a different load of the same dataset.
    """
    con = getattr(store, "con", store)
    if not hasattr(con, "execute"):
        raise BindingError(f"not a queryable store: {type(store).__name__}")
    try:
        row = con.execute(
            "SELECT c.coverage_start, c.coverage_end, c.artifact_sha256, c.artifact_path, "
            "c.source_identity, c.recorded_at, c.ingest_run_id "
            "FROM dataset_coverage c JOIN ingest_runs r ON r.run_id = c.ingest_run_id "
            "WHERE c.dataset = ? AND r.dataset = c.dataset AND LOWER(c.status) = 'ok' "
            "AND LOWER(r.status) = 'ok' AND r.finished_at IS NOT NULL AND r.rows = c.rows_loaded "
            "AND c.coverage_start <= c.coverage_end "
            "ORDER BY c.recorded_at DESC LIMIT 1", [dataset]).fetchone()
    except Exception as exc:
        # An older store predates the coverage table or the run linkage entirely: coverage unknown.
        return ActionSourceDeclaration(
            identity=f"{dataset}:coverage-unrecorded ({type(exc).__name__})", authoritative=False)
    if row is None:
        # No coverage row, or one whose linked execution is absent, failed, unfinished, of the wrong
        # dataset, row-count-mismatched, or date-inverted. None of those confer authority.
        return ActionSourceDeclaration(identity=f"{dataset}:coverage-unlinked", authoritative=False)

    coverage_start, coverage_end, artifact, artifact_path, source_identity, recorded_at, run_id = row
    if not _is_sha256(artifact) or not str(artifact_path or "").strip() \
            or not str(source_identity or "").strip():
        return ActionSourceDeclaration(
            identity=f"{dataset}:coverage-incomplete", authoritative=False,
            coverage_start=coverage_start, coverage_end=coverage_end)

    if authority_policy is None:
        # Authority rests on an IMMUTABLE artifact, so the artifact is re-verified — not merely
        # referenced. A recorded digest with valid syntax proves nothing about the bytes on disk today.
        ok, reason = _artifact_matches(artifact_path, str(artifact))
        if not ok:
            return ActionSourceDeclaration(
                identity=f"{dataset}:{reason}", authoritative=False,
                coverage_start=coverage_start, coverage_end=coverage_end)
    else:
        # Manifest-bound authority. `artifact_path` is audit metadata here and is NOT resolved; the
        # binding that has to hold is that this store's provenance names the same governed vintage the
        # countersigned manifest binds — for EVERY authoritative row, not merely the newest one.
        failure = _manifest_bound_failure(con, dataset=dataset, policy=authority_policy)
        if failure is not None:
            return ActionSourceDeclaration(
                identity=f"{dataset}:{failure}", authoritative=False,
                coverage_start=coverage_start, coverage_end=coverage_end)

    # A running or failed ingest since the coverage was recorded may have mutated the dataset.
    try:
        unclean = con.execute(
            "SELECT COUNT(*) FROM ingest_runs WHERE dataset = ? AND LOWER(status) <> 'ok' "
            "AND started_at >= ?", [dataset, recorded_at]).fetchone()
    except Exception:                                     # pragma: no cover - defensive
        unclean = (1,)
    if unclean and unclean[0]:
        return ActionSourceDeclaration(
            identity=f"{dataset}:superseded-by-unclean-ingest", authoritative=False,
            coverage_start=coverage_start, coverage_end=coverage_end)

    return ActionSourceDeclaration(
        identity=f"{source_identity}@{artifact}#{run_id}", authoritative=True,
        coverage_start=coverage_start, coverage_end=coverage_end)


def _manifest_bound_failure(con: Any, *, dataset: str,
                            policy: ManifestBoundAuthorityPolicy) -> str | None:
    """Why manifest-bound authority does NOT hold for `dataset`, or `None` when it does.

    ⚠ Checked across EVERY authoritative row, not just the one the caller selected. A store carrying
    two `ok` coverage rows from two different vintages is exactly the conflict worth refusing, and
    reading only the newest would hide it. Multiple rows from the SAME governed vintage are benign —
    which is why this is a vintage-agreement test and not a row-count invariant, a rule that would
    refuse the harmless case and miss the dangerous one.
    """
    try:
        rows = con.execute(
            "SELECT c.source_identity FROM dataset_coverage c "
            "JOIN ingest_runs r ON r.run_id = c.ingest_run_id "
            "WHERE c.dataset = ? AND r.dataset = c.dataset AND LOWER(c.status) = 'ok' "
            "AND LOWER(r.status) = 'ok' AND r.finished_at IS NOT NULL "
            "AND r.rows = c.rows_loaded AND c.coverage_start <= c.coverage_end",
            [dataset]).fetchall()
    except Exception:                                     # pragma: no cover - defensive
        return "coverage-unreadable"
    if not rows:
        return "coverage-unlinked"

    vintages: set[str] = set()
    for (raw,) in rows:
        parsed = parse_source_identity(raw)
        if parsed is None:
            return "source-identity-malformed"
        # The dataset the row claims must be the dataset being declared. A TICKERS row cannot confer
        # authority on ACTIONS however well-formed it is.
        if parsed.dataset.strip().upper() != str(dataset).strip().upper():
            return "source-identity-wrong-dataset"
        vintages.add(parsed.source_vintage_sha256)

    if len(vintages) > 1:
        return "source-vintage-conflict"
    if vintages != {str(policy.source_vintage_sha256).strip().lower()}:
        return "source-vintage-unbound"
    return None


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def _artifact_matches(artifact_path: object, expected_sha256: str) -> tuple[bool, str]:
    """Re-verify the recorded artifact against its recorded digest.

    Deliberately NOT cached: the whole point is that the bytes are re-read. (A cache would have to key
    on path + size + mtime + expected digest, and for an ACTIONS artifact the hash is cheap enough that
    the safer thing is simply to do it.) Returns (ok, reason) where the reason names what failed.
    """
    path = Path(str(artifact_path or ""))
    try:
        if not path.is_file():
            return False, "artifact-missing"
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            while block := fh.read(1 << 20):
                digest.update(block)
    except OSError:
        return False, "artifact-unreadable"
    if digest.hexdigest() != expected_sha256:
        return False, "artifact-digest-mismatch"
    return True, ""


def pit_price_fn(store: Any) -> Callable[[str, date], float | None]:
    """A point-in-time `closeadj` reader: the price of `ticker` ON `session`, or None.

    No fallback to a neighbouring session, no forward fill, no "last known price". A name without a
    usable mark on the session returns None, and the caller (the shadow ledger's mark-to-market) leaves
    that sleeve at its previous mark rather than inventing one — the same behaviour the census had.
    """
    con = getattr(store, "con", store)
    if not hasattr(con, "execute"):
        raise BindingError(f"not a queryable store: {type(store).__name__}")

    def price(ticker: str, session: date) -> float | None:
        row = con.execute(
            "SELECT closeadj FROM sep WHERE ticker = ? AND date = ? AND closeadj IS NOT NULL",
            [ticker, session]).fetchone()
        return float(row[0]) if row is not None and row[0] is not None else None

    return price


class PriceUnavailable(IntegrityStop):
    """A security the ledger must mark has no usable exact-session price. Fails closed: the session is
    not valued on a stale mark, it is not valued at all."""


def strict_pit_price_fn(store: Any) -> Callable[[str, date], float]:
    """The PRODUCTION price function: point-in-time, and strict.

    `pit_price_fn` returning None is not neutral — the shadow ledger's mark-to-market simply keeps the
    sleeve at its previous mark, which is a stale valuation wearing an absence's clothes. Every price
    the ledger asks for is a security it is actually accounting for (a current holding being marked, or
    a decision target being sleeved), so a missing, null or nonpositive mark raises instead. The runner
    maps that to NOT_READY_CURRENT_SESSION_MISSING: nothing booked, nothing committed, count unchanged.
    """
    lenient = pit_price_fn(store)

    def price(ticker: str, session: date) -> float:
        value = lenient(ticker, session)
        if value is None:
            raise PriceUnavailable(
                f"{ticker} has no usable closeadj on {session.isoformat()}; a security the ledger must "
                f"mark cannot be valued on an earlier session's price")
        if value <= 0:
            raise PriceUnavailable(
                f"{ticker} has a nonpositive closeadj ({value}) on {session.isoformat()}")
        return value

    return price


def build_forward_context(
    session: date,
    *,
    dgs3mo_path: Path,
    trial_ledger_path: Path,
    ledger_account_id: int,
    # ⚠⚠ NO DEFAULT, and it never gets one again. This previously defaulted to
    # VALIDATION_MEASUREMENT_COMMIT — the EXPECTED value — so unless a caller overrode it the gate
    # compared the constant to itself and passed unconditionally. The actual deployed HEAD is a fact
    # about the running process that only the caller knows; a default is a fabricated answer.
    code_commit: str,
    measurement_freeze: Any,
    runtime_root: Path,
    is_nyse_trading_session: bool = True,
    ancestry_marker: Path | None = None,
    config: dict | None = None,
) -> ForwardRunContext:
    """The per-session run context on the FROZEN §0 bindings.

    Everything the preflight gate verifies comes from the frozen module constants rather than from a
    caller-supplied dict, so a session cannot be run against a quietly different benchmark set, cutoff
    or trial count. The two artifact PATHS and the ledger account are deployment facts and stay
    parameters; the gate digests the artifacts themselves.
    """
    if ledger_account_id == 4:
        raise BindingError("the validation ledger may never be Account 4")
    return ForwardRunContext(
        session_date=session,
        is_nyse_trading_session=is_nyse_trading_session,
        code_commit=code_commit,
        benchmark_commits=dict(BENCHMARK_COMMITS),
        dgs3mo_path=dgs3mo_path,
        dgs3mo_cutoff=DGS3MO_OBSERVATION_CUTOFF,
        trial_ledger_path=trial_ledger_path,
        effective_dsr_trial_count=EFFECTIVE_DSR_TRIAL_COUNT,
        config=dict(config or FROZEN_CONFIG),
        ledger_account_id=ledger_account_id,
        ledger_is_shadow_or_separate_paper=True,
        references_account4_capital=False,
        references_retired_baseline=False,
        measurement_freeze=measurement_freeze,
        runtime_root=runtime_root,
        ancestry_marker=ancestry_marker,
    )
