"""ADR 0043 Phase-0 same-session orchestrator — the instrument that produces the readiness package.

Runs the frozen same-session sequence and STOPS with a package for broker-submission authorization.
It submits no order and generates no loss. The ONLY write it can perform is the immutable session
baseline, behind ``--capture-baseline``; without that flag it is strictly read-only.

WHY THIS IS VERSION CONTROLLED
------------------------------
Its output is the evidence a Phase-0 session is authorized from. An instrument that exists only as
a file on a host cannot be reviewed, cannot be diffed, and cannot be shown to be the thing that
produced a given package. The governed path is: review → merge → identify the exact merged git blob
→ verify its SHA-256 → transfer that blob to the validation host → mount it read-only into the
UNCHANGED deployed image → record host/container SHA equality. Version control does not require
baking it into the image, so runtime continuity is preserved.

The package embeds ``tool_version`` and the SHA-256 of the running source, so a package can always
be tied back to the instrument that emitted it.

EVERY IDENTITY IS REQUIRED, NONE IS DEFAULTED
---------------------------------------------
Instance, database URL, broker account, user, account, and the frozen limits digest must all be
supplied explicitly and must all match. A tool that defaults its own identity can run correctly
against the wrong machine — and every command here bind-mounts a data directory, so "the wrong
machine" means the production database.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from scripts.adr0043_reachability import Caps, assess

TOOL_VERSION = "1.0.0"

#: The only broker methods this tool may reach. Anything that could place, change, or cancel an
#: order is absent BY CONSTRUCTION, not by convention — see ReadOnlyBrokerView.
ALLOWED_BROKER_METHODS = frozenset(
    {"get_account", "get_positions", "list_orders", "get_order", "get_clock", "_client"}
)

REFUSE_INSTANCE = "VALIDATION_INSTANCE_MISMATCH"
REFUSE_DB_PATH = "DATABASE_PATH_MISMATCH"
REFUSE_CONFIG = "REQUIRED_CONFIGURATION_MISSING"
REFUSE_BROKER_IDENTITY = "BROKER_ACCOUNT_IDENTITY_MISMATCH"
REFUSE_BROKER_UNREACHABLE = "BROKER_UNREACHABLE"
REFUSE_MUTATING_CALL = "MUTATING_BROKER_CALL_ATTEMPTED"
REFUSE_LIMITS = "FROZEN_LIMITS_DIGEST_MISMATCH"
REFUSE_POSITIONS = "POSITION_PRECONDITION_FAILED"
REFUSE_NOT_FLAT = "ACCOUNT_NOT_FLAT"
REFUSE_SESSION = "MARKET_NOT_CURRENTLY_OPEN"
REFUSE_BASELINE_CONTRADICTORY = "CONTRADICTORY_SESSION_BASELINE"

_SHA_FIELDS = (
    "user_id", "scope_type", "scope_id", "broker_mode", "max_daily_loss", "max_position_qty",
    "max_position_notional", "max_gross_exposure", "max_orders_per_minute", "max_orders_per_day",
    "allow_short", "allowed_symbols", "denied_symbols",
)


class SessionOpenRefused(RuntimeError):
    """A precondition for a VALID readiness package is absent. Refusing is a correct outcome."""

    def __init__(self, code: str, detail: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.diagnostics = diagnostics or {}


class ReadOnlyBrokerView:
    """A broker adapter with every mutating capability removed.

    "The tool contains no submit call" is a property of today's source; this is a property of the
    object, so a future edit that reaches for one fails loudly instead of trading.
    """

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        if name not in ALLOWED_BROKER_METHODS:
            raise SessionOpenRefused(
                REFUSE_MUTATING_CALL,
                f"{name!r} is not on the read-only allowlist for this tool",
                {"attempted": name, "allowed": sorted(ALLOWED_BROKER_METHODS)},
            )
        self.calls.append(name)
        return getattr(self._adapter, name)


@dataclass(frozen=True)
class Config:
    """Every identity the run must match. All required; none defaulted."""

    user_id: int
    account_id: int
    expected_broker_account: str
    forbidden_broker_account: str
    expected_instance_id: str
    expected_db_url: str
    frozen_limits_sha256: str
    protected: tuple[tuple[str, D], ...]
    churn_symbols: tuple[str, ...]
    caps: Caps

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        env = dict(os.environ if env is None else env)

        def need(key: str) -> str:
            value = env.get(key, "").strip()
            if not value:
                raise SessionOpenRefused(
                    REFUSE_CONFIG,
                    f"{key} is required; this tool never defaults an identity",
                    {"missing": key},
                )
            return value

        return cls(
            user_id=int(need("ADR0043_USER")),
            account_id=int(need("ADR0043_ACCOUNT")),
            expected_broker_account=need("ADR0043_EXPECTED_BROKER_ACCOUNT"),
            forbidden_broker_account=need("ADR0043_FORBIDDEN_BROKER_ACCOUNT"),
            expected_instance_id=need("ADR0043_EXPECTED_INSTANCE_ID"),
            expected_db_url=need("ADR0043_EXPECTED_DB_URL"),
            frozen_limits_sha256=need("ADR0043_FROZEN_LIMITS_SHA256"),
            protected=tuple(
                (sym.strip().upper(), D(qty))
                for sym, qty in (p.split(":") for p in need("ADR0043_LEGS").split(","))
            ),
            churn_symbols=tuple(s.strip().upper() for s in need("ADR0043_CHURN").split(",") if s.strip()),
            caps=Caps(
                loss_target=D(need("ADR0043_LOSS_TARGET")),
                max_round_trips=int(need("ADR0043_MAX_ROUND_TRIPS")),
                max_setup_notional=D(need("ADR0043_MAX_SETUP_NOTIONAL")),
                max_position_qty=D(need("ADR0043_MAX_POSITION_QTY")),
            ),
        )


# --------------------------------------------------------------------------------- guards


def check_instance(cfg: Config, observed_instance_id: str | None) -> dict[str, Any]:
    """The run must be on the validation host. `ssh workbench` is the PRODUCTION paper stack, and
    every documented invocation bind-mounts a data directory — so a tool that cannot tell the hosts
    apart is one typo away from pointing canary tooling at the live book."""
    if not observed_instance_id:
        raise SessionOpenRefused(
            REFUSE_INSTANCE, "the host identity could not be read; it cannot be assumed"
        )
    if observed_instance_id != cfg.expected_instance_id:
        raise SessionOpenRefused(
            REFUSE_INSTANCE,
            "this is not the approved validation instance",
            {"observed": observed_instance_id, "expected": cfg.expected_instance_id},
        )
    return {"instance_id": observed_instance_id, "ok": True}


def check_db_path(cfg: Config, observed_db_url: str | None) -> dict[str, Any]:
    """Exact match, not a substring or a suffix: `.../workbench.sqlite` is a suffix of both the
    validation database and the production one."""
    if observed_db_url != cfg.expected_db_url:
        raise SessionOpenRefused(
            REFUSE_DB_PATH,
            "the configured database is not the approved validation database",
            {"observed": observed_db_url, "expected": cfg.expected_db_url},
        )
    return {"db_url": observed_db_url, "ok": True}


def fetch_account(broker: Any, *, attempts: int = 5, backoff_s: float = 0.5) -> dict[str, Any]:
    """The broker account payload, with bounded retries. 5xx flaps against Alpaca are routine and a
    same-session procedure cannot afford to lose the session to one; exhausting the attempts is a
    refusal, never a fabricated payload."""
    last: str | None = None
    for attempt in range(attempts):
        try:
            raw = broker.get_account()
            if raw:
                return dict(raw)
            last = "broker returned an empty account payload"
        except SessionOpenRefused:
            raise
        except Exception as exc:  # noqa: BLE001 — type + bounded message, never the object
            last = f"{type(exc).__name__}: {str(exc)[:200]}"
        if attempt < attempts - 1:
            time.sleep(backoff_s * (2**attempt))
    raise SessionOpenRefused(
        REFUSE_BROKER_UNREACHABLE, f"no account payload after {attempts} attempts", {"last": last}
    )


def check_broker_identity(cfg: Config, account: dict[str, Any]) -> dict[str, Any]:
    number = str(account.get("account_number") or "")
    status = str(account.get("status") or "")
    if number == cfg.forbidden_broker_account:
        raise SessionOpenRefused(
            REFUSE_BROKER_IDENTITY,
            "the credential resolves to the FORBIDDEN account",
            {"observed": number, "forbidden": cfg.forbidden_broker_account},
        )
    if number != cfg.expected_broker_account:
        raise SessionOpenRefused(
            REFUSE_BROKER_IDENTITY,
            "the credential does not resolve to the canary account",
            {"observed": number, "expected": cfg.expected_broker_account},
        )
    if status.upper() != "ACTIVE":
        raise SessionOpenRefused(
            REFUSE_BROKER_IDENTITY, f"account status is {status!r}, not ACTIVE", {"status": status}
        )
    return {"account_number": number, "status": status, "ok": True}


def limits_sha256(row: dict[str, Any]) -> str:
    """The digest of the frozen limits row. Field set and normalisation are part of the frozen
    contract — changing either silently invalidates every previously recorded digest."""

    def norm(key: str, value: Any) -> Any:
        if key in ("max_daily_loss", "max_position_notional", "max_gross_exposure"):
            return str(D(str(value)).quantize(D("0.01")))
        if key == "max_position_qty":
            return str(D(str(value)))
        if key == "scope_type":
            return "global"
        if key in ("allowed_symbols", "denied_symbols"):
            return json.loads(value) if isinstance(value, str) else value
        if key == "allow_short":
            return bool(value)
        return value

    payload = {k: norm(k, row[k]) for k in _SHA_FIELDS}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def check_limits(cfg: Config, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) != 1:
        raise SessionOpenRefused(
            REFUSE_LIMITS,
            f"expected exactly one limits row for user {cfg.user_id}, found {len(rows)}",
            {"row_count": len(rows)},
        )
    digest = limits_sha256(rows[0])
    if digest != cfg.frozen_limits_sha256:
        raise SessionOpenRefused(
            REFUSE_LIMITS,
            "the limits row has changed since it was frozen; continuity is broken",
            {"observed": digest, "expected": cfg.frozen_limits_sha256},
        )
    return {"limits_sha256": digest, "sha_unchanged": True}


def check_positions(
    cfg: Config, broker_positions: dict[str, D], db_positions: dict[str, D]
) -> dict[str, Any]:
    """The protected legs, exactly, on both sides. An unrelated position means the account is not
    the account the plan was frozen against."""
    expected = {sym: qty for sym, qty in cfg.protected}
    broker_held = {s: q for s, q in broker_positions.items() if q != 0}
    db_held = {s: q for s, q in db_positions.items() if q != 0}
    if broker_held != expected or db_held != expected:
        raise SessionOpenRefused(
            REFUSE_POSITIONS,
            "positions do not match the frozen legs on both the broker and the ledger",
            {
                "expected": {s: str(q) for s, q in expected.items()},
                "broker": {s: str(q) for s, q in broker_held.items()},
                "db": {s: str(q) for s, q in db_held.items()},
            },
        )
    return {"legs": {s: str(q) for s, q in expected.items()}, "ok": True}


def check_flat(open_orders: int, held_reservations: int) -> dict[str, Any]:
    if open_orders or held_reservations:
        raise SessionOpenRefused(
            REFUSE_NOT_FLAT,
            "the account carries open orders or held reservations",
            {"open_orders": open_orders, "held_reservations": held_reservations},
        )
    return {"open_orders": 0, "held_reservations": 0, "clean": True}


def check_session_open(market_open_now: bool | None, *, required: bool) -> dict[str, Any]:
    """`--capture-baseline` demands a positively observed open market. An unknown clock is not an
    open one: a baseline minted outside the session it claims to describe is unauditable, and the
    same-session rule means it cannot be corrected afterwards."""
    if required and market_open_now is not True:
        raise SessionOpenRefused(
            REFUSE_SESSION,
            "the market is not positively observed to be open right now",
            {"market_open_now": market_open_now},
        )
    return {"market_open_now": market_open_now}


def select_existing_baseline(rows: list[dict[str, Any]], session_date: str) -> dict[str, Any] | None:
    """The session's existing ACTIVE baseline, if any — so a re-run REUSES rather than recaptures.

    Two ACTIVE rows for one session is refused rather than resolved: the run would have to pick,
    and picking is a guess about which number the session is being judged against.
    """
    active = [
        r
        for r in rows
        if r["market_session_date"] == session_date and r["status"] == "ACTIVE"
    ]
    if len(active) > 1:
        raise SessionOpenRefused(
            REFUSE_BASELINE_CONTRADICTORY,
            f"{len(active)} ACTIVE baselines for session {session_date}",
            {"baseline_ids": [r["id"] for r in active]},
        )
    return active[0] if active else None


# ---------------------------------------------------------------------------- evidence


def source_digest() -> dict[str, str]:
    """SHA-256 of the running source of both tool modules, so a package names its instrument."""
    here = Path(__file__).resolve().parent
    digests = {}
    for name in ("adr0043_session_open.py", "adr0043_reachability.py"):
        path = here / name
        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "ABSENT"
    return digests


def write_package_atomically(package: dict[str, Any], path: Path) -> None:
    """Write once, completely, or not at all.

    A reader that finds a truncated package must never mistake it for a complete one, so the
    content lands in a temp file in the SAME directory (same filesystem, so ``os.replace`` is
    atomic) and is renamed over the target.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(package, indent=2, sort_keys=True, default=str)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".sessionpkg-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def build_package(
    *,
    cfg: Config,
    steps: dict[str, Any],
    captured_at: datetime,
    capture_requested: bool,
) -> dict[str, Any]:
    ready = all(
        steps.get(k, {}).get("ok") or steps.get(k, {}).get("clean") or steps.get(k, {}).get("sha_unchanged")
        for k in ("1_instance", "2_database", "3_identity", "4_positions", "5_flat", "6_limits")
    )
    reach = steps.get("9_reachability", {})
    return {
        "tool": {
            "name": "adr0043_session_open",
            "version": TOOL_VERSION,
            "source_sha256": source_digest(),
        },
        "captured_utc": captured_at.isoformat(),
        "classification": (
            "AUTHORITATIVE_SESSION_READINESS" if capture_requested else "READ_ONLY_PRECHECK"
        ),
        "identity": {
            "user_id": cfg.user_id,
            "account_id": cfg.account_id,
            "expected_broker_account": cfg.expected_broker_account,
            "expected_instance_id": cfg.expected_instance_id,
            "expected_db_url": cfg.expected_db_url,
            "frozen_limits_sha256": cfg.frozen_limits_sha256,
        },
        "steps": steps,
        "READY_FOR_BASELINE_AND_PREFLIGHT": bool(ready),
        "REACHABILITY_VERDICT": reach.get("verdict"),
        "REACHABILITY_BINDING": reach.get("binding", False),
        "NEXT": (
            "Return this package for explicit broker-submission authorization. No orders were "
            "submitted and none are authorized by this package."
        ),
    }


# ---------------------------------------------------------------------------- entrypoint


def _instance_id_from_host() -> str | None:
    """The host's own identity. Read from a file the provisioner writes, not from the network, so
    the check works inside a container with no metadata access."""
    path = Path(os.environ.get("ADR0043_INSTANCE_ID_FILE", "/app/data/adr0043_instance_id"))
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture-baseline",
        action="store_true",
        help="perform the ONE write: the immutable session baseline, at the eligible open",
    )
    parser.add_argument("--output", type=Path, required=True, help="path for the evidence package")
    args = parser.parse_args(argv)

    from sqlalchemy import text

    from app.brokers.alpaca.adapter import AlpacaAdapter
    from app.brokers.alpaca.credentials import credentials_for_mode
    from app.db.session import get_sessionmaker
    from app.market_data.quotes import get_last_quote
    from app.risk.loss_control.session_baseline import SessionBaselineShadow, resolve_session_date

    now = datetime.now(UTC)
    steps: dict[str, Any] = {}
    cfg = Config.from_env()

    steps["1_instance"] = check_instance(cfg, _instance_id_from_host())
    steps["2_database"] = check_db_path(cfg, os.environ.get("WORKBENCH_DB_URL"))

    sf = get_sessionmaker()
    creds = await credentials_for_mode("paper", cfg.user_id, sf)
    raw_adapter = AlpacaAdapter(creds)
    raw_adapter.connect()
    broker = ReadOnlyBrokerView(raw_adapter)

    account = fetch_account(broker)
    steps["3_identity"] = check_broker_identity(cfg, account)

    broker_positions = {
        str(p.get("symbol")).upper(): D(str(p.get("qty")))
        for p in (broker.get_positions() or [])
        if p.get("qty") is not None
    }
    async with sf() as session:
        db_positions = {
            str(r.ticker).upper(): D(str(r.qty))
            for r in (
                await session.execute(
                    text(
                        "SELECT s.ticker AS ticker, p.qty AS qty FROM positions p "
                        "JOIN symbols s ON s.id = p.symbol_id WHERE p.account_id = :a"
                    ),
                    {"a": cfg.account_id},
                )
            ).fetchall()
        }
        held = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM risk_reservations WHERE account_id = :a AND state = 'HELD'"
                ),
                {"a": cfg.account_id},
            )
        ).scalar() or 0
        limit_rows = [
            dict(r._mapping)
            for r in (
                await session.execute(
                    text(
                        "SELECT user_id, scope_type, scope_id, broker_mode, max_daily_loss, "
                        "max_position_qty, max_position_notional, max_gross_exposure, "
                        "max_orders_per_minute, max_orders_per_day, allow_short, allowed_symbols, "
                        "denied_symbols FROM risk_limits WHERE user_id = :u"
                    ),
                    {"u": cfg.user_id},
                )
            ).fetchall()
        ]
        baseline_rows = [
            dict(r._mapping)
            for r in (
                await session.execute(
                    text(
                        "SELECT id, market_session_date, baseline_equity, captured_at, status "
                        "FROM risk_session_baselines WHERE account_id = :a"
                    ),
                    {"a": cfg.account_id},
                )
            ).fetchall()
        ]

    open_orders = sum(
        1
        for o in (broker.list_orders() or [])
        if str(o.get("status", "")).lower()
        in {"new", "accepted", "pending_new", "partially_filled", "pending_replace", "replaced"}
    )
    steps["4_positions"] = check_positions(cfg, broker_positions, db_positions)
    steps["5_flat"] = check_flat(open_orders, int(held))
    steps["6_limits"] = check_limits(cfg, limit_rows)

    market_open_now: bool | None
    try:
        market_open_now = bool(getattr(broker._client().get_clock(), "is_open", False))
    except Exception as exc:  # noqa: BLE001
        market_open_now = None
        steps["7_session_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    steps["7_session"] = check_session_open(market_open_now, required=args.capture_baseline)

    session_date = resolve_session_date(now)
    existing = select_existing_baseline(baseline_rows, session_date or "")
    if not args.capture_baseline:
        steps["8_baseline"] = {
            "skipped": "read-only precheck; pass --capture-baseline at the eligible open",
            "existing": existing["id"] if existing else None,
        }
    elif existing is not None:
        steps["8_baseline"] = {
            "outcome": "REUSED",
            "baseline_id": existing["id"],
            "baseline_equity": str(existing["baseline_equity"]),
            "note": "the session already has an immutable baseline; it is never replaced",
        }
    else:
        async with sf() as session:
            result = await SessionBaselineShadow(session=session, adapter=raw_adapter).capture(
                account_id=cfg.account_id,
                reconciled_equity=D(str(account.get("equity"))),
                now=now,
            )
            await session.commit()
        steps["8_baseline"] = {
            "outcome": getattr(result, "outcome", str(result)),
            "baseline_equity": str(getattr(result, "baseline_equity", None)),
            "session_date": session_date,
        }

    quotes = {}
    for symbol in cfg.churn_symbols:
        quote = await get_last_quote(symbol)
        quotes[symbol] = _with_age(quote, now)
    last_equity = _decimal_or_none(account.get("last_equity"))
    equity = _decimal_or_none(account.get("equity"))
    day_change = (
        equity - last_equity
        if (equity is not None and last_equity is not None and last_equity > 0)
        else None
    )
    steps["9_reachability"] = assess(
        day_change=day_change,
        quotes=quotes,
        symbols=list(cfg.churn_symbols),
        caps=cfg.caps,
    ).as_dict()
    steps["9_note"] = (
        "day_change is equity - last_equity; a broker that reports no usable last_equity leaves it "
        "UNKNOWN and the verdict INDETERMINATE — it is never treated as zero"
    )

    package = build_package(
        cfg=cfg, steps=steps, captured_at=now, capture_requested=args.capture_baseline
    )
    write_package_atomically(package, args.output)
    print("SESSION_PACKAGE " + json.dumps(package, indent=2, sort_keys=True, default=str))
    return 0


def _with_age(quote: dict[str, Any] | None, now: datetime) -> dict[str, Any] | None:
    if not quote:
        return None
    age = None
    ts = quote.get("ts")
    if ts:
        try:
            age = (now - datetime.fromisoformat(str(ts))).total_seconds()
        except Exception:  # noqa: BLE001 — an unparseable timestamp means unknown age, not fresh
            age = None
    return {"bid": quote.get("bid"), "ask": quote.get("ask"), "age_s": age}


def _decimal_or_none(value: Any) -> D | None:
    if value is None or value == "":
        return None
    try:
        return D(str(value))
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":  # pragma: no cover - entrypoint
    try:
        raise SystemExit(asyncio.run(main()))
    except SessionOpenRefused as refusal:
        print(
            "SESSION_OPEN_REFUSED "
            + json.dumps(
                {"code": refusal.code, "detail": refusal.detail, "diagnostics": refusal.diagnostics},
                indent=2,
                default=str,
            )
        )
        raise SystemExit(2) from None
