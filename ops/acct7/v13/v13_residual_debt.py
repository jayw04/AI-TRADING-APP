"""RESIDUAL_CLEANUP_REQUIRED - first-class operational debt for permitted residuals.

Transition Protocol v2, owner ruling 2026-08-21:

    "A permitted residual must create a first-class RESIDUAL_CLEANUP_REQUIRED obligation.
     The residual must be carried into subsequent planning and must never disappear
     because the symbol later re-enters the target universe."

WHY THIS MODULE EXISTS AT ALL
----------------------------
Before v2 a refused exit vanished from the record the moment the next manifest was
generated: the planner sizes from CURRENT holdings, so a name that failed to exit simply
looked like a name we still wanted. The conflict is not hypothetical - TSM was exited on
2026-08-20 (seq 3, filled) and bought back on 2026-08-21 (seq 42). Had that exit been
refused instead of filled, the residual would silently have become an intended holding
with no record that it was ever meant to leave the book.

DESIGN
------
* Append-only JSONL. Never rewritten in place; a status change appends a new event and
  the current state is folded from the event stream. That keeps the file safe to read
  concurrently and makes the history auditable.
* This module NEVER trades and NEVER imports the order path. It records and reads.
* An open obligation is advisory to planning and disclosure, not a block. Per the owner
  ruling it "should not trigger an ungoverned manual trade and should not automatically
  block /start if the amended protocol explicitly permits that residual".
"""
import json
import os
from datetime import datetime, UTC
from pathlib import Path

DEBT_PATH = Path("/app/data/ops/acct7/residual_debt.jsonl")

OBLIGATION = "RESIDUAL_CLEANUP_REQUIRED"
STATUS_OPEN = "OPEN"

# ---- terminal statuses (owner ruling 2026-08-21, ADR 0054 review) ---------------------
# An obligation leaves OPEN only into one of these, and only by an APPENDED event.
STATUS_RESOLVED_FILLED = "RESOLVED_FILLED"
STATUS_RESOLVED_TARGET_REENTERED = "RESOLVED_TARGET_REENTERED_WITH_OWNER_ACCEPTANCE"
STATUS_SUPERSEDED_BY_PLAN = "SUPERSEDED_BY_NEW_GOVERNED_PLAN"
STATUS_ESCALATED = "ESCALATED"

TERMINAL_STATUSES = (STATUS_RESOLVED_FILLED, STATUS_RESOLVED_TARGET_REENTERED,
                     STATUS_SUPERSEDED_BY_PLAN, STATUS_ESCALATED)

# The one that needs a guard. A residual symbol re-entering the target universe does NOT
# close its obligation: the owner must accept it explicitly, and the acceptance reference is
# recorded. Without that guard the position stops being a residual we owe a decision on and
# starts looking like a position we chose - the exact disappearance this ledger prevents.
STATUSES_REQUIRING_OWNER_ACCEPTANCE = (STATUS_RESOLVED_TARGET_REENTERED,)

# Exactly the fields the owner ruling requires, in the order it lists them.
REQUIRED_FIELDS = (
    "strategy_id",
    "account_id",
    "originating_manifest_run_id",
    "originating_manifest_sha256",
    "symbol",
    "residual_qty",
    "governed_residual_valuation_usd",
    "abort_reason",
    "originating_stage",
    "recorded_at_utc",
    "target_disposition",
    "status",
)


def _iso():
    return datetime.now(UTC).isoformat()


def _append(path, rec):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(rec, default=str, sort_keys=True) + "\n")
    try:
        os.chmod(path, 0o644)
    except OSError:
        pass
    return rec


def build(*, strategy_id, account_id, run_id, manifest_sha256, stage, disposition,
          target_disposition="clear_at_next_governed_rebalance"):
    """Build one obligation from a residual-ledger order disposition."""
    return {
        "record": OBLIGATION,
        "schema_version": 1,
        "strategy_id": strategy_id,
        "account_id": account_id,
        "originating_manifest_run_id": run_id,
        "originating_manifest_sha256": manifest_sha256,
        "symbol": disposition["symbol"],
        "side_not_completed": disposition.get("side"),
        "intended_qty": disposition.get("intended_qty"),
        "filled_qty": disposition.get("filled_qty"),
        "residual_qty": disposition.get("residual_qty"),
        "governed_residual_valuation_usd": disposition.get("residual_notional"),
        "residual_valuation_price": disposition.get("residual_valuation_price"),
        "abort_reason": disposition.get("abort_reason"),
        "failure_class": disposition.get("failure_class"),
        "originating_stage": stage,
        "final_disposition": disposition.get("final_disposition"),
        "recorded_at_utc": _iso(),
        "target_disposition": target_disposition,
        "status": STATUS_OPEN,
    }


def record_many(obligations, path=None):
    # Resolved at CALL time, never bound as a default: a default argument would
    # capture DEBT_PATH at import and no caller could ever redirect it - including a
    # conformance suite, which must never write into the governed ledger.
    path = path or DEBT_PATH
    for o in obligations:
        missing = [f for f in REQUIRED_FIELDS if f not in o]
        if missing:
            raise ValueError(
                "%s is missing owner-required field(s) %s" % (OBLIGATION, missing))
        _append(path, o)
    return len(obligations)


def _events(path=None):
    path = path or DEBT_PATH
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _key(e):
    return (e.get("originating_manifest_run_id"), e.get("symbol"),
            e.get("originating_stage"))


def current(path=None):
    """Fold the append-only stream into current state, latest event per obligation."""
    path = path or DEBT_PATH
    state = {}
    for e in _events(path):
        state[_key(e)] = e
    return list(state.values())


def open_obligations(account_id=None, strategy_id=None, path=None):
    """Every obligation still OPEN. This is what planning must carry forward.

    NOTE the deliberate absence of any symbol filter. An obligation is keyed by the
    manifest that created it, never by whether the symbol is currently held or currently
    targeted - that is exactly the disappearance the owner ruling forbids.
    """
    rows = [e for e in current(path) if e.get("status") == STATUS_OPEN]
    if account_id is not None:
        rows = [e for e in rows if e.get("account_id") == account_id]
    if strategy_id is not None:
        rows = [e for e in rows if e.get("strategy_id") == strategy_id]
    return sorted(rows, key=lambda e: (e.get("recorded_at_utc") or "", e.get("symbol") or ""))


def total_open_usd(account_id=None, strategy_id=None, path=None):
    path = path or DEBT_PATH
    return round(sum(float(e.get("governed_residual_valuation_usd") or 0.0)
                     for e in open_obligations(account_id, strategy_id, path)), 2)


def close(obligation, *, status, note=None, cleared_by=None,
          owner_acceptance_ref=None, path=None):
    """Append a closing event. The original OPEN event is never rewritten.

    `status` is REQUIRED and has no default: closing an obligation is a governed disposition,
    and a default would let a caller close one without saying how it was discharged.
    """
    path = path or DEBT_PATH
    if status not in TERMINAL_STATUSES:
        raise ValueError(
            "status must be one of %s, got %r. An obligation leaves OPEN only into an "
            "explicit terminal disposition." % (list(TERMINAL_STATUSES), status))
    if status in STATUSES_REQUIRING_OWNER_ACCEPTANCE and not owner_acceptance_ref:
        raise ValueError(
            "%s requires owner_acceptance_ref. OWNER RULING 2026-08-21: a residual symbol "
            "re-entering the target universe does NOT close its obligation; closing it that "
            "way needs a recorded owner acceptance." % status)
    rec = {**obligation, "status": status, "closed_at_utc": _iso(),
           "close_note": note, "cleared_by": cleared_by,
           "owner_acceptance_ref": owner_acceptance_ref}
    return _append(path, rec)


def health(path=None):
    """Activation invariant: the ledger must be present-or-creatable and parseable.

    Fail-closed: an invariant that cannot be EVALUATED counts as failed, so an unreadable or
    corrupt ledger is a problem rather than an empty one.
    """
    path = Path(path or DEBT_PATH)
    out = {"path": str(path), "exists": path.exists(), "writable": None,
           "parseable": None, "lines": 0, "bad_lines": 0, "open_obligations": None,
           "healthy": False, "problem": None}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a"):
            pass
        os.chmod(path, 0o644)
        out["writable"] = True
    except OSError as exc:
        out["writable"] = False
        out["problem"] = "not writable: %s" % exc
        return out
    bad = 0
    n = 0
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        n += 1
        try:
            json.loads(line)
        except ValueError:
            bad += 1
    out["lines"], out["bad_lines"] = n, bad
    out["parseable"] = bad == 0
    if bad:
        out["problem"] = ("%d unparseable line(s) - the ledger is append-only and must never "
                          "be hand-edited" % bad)
        return out
    out["open_obligations"] = len(open_obligations(path=path))
    out["healthy"] = True
    return out


def summary_for_disclosure(account_id=None, strategy_id=None, path=None):
    """The block the C40 epoch-boundary record must disclose at activation."""
    path = path or DEBT_PATH
    rows = open_obligations(account_id, strategy_id, path)
    return {
        "obligation": OBLIGATION,
        "open_count": len(rows),
        "total_open_usd": total_open_usd(account_id, strategy_id, path),
        "symbols": sorted({r["symbol"] for r in rows}),
        "detail": rows,
        "disclosure_rule": ("Transition Protocol v2 requires the C40 epoch-boundary record "
                            "to disclose any residual operational debt present at "
                            "activation."),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=OBLIGATION + " ledger (read-only CLI)")
    ap.add_argument("--path", default=str(DEBT_PATH))
    ap.add_argument("--account-id", type=int, default=None)
    ap.add_argument("--strategy-id", type=int, default=None)
    a = ap.parse_args()
    s = summary_for_disclosure(a.account_id, a.strategy_id, Path(a.path))
    print(json.dumps(s, indent=1, default=str))
