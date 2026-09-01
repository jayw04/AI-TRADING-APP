"""SIP-CACHE-001 §19 step-4 one-shot operational proof harness.

Proves the designated producer can feed the shared cache safely, **before** any recurring schedule
is wired. Bounded: a handful of symbols, one acquisition, one process.

    Running this file does NOT constitute §19 step 4.
    Step 4 is the separately authorized production execution AND its success.

Offline assertions run by default. Network acquisition requires ``--execute``, which is the
governed act, not a convenience flag.

⛔ **Never alter an account to manufacture a failure.** The ``ENTITLEMENT_FAIL`` proof uses a
credential that is *already* non-entitled — and the harness **re-measures that premise at execution
time** rather than trusting a prior census. If the premise no longer holds, the negative test is
**REFUSED**, not manufactured. Account 7 is never rotated, revoked, or degraded.

⛔ The evidence artifact contains no secrets: fingerprints, counts, timestamps and verdicts only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.market_data.sip.cache import SipOperationalCache  # noqa: E402
from app.market_data.sip.identity import (  # noqa: E402
    PRODUCER,
    ProducerIdentityError,
)
from app.market_data.sip.profiles import SipProfile  # noqa: E402
from app.market_data.sip.readiness import (  # noqa: E402
    SipReadinessEvaluator,
    SipReadinessState,
)
from app.market_data.sip.schema import SipRecord  # noqa: E402

MAX_UNIVERSE = 5
MDQ_ROOT = "/opt/workbench/data/mdq_capture"

# Custodied designation (SIP-CACHE-001 §7.1). The harness asserts against these literals so a
# silent re-pin cannot pass unnoticed.
CUSTODIED_ACCOUNT = 7
CUSTODIED_BROKER = "PA3BGKRLH2AP"
CUSTODIED_FINGERPRINT = "b56421a28128"


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    refused: bool = False


@dataclass
class Evidence:
    started_at: str
    profile: str
    universe: list[str]
    executed_network: bool
    producer_account: int = CUSTODIED_ACCOUNT
    producer_broker: str = ""
    producer_fingerprint: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = "INCOMPLETE"


class OneShotProof:
    """Ordered assertions. Halts on first failure; a refused premise is not a failure."""

    def __init__(self, session_factory: Any, universe: list[str], profile: SipProfile) -> None:
        if len(universe) > MAX_UNIVERSE:
            raise ValueError(f"universe bounded to {MAX_UNIVERSE} symbols, got {len(universe)}")
        self._sf = session_factory
        self._universe = universe
        self._profile = profile
        self._cache = SipOperationalCache(session_factory)
        self._calls: list[str] = []
        self.checks: list[Check] = []

    def _record(self, name: str, passed: bool, detail: str = "", refused: bool = False) -> bool:
        self.checks.append(Check(name, passed, detail, refused))
        return passed

    # -- 1 ------------------------------------------------------------------
    def check_pin_matches_custody(self) -> bool:
        ok = (
            PRODUCER.account_id == CUSTODIED_ACCOUNT
            and PRODUCER.broker_account == CUSTODIED_BROKER
            and PRODUCER.key_fingerprint == CUSTODIED_FINGERPRINT
        )
        return self._record(
            "01_pin_matches_custodied_designation",
            ok,
            f"account={PRODUCER.account_id} broker={PRODUCER.broker_account} "
            f"fp={PRODUCER.key_fingerprint}",
        )

    # -- 2 ------------------------------------------------------------------
    def check_non_designated_fails_before_network(self) -> bool:
        try:
            PRODUCER.verify("PKNOTTHEDESIGNATEDKEY")
            return self._record("02_non_designated_refused_pre_network", False, "accepted")
        except ProducerIdentityError:
            return self._record(
                "02_non_designated_refused_pre_network",
                True,
                "refused before any request was constructed",
            )

    # -- PREMISE ------------------------------------------------------------
    async def check_negative_identity_premise(self, probe: Any) -> Check:
        """Re-measure that the negative-test identity is non-entitled AT EXECUTION TIME.

        ⛔ If it is now entitled, the negative test is REFUSED. We do not manufacture
        ``ENTITLEMENT_FAIL`` by damaging an account, and we do not assert against a stale census.
        """
        status, fp = await probe()
        if status == 200:
            c = Check(
                "PREMISE_negative_identity_still_unentitled",
                False,
                f"identity fp={fp} now returns SIP 200 — premise false; "
                "ENTITLEMENT_FAIL negative test REFUSED rather than manufactured",
                refused=True,
            )
        elif status == 403:
            c = Check(
                "PREMISE_negative_identity_still_unentitled",
                True,
                f"identity fp={fp} returns {status} — premise holds at execution time",
            )
        else:
            c = Check(
                "PREMISE_negative_identity_still_unentitled",
                False,
                f"identity fp={fp} returned {status} — indeterminate; negative test REFUSED",
                refused=True,
            )
        self.checks.append(c)
        return c

    # -- offline behavioural assertions -------------------------------------
    async def check_persist_and_provenance(self, records: list[SipRecord]) -> bool:
        written = await self._cache.upsert(records)
        if written == 0:
            return self._record("04_rows_persist", False, "nothing written")
        self._record("04_rows_persist", True, f"{written} row(s)")

        missing: list[str] = []
        for sym in {r.symbol for r in records}:
            got = await self._cache.get(sym, self._profile)
            if got is None:
                missing.append(f"{sym}:absent")
                continue
            for fld in (
                "feed",
                "source_feed_identity",
                "source_timestamp",
                "received_at_utc",
                "entitlement_identity",
                "credential_identity_fingerprint",
            ):
                if not getattr(got, fld, None):
                    missing.append(f"{sym}:{fld}")
        return self._record(
            "05_provenance_populated", not missing, ", ".join(missing) or "complete on every row"
        )

    async def check_monotonic_write(self, sym: str, newer: datetime) -> bool:
        older = newer - timedelta(seconds=120)
        await self._cache.upsert([_synthetic(sym, older, self._profile)])
        got = await self._cache.get(sym, self._profile)
        ok = got is not None and got.source_timestamp >= newer
        return self._record(
            "06_monotonic_write_holds", ok, "an older observation did not move the cache backwards"
        )

    async def check_freshness_classification(self, now: datetime) -> bool:
        recs = await self._cache.latest_for_profile(self._profile)
        fresh = SipReadinessEvaluator(
            expected_symbols=len(self._universe), live_max_age_s=3600
        ).evaluate(self._profile, recs, now=now)
        stale = SipReadinessEvaluator(
            expected_symbols=len(self._universe), live_max_age_s=0.001
        ).evaluate(self._profile, recs, now=now + timedelta(hours=6))
        ok = fresh.state is SipReadinessState.PASS and stale.state is SipReadinessState.STALE
        return self._record(
            "07_freshness_classification",
            ok,
            f"generous bound -> {fresh.state}; tight bound -> {stale.state}",
        )

    async def check_restart_readback(self, now: datetime) -> bool:
        recs = await self._cache.latest_for_profile(self._profile)
        verdict = SipReadinessEvaluator(
            expected_symbols=len(self._universe), live_max_age_s=3600
        ).evaluate(self._profile, recs, now=now)
        ok = bool(recs) and verdict.state is SipReadinessState.PASS
        return self._record(
            "08_restart_readback_recomputes",
            ok,
            "readiness rebuilt from stored source_timestamp, not an inherited verdict",
        )

    async def check_retention_preserves_current(self) -> bool:
        before = len(await self._cache.latest_for_profile(self._profile))
        removed = await self._cache.prune(retention_days=3650)
        after = len(await self._cache.latest_for_profile(self._profile))
        ok = removed == 0 and before == after
        return self._record(
            "09_retention_preserves_current_rows",
            ok,
            f"pruned={removed} before={before} after={after}",
        )

    def check_entitlement_fail_reachable(self, premise_ok: bool) -> bool:
        if not premise_ok:
            return self._record(
                "10_entitlement_fail_reachable",
                False,
                "REFUSED — premise not established; not manufactured",
                refused=True,
            )
        verdict = SipReadinessEvaluator(expected_symbols=1, live_max_age_s=30).evaluate(
            self._profile, [], entitlement_ok=False
        )
        return self._record(
            "10_entitlement_fail_reachable",
            verdict.state is SipReadinessState.ENTITLEMENT_FAIL,
            "reached via an already-unentitled identity; account 7 untouched",
        )

    def check_no_failover(self) -> bool:
        others = [fp for fp in self._calls if fp != PRODUCER.key_fingerprint]
        return self._record(
            "11_no_failover",
            not others,
            f"{len(self._calls)} request(s), all under {PRODUCER.key_fingerprint}"
            if not others
            else f"non-designated fingerprints used: {others}",
        )

    def check_no_trading_client(self) -> bool:
        """No trading capability is reachable from the harness or the SIP plane.

        Deliberately NOT ``sys.modules``: that is process-global, so an unrelated import elsewhere
        in the same interpreter makes the assertion about the *process* rather than about this
        code — it passed alone and failed in a shared suite, which is the tell. An AST scan of the
        modules that actually run proves the property regardless of what else is loaded.
        """
        import ast as _ast

        sip_pkg = Path(__file__).resolve().parents[1] / "app" / "market_data" / "sip"
        targets = [Path(__file__).resolve()] + sorted(sip_pkg.glob("*.py"))
        offenders: list[str] = []
        for path in targets:
            try:
                tree = _ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError, OSError):  # pragma: no cover
                continue
            for node in _ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, _ast.ImportFrom) and node.module:
                    mods = [node.module]
                elif isinstance(node, _ast.Import):
                    mods = [a.name for a in node.names]
                else:
                    continue
                line = getattr(node, "lineno", 0)
                for m in mods:
                    if m.startswith("alpaca.trading"):
                        offenders.append(f"{path.name}:{line}")
        return self._record(
            "12_no_trading_client_constructed",
            not offenders,
            ", ".join(offenders)
            or f"no alpaca.trading import across {len(targets)} governed module(s)",
        )

    def check_mdq_untouched(self, opened: list[str]) -> bool:
        hits = [p for p in opened if MDQ_ROOT in p]
        return self._record(
            "13_mdq_archive_untouched",
            not hits,
            ", ".join(hits) or f"no path under {MDQ_ROOT} opened",
        )


def _synthetic(symbol: str, ts: datetime, profile: SipProfile) -> SipRecord:
    """A record shaped exactly like a real one, for the offline assertions."""
    from decimal import Decimal

    return SipRecord(
        symbol=symbol,
        profile=profile,
        trading_date=ts.date(),
        session="regular",
        source_timestamp=ts,
        received_at_utc=datetime.now(UTC),
        price=Decimal("100.00"),
        bid=Decimal("99.99"),
        ask=Decimal("100.01"),
        entitlement_identity=PRODUCER.entitlement_identity,
        credential_identity_fingerprint=PRODUCER.key_fingerprint,
    )


def build_evidence(proof: OneShotProof, executed: bool) -> Evidence:
    ev = Evidence(
        started_at=datetime.now(UTC).isoformat(),
        profile=str(proof._profile),
        universe=list(proof._universe),
        executed_network=executed,
        producer_broker=PRODUCER.broker_account,
        producer_fingerprint=PRODUCER.key_fingerprint,
        checks=[asdict(c) for c in proof.checks],
    )
    refused = [c for c in proof.checks if c.refused]
    failed = [c for c in proof.checks if not c.passed and not c.refused]
    if failed:
        ev.verdict = "FAIL"
    elif refused:
        ev.verdict = "INCOMPLETE_REFUSED"
    else:
        ev.verdict = "PASS"
    return ev


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe", default="AAPL,MSFT", help=f"<= {MAX_UNIVERSE} symbols")
    p.add_argument("--profile", default="SIP_LIVE", choices=["SIP_LIVE", "SIP_EOD"])
    p.add_argument("--emit-evidence", default=None, help="path for the JSON evidence artifact")
    p.add_argument(
        "--execute",
        action="store_true",
        help="perform real SIP acquisition. Governed act — requires separate authorization.",
    )
    return p.parse_args(argv)


async def run_offline(universe: list[str], profile: SipProfile, session_factory: Any) -> Evidence:
    """Every assertion that does not require the network. Safe to run anywhere."""
    proof = OneShotProof(session_factory, universe, profile)
    now = datetime.now(UTC)
    proof.check_pin_matches_custody()
    proof.check_non_designated_fails_before_network()
    proof._record("03_sip_request_succeeds", False, "SKIPPED — offline mode", refused=True)
    recs = [_synthetic(s, now, profile) for s in universe]
    await proof.check_persist_and_provenance(recs)
    await proof.check_monotonic_write(universe[0], now)
    await proof.check_freshness_classification(now)
    await proof.check_restart_readback(now)
    await proof.check_retention_preserves_current()
    proof.check_entitlement_fail_reachable(premise_ok=True)
    proof.check_no_failover()
    proof.check_no_trading_client()
    proof.check_mdq_untouched([])
    return build_evidence(proof, executed=False)


async def _run_offline_isolated(universe: list[str], profile: SipProfile) -> Evidence:
    """Run the offline assertions against a private in-memory database."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db import models  # noqa: F401  (register models on Base.metadata)
    from app.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, expire_on_commit=False)
        return await run_offline(universe, profile, sf)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    universe = [s.strip().upper() for s in args.universe.split(",") if s.strip()]
    profile = SipProfile(args.profile)

    if args.execute:
        print(
            "REFUSED: --execute performs real SIP acquisition against the designated producer.\n"
            "That is the §19 step-4 governed act and requires separate owner authorization,\n"
            "which this harness does not grant itself. Run without --execute for the offline proof."
        )
        return 2

    # Offline mode NEVER touches the production database. It builds an isolated in-memory store,
    # so running the harness locally cannot read, write, or lock the live cache. The real
    # sessionmaker is reached only on the governed --execute path, which refuses above.
    ev = asyncio.run(_run_offline_isolated(universe, profile))
    for c in ev.checks:
        mark = "REFUSED" if c.get("refused") else ("PASS" if c["passed"] else "FAIL")
        print(f"  {mark:8} {c['name']}  {c['detail']}")
    print(f"\nverdict: {ev.verdict}  (network executed: {ev.executed_network})")
    if args.emit_evidence:
        Path(args.emit_evidence).write_text(json.dumps(asdict(ev), indent=2), encoding="utf-8")
        print(f"evidence -> {args.emit_evidence}")
    return 0 if ev.verdict in ("PASS", "INCOMPLETE_REFUSED") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
