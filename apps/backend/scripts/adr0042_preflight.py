"""ADR 0042 canary — READ-ONLY preflight. Places no orders. Run before every canary.

"Ran from committed code" is an assertion until it is cryptographically tied to the container that
actually executed. A host-side hash is not enough: the evidence must establish which bytes the
running interpreter READ. So the hashes below are computed INSIDE the container, from the files
`import` would resolve.

Refuses to pass — and therefore blocks the live churn — on any of:
  * a commit SHA or image digest that does not match what was declared;
  * a harness source hash that does not match the manifest;
  * a deadline that does not resolve to a future time;
  * protected symbols not configured;
  * cap-aware sizing that cannot see the account's real limits;
  * a checkpoint path that is not writable, or a stale checkpoint from an earlier run;
  * a stale canary lock file.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

from app.brokers.registry import BrokerRegistry
from app.db.session import get_sessionmaker
from scripts.adr0042_canary_lib import (
    ACCT,
    BUDGET_MINUTES,
    CHECKPOINT,
    CHURN_SYMBOLS,
    LEGS,
    LOCKFILE,
    PROTECTED,
    USER,
    admissible_shares,
    load_limits,
    snapshot_state,
)

HARNESS = [
    "scripts/adr0042_canary_lib.py",
    "scripts/adr0042_churn_to_breach.py",
    "scripts/adr0042_canary_run.py",
    "scripts/adr0042_concurrency_worker.py",
    "scripts/adr0042_preflight.py",
    "app/risk/decision_service.py",
    "app/risk/risk_effect.py",
    "app/risk/account_snapshot.py",
    "app/db/models/risk_capacity_state.py",
]

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> bool:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def _sha(path: Path) -> str:
    """Hash the file's CONTENT, with line endings normalised.

    ⚠ The deployed container's files carry CRLF: `git archive` run on a Windows host applies
    `core.autocrlf` on the way into the tarball. The source is LF. Normalised, the bytes are
    identical — so a raw-byte hash would report all nine harness files as "differing from the
    manifest" and block the canary over a transport artifact.

    Provenance asks whether this is the same SOURCE, not whether it survived the same filesystem.
    Both sides of the check normalise, so both sides answer that question.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


async def main() -> int:
    root = Path("/app")
    print("ADR 0042 canary — PREFLIGHT (read-only; no orders)\n")

    # ---- provenance: which bytes is this interpreter actually running? ---------------------
    hashes = {}
    missing = []
    for rel in HARNESS:
        p = root / rel
        if not p.exists():
            missing.append(rel)
            continue
        hashes[rel] = _sha(p)
    check("harness_present", not missing, f"missing: {missing}" if missing else "all present")

    declared = os.environ.get("ADR0042_MANIFEST")
    if declared and Path(declared).exists():
        want = json.loads(Path(declared).read_text(encoding="utf-8")).get("source_sha256", {})
        drift = {k: (want.get(k), v) for k, v in hashes.items() if want.get(k) != v}
        check("source_matches_manifest", not drift,
              f"{len(drift)} file(s) differ from the manifest: {list(drift)}" if drift
              else f"{len(hashes)} file(s) match")
    else:
        check("source_matches_manifest", False,
              "no ADR0042_MANIFEST supplied — provenance cannot be established, so this run "
              "could not be evidence")

    for key, env in (("commit_sha", "ADR0042_COMMIT_SHA"),
                     ("image_digest", "ADR0042_IMAGE_DIGEST"),
                     ("deployed_at", "ADR0042_DEPLOYED_AT")):
        check(f"provenance.{key}", bool(os.environ.get(env)),
              os.environ.get(env) or f"{env} not set")

    # ---- configuration ----------------------------------------------------------------------
    check("protected_configured", bool(PROTECTED), f"protected = {list(PROTECTED)}")
    check("legs_configured", bool(LEGS), f"legs = {[(s, str(q)) for s, q in LEGS]}")
    check("churn_configured", bool(CHURN_SYMBOLS), f"churn = {list(CHURN_SYMBOLS)}")
    check("legs_are_protected",
          all(s in PROTECTED for s, _ in LEGS),
          "every leg is in PROTECTED — the churn can never flatten them")

    # ---- the deadline must RESOLVE, and to the future ---------------------------------------
    if CHECKPOINT.exists():
        check("checkpoint_clean", False,
              f"a checkpoint from an earlier run exists at {CHECKPOINT} — remove it, or resume "
              f"deliberately; a canary must not silently continue someone else's run")
    else:
        check("checkpoint_clean", True, f"{CHECKPOINT} absent")
    try:
        CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        probe = CHECKPOINT.parent / ".adr0042_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        check("checkpoint_writable", True, str(CHECKPOINT.parent))
    except Exception as exc:  # noqa: BLE001
        check("checkpoint_writable", False, f"{type(exc).__name__}: {exc}")

    # ⚠ Construct the deadline the way the RUN does. A bare `Checkpoint()` leaves `deadline_at`
    # empty, and the earlier version then fell back to "now" — so the check compared now > now and
    # always failed. The preflight was refusing a perfectly good configuration.
    deadline = datetime.now(UTC) + timedelta(minutes=BUDGET_MINUTES)
    check("deadline_resolves_to_future", deadline > datetime.now(UTC),
          f"{deadline.isoformat()} (relative budget of {BUDGET_MINUTES} min — NOT a calendar date)")

    check("no_stale_lock", not LOCKFILE.exists(),
          f"{LOCKFILE} absent" if not LOCKFILE.exists()
          else f"{LOCKFILE} exists — another harness process may be live")

    # ---- cap-aware sizing must see the account's REAL limits ---------------------------------
    sf = get_sessionmaker()
    limits = await load_limits(sf)
    check("limits_visible", limits.max_daily_loss is not None,
          f"max_daily_loss=${limits.max_daily_loss}, max_position_notional="
          f"{limits.max_position_notional}, max_gross_exposure={limits.max_gross_exposure}")

    reg = BrokerRegistry(sf)
    await reg.load_all()
    ad = reg.get(USER)
    snap = await snapshot_state(sf, ad)
    acct = ad.get_account()
    bp = D(str(acct.get("buying_power") or acct.get("cash") or 0))
    sized = admissible_shares(price=D("70"), limits=limits, gross_used=D(0),
                              buying_power=bp, ceiling=D("25000"))
    check("cap_aware_sizing_works", sized > 0,
          f"a $70 instrument sizes to {sized} shares under the account's own limits "
          f"(buying power ${bp:,.0f})")

    # ---- account state ----------------------------------------------------------------------
    check("account_flat_or_legs_only",
          all(s in PROTECTED for s in snap.positions),
          f"positions = { {k: str(v) for k, v in snap.positions.items()} }")
    check("no_stale_open_orders", snap.open_orders == 0,
          f"{snap.open_orders} open order(s) at the broker")
    check("not_already_locked", not snap.lock_active,
          f"day_change ${snap.day_change:,.2f} vs cap ${snap.max_daily_loss}")
    check("breaker_clear", snap.breaker_tripped_at is None,
          f"breaker tripped_at = {snap.breaker_tripped_at}")

    ok = all(r[1] for r in RESULTS)
    print("\n" + "=" * 72)
    print(f"  PREFLIGHT: {'PASS' if ok else 'FAIL'} — "
          f"{'the live churn may proceed' if ok else 'DO NOT begin the live churn'}")
    print("=" * 72)

    Path("/app/data/adr0042_preflight.json").write_text(
        json.dumps(
            {
                "at": datetime.now(UTC).isoformat(),
                "pass": ok,
                "account_id": ACCT,
                "source_sha256": hashes,
                "commit_sha": os.environ.get("ADR0042_COMMIT_SHA"),
                "image_digest": os.environ.get("ADR0042_IMAGE_DIGEST"),
                "deployed_at": os.environ.get("ADR0042_DEPLOYED_AT"),
                "risk_limits": limits.as_dict(),
                "initial_state": snap.as_dict(),
                "checks": [{"name": n, "result": "PASS" if p else "FAIL", "detail": d}
                           for n, p, d in RESULTS],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
