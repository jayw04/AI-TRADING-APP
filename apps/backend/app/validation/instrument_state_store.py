"""The instrument's own durable book (R5c-2b2) — what MomentumDaily carries between sessions.

The census drove twenty-one years inside one process, so the instrument's state lived in memory. A
once-a-day forward runner cannot: the deployment lifecycle, the seed attempt, the last applied targets,
the positions and the equity the instrument reasons about must survive between invocations, or every
session would look like day one.

This is the INSTRUMENT's book, and it is not the shadow ledger. The two are deliberately separate:

  * the instrument book is what the strategy decides FROM — its own positions, equity and durable state;
  * the shadow ledger is the governed $100k performance accounting at the registered turnover cost.

They diverge by cumulative cost drag by design, which is exactly why a decision must never be validated
against the ledger (owner ruling 2026-07-23) and why the two are persisted separately here.

## Values are validated and canonicalized at every boundary

The self-digest proves the bytes did not change; it proves nothing about whether they mean anything.
`Decimal("NaN")` and `Decimal("Infinity")` construct happily and are not portfolio state, `true` is not
a session count, and 19 / 19.0 / 19.00 must be one value with one identity. Equity and quantities are
therefore validated as finite decimals and canonicalized on open, load and capture; zero holdings are
dropped; session metadata must be an exact non-negative integer with a last-session date that is null
exactly when no session has been seen.

## The same crash-safety discipline as the ledger

Committed storage is the source of truth for how many sessions exist. The book records how many it has
seen, and the two must agree before a session runs:

  BOOK_AHEAD_OF_RECORD    the instrument decided and its book was saved, but the observation never
                          committed — re-running would decide from a state no observation describes;
  BOOK_BEHIND_RECORD      the observation committed but the book save did not land;
  BOOK_SESSION_MISMATCH   the counts agree but the book's last session is not the record's.

None of these is repaired here. Recovery is an explicit, audited operation (ADR 0044 invariant 7), and
the runner refuses until it has been performed. A fresh book may only be opened when the committed
record is empty — a forward record never continues on a book that lost its history.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date as _date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.validation.forward_window import IntegrityStop
from app.validation.observation_store import Durability, default_durability

SCHEMA_VERSION = 1

# The only durable key a genuinely fresh book may carry. Everything else — the regime memory, the
# backstop clock, the last applied targets — is written by a session that has already happened.
FRESH_BOOK_STATE_KEYS = frozenset({"deployment"})


def _exact_decimal(raw: Any, *, field: str, allow_zero: bool = True,
                   allow_negative: bool = False) -> str:
    """Validate and CANONICALIZE a stored quantity.

    The self-digest proves the bytes did not change; it says nothing about whether they mean anything.
    `Decimal("NaN")` and `Decimal("Infinity")` construct happily and are not portfolio state — they
    would flow into sizing and comparisons without necessarily raising. Canonicalizing here also means
    19, 19.0 and 19.00 are one value with one book identity, rather than three.
    """
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InstrumentBookError(f"{field} is not a decimal: {raw!r}") from exc
    if not value.is_finite():
        raise InstrumentBookError(f"{field} is not finite: {raw!r}")
    if not allow_negative and value < 0:
        raise InstrumentBookError(f"{field} is negative: {raw!r}")
    if not allow_zero and value == 0:
        raise InstrumentBookError(f"{field} is zero: {raw!r}")
    normalized = value.normalize()
    return format(normalized if normalized != 0 else Decimal(0), "f")


def _exact_positions(raw: Any) -> dict[str, str]:
    """Canonical position book: finite, non-negative quantities, zero holdings DROPPED.

    A long-only instrument carries no negative quantity, and a zero holding is not a position — keeping
    one would make two identical books digest differently depending on how they got there.

    Two keys that canonicalize to the same symbol (`MSFT` and ` msft `) are a CONFLICT, not a merge. The
    quantities are never summed: summing would be a repair, and it would conceal an upstream book that
    has two disagreeing entries for one holding while still producing a valid, self-consistent digest.
    """
    if not isinstance(raw, dict):
        raise InstrumentBookError(f"positions must be an object, got {type(raw).__name__}")
    out: dict[str, str] = {}
    for ticker, qty in raw.items():
        symbol = str(ticker).upper().strip()
        if not symbol:
            raise InstrumentBookError("a position carries an empty ticker")
        canonical = _exact_decimal(qty, field=f"position {symbol}")
        if symbol in out:
            raise InstrumentBookError(
                f"positions contain duplicate canonical symbol {symbol!r} ({out[symbol]} and "
                f"{canonical}); the quantities are not summed, because a disagreement about one "
                f"holding is not something this book may repair")
        if Decimal(canonical) == 0:
            continue
        out[symbol] = canonical
    return out


def _exact_session_count(raw: Any) -> int:
    """An exact, non-negative JSON integer. `true` is not 1 and 1.5 is not 1."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise InstrumentBookError(f"sessions_recorded must be an integer, got {raw!r}")
    if raw < 0:
        raise InstrumentBookError(f"sessions_recorded is negative: {raw}")
    return raw


def _exact_session_date(raw: Any, *, sessions_recorded: int) -> str | None:
    """Null exactly when no session has been seen; a valid ISO date otherwise."""
    if sessions_recorded == 0:
        if raw is not None:
            raise InstrumentBookError(
                f"a book with no recorded sessions carries last_session_date {raw!r}")
        return None
    if raw is None:
        raise InstrumentBookError(
            f"a book with {sessions_recorded} recorded session(s) carries no last_session_date")
    try:
        return _date.fromisoformat(str(raw)).isoformat()
    except ValueError as exc:
        raise InstrumentBookError(f"last_session_date {raw!r} is not an ISO date") from exc


class InstrumentBookError(IntegrityStop):
    """The instrument's durable book is unreadable, or disagrees with the committed record. Fails
    closed — a session is never decided from a book whose history cannot be trusted."""


@dataclass(frozen=True)
class InstrumentBook:
    """One session-boundary snapshot of the instrument's own state.

    Quantities and equity are carried as decimal STRINGS: the instrument sizes in `Decimal`, and a
    float round-trip through JSON would quietly change what it decides.
    """
    schema_version: int
    state: dict[str, Any]                  # the strategy's durable state blob (deployment, seeds, …)
    positions: dict[str, str]              # ticker -> quantity, exact
    equity: str                            # exact
    sessions_recorded: int                 # committed observations this book has seen
    last_session_date: str | None
    book_digest: str = ""

    def with_digest(self) -> InstrumentBook:
        body = {k: v for k, v in asdict(self).items() if k != "book_digest"}
        return InstrumentBook(**body, book_digest=_digest(body))

    def to_open_provenance(self) -> dict[str, Any]:
        """Open provenance: shape and identity, never the instrument's positions or equity — those are
        the book's contents, and the record references them by digest."""
        return {
            "schema_version": self.schema_version,
            "state_keys": sorted(self.state),
            "position_count": len(self.positions),
            "sessions_recorded": self.sessions_recorded,
            "last_session_date": self.last_session_date,
            "book_digest": self.book_digest,
        }


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def open_fresh_book(*, starting_capital: float | Decimal, deployment_blob: dict[str, Any],
                    committed_count: int) -> InstrumentBook:
    """Open the instrument's book for a record that has not begun.

    Refuses when observations already exist: a forward record never continues on a book that lost its
    history, because the instrument would decide as though it held nothing.
    """
    if committed_count != 0:
        raise InstrumentBookError(
            f"committed storage holds {committed_count} observation(s); a fresh instrument book would "
            f"decide as though the record had never begun")
    return InstrumentBook(
        schema_version=SCHEMA_VERSION, state={"deployment": dict(deployment_blob)}, positions={},
        equity=_exact_decimal(starting_capital, field="starting capital", allow_zero=False),
        sessions_recorded=0, last_session_date=None).with_digest()


def load_instrument_book(path: Path | str) -> InstrumentBook | None:
    """Read the durable book, or None when it has never been written. Malformed is NOT 'no book'."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstrumentBookError(f"the instrument book at {p} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise InstrumentBookError(f"the instrument book at {p} is not an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise InstrumentBookError(
            f"the instrument book at {p} is schema version {payload.get('schema_version')!r}, not "
            f"{SCHEMA_VERSION}")
    try:
        sessions = _exact_session_count(payload["sessions_recorded"])
        book = InstrumentBook(
            schema_version=SCHEMA_VERSION, state=dict(payload["state"]),
            positions=_exact_positions(payload["positions"]),
            equity=_exact_decimal(payload["equity"], field="equity", allow_zero=False),
            sessions_recorded=sessions,
            last_session_date=_exact_session_date(payload.get("last_session_date"),
                                                  sessions_recorded=sessions),
            book_digest=str(payload.get("book_digest", "")))
    except InstrumentBookError as exc:
        raise InstrumentBookError(f"the instrument book at {p} is invalid: {exc}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise InstrumentBookError(f"the instrument book at {p} is malformed: {exc}") from exc
    if book.book_digest != book.with_digest().book_digest:
        raise InstrumentBookError(
            f"the instrument book at {p} fails its own digest — it was modified outside the runner")
    return book


def save_instrument_book(book: InstrumentBook, path: Path | str, *,
                         durability: Durability | None = None) -> None:
    """Persist atomically with full rename durability, exactly as the shadow ledger does: temp file →
    fsync → replace → fsync the parent directory. A pre-rename failure never destroys the existing
    book."""
    dur = durability or default_durability()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(asdict(book.with_digest()), sort_keys=True, indent=2) + "\n").encode("utf-8")
    tmp = p.with_suffix(p.suffix + ".tmp")
    replaced = False
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
        dur.fsync_file(tmp)
        os.replace(tmp, p)
        replaced = True
        dur.fsync_dir(p.parent)
    except BaseException:
        if not replaced:
            with contextlib.suppress(OSError):
                tmp.unlink()
        raise


def assert_genuinely_fresh(book: InstrumentBook, *,
                           expected_starting_capital: float | Decimal | None = None) -> None:
    """A zero-session book must be genuinely fresh, not merely counted as zero.

    `sessions_recorded == 0` is a claim about history, not about contents. A book with positions, an
    equity that is not the governed starting capital, a last-session value, or durable keys only a
    completed session writes describes a history the record does not have — and the empty-record
    exception must not let it through.
    """
    problems: list[str] = []
    if book.positions:
        problems.append(f"holds {len(book.positions)} position(s)")
    if book.last_session_date is not None:
        problems.append(f"records a last session ({book.last_session_date})")
    unexpected = sorted(set(book.state) - FRESH_BOOK_STATE_KEYS)
    if unexpected:
        problems.append(f"carries durable key(s) {unexpected} that only a completed session writes")
    if expected_starting_capital is not None:
        expected = Decimal(str(expected_starting_capital))
        if Decimal(book.equity) != expected:
            problems.append(f"has equity {book.equity}, not the governed starting capital {expected}")
    if problems:
        raise InstrumentBookError(
            "the instrument book reports zero sessions but is not fresh: it "
            + "; ".join(problems)
            + " — a record with no observations cannot continue from a book that has a history")


def reconcile_with_record(book: InstrumentBook, *, committed_count: int,
                          last_committed_session: str | None,
                          expected_starting_capital: float | Decimal | None = None) -> None:
    """Require the instrument's book to describe the same history as committed storage.

    Nothing is repaired: each divergence names what happened and what evidence a governed recovery
    would use, and the runner stops until that recovery has been performed. When the record is empty the
    book must additionally be genuinely fresh — see `assert_genuinely_fresh`.
    """
    if book.sessions_recorded > committed_count:
        raise InstrumentBookError(
            f"the instrument book has seen {book.sessions_recorded} session(s) but committed storage "
            f"holds {committed_count} (BOOK_AHEAD_OF_RECORD): the instrument decided and its book was "
            f"saved, but the observation never committed — recovery is an explicit audited operation")
    if book.sessions_recorded < committed_count:
        raise InstrumentBookError(
            f"the instrument book has seen {book.sessions_recorded} session(s) but committed storage "
            f"holds {committed_count} (BOOK_BEHIND_RECORD): the observation committed but the book "
            f"save did not land — the committed record is the audited recovery input")
    if book.last_session_date != last_committed_session:
        raise InstrumentBookError(
            f"the instrument book's last session {book.last_session_date!r} is not the record's "
            f"{last_committed_session!r} (BOOK_SESSION_MISMATCH)")
    if committed_count == 0:
        assert_genuinely_fresh(book, expected_starting_capital=expected_starting_capital)


def apply_to_adapter(book: InstrumentBook, adapter: Any) -> None:
    """Restore the instrument's book onto the context it will decide from."""
    adapter._state = dict(book.state)
    adapter._positions = {ticker: Decimal(qty) for ticker, qty in book.positions.items()}
    adapter.equity = Decimal(book.equity)


def capture_from_adapter(adapter: Any, *, sessions_recorded: int,
                         last_session_date: str) -> InstrumentBook:
    """Take the instrument's book AFTER a session, ready to persist once the observation commits."""
    count = _exact_session_count(sessions_recorded)
    if count < 1:
        raise InstrumentBookError(
            "a book captured after a session must record at least one session")
    return InstrumentBook(
        schema_version=SCHEMA_VERSION, state=dict(getattr(adapter, "_state", {}) or {}),
        positions=_exact_positions(dict(getattr(adapter, "_positions", {}) or {})),
        equity=_exact_decimal(getattr(adapter, "equity", 0), field="equity", allow_zero=False),
        sessions_recorded=count,
        last_session_date=_exact_session_date(last_session_date,
                                              sessions_recorded=count)).with_digest()


@dataclass
class InstrumentBookPaths:
    """Where the book and its pre-session snapshot live, beside the shadow ledger's own files."""
    book_path: Path
    pre_session_snapshot: Path = field(init=False)

    def __post_init__(self) -> None:
        self.pre_session_snapshot = self.book_path.with_suffix(
            self.book_path.suffix + ".pre-session")
