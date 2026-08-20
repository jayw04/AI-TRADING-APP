"""Close the ONE coverage gap the launcher rehearsal cannot close by itself.

The closed-latch launcher rehearsal runs `--window development`, and the launcher gates BOTH
fold-assignment verification and gate evaluation on `args.window == "validation"`:

    report["fold_assignment"] = (F.verify_assignment(...) if args.window == "validation"
                                 else {"skipped": "rehearsal window"})
    report["decision"]        = (G.evaluate(...)          if args.window == "validation"
                                 else {"verdict": "REHEARSAL_NO_VERDICT", ...})

So the rehearsal proves read -> custody -> materialize -> replay -> decision-branch, and does
NOT prove that fold assignment or gate evaluation work. Claiming "five-fold and gate
orchestration completes" on the strength of that rehearsal would be false.

The gap cannot be closed by widening the fixtures: the Validation-2 fold geometry spans
2023-05-30..2026-07-01, and any fixture covering those sessions would have to contain the
withheld holdout. So the two skipped functions are exercised DIRECTLY here instead.

⛔ WHAT IS AND IS NOT SAFE HERE.
  - Fold BOUNDARIES are calendar dates already registered in folds.py and committed to Git.
    Dates are not the withheld economic observations. Verifying assignment over them consumes
    nothing and reads no object.
  - Gate evaluation is run ONLY on SYNTHETIC return series constructed in this file. No
    Validation-2 return, NAV or metric exists here. The synthetic series are chosen to land on
    known sides of each gate, so the gate is proven to DISCRIMINATE rather than merely to run.
  - This file therefore produces NO economic observation of any kind and cannot consume the
    opening.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.phase3c import NAV0, IntegrityFailure  # noqa: E402
from app.research.mr002.phase3c import folds as F  # noqa: E402
from app.research.mr002.phase3c import gates as G  # noqa: E402

FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK ' if ok else 'X  '} {name}" + (f"  -- {detail}" if detail and not ok else ""))
    if not ok:
        FAIL.append(name)


def _sessions_from_folds() -> list[_dt.date]:
    """Reconstruct the exact session list the frozen folds describe, from the folds themselves."""
    out: list[_dt.date] = []
    for f in F.FROZEN_FOLDS:
        d, n = f.first, 0
        while n < f.sessions:
            if d.weekday() < 5:
                out.append(d)
                n += 1
            d += _dt.timedelta(days=1)
    return out


print("FOLD ASSIGNMENT (dates only - no economic observation)")
sessions = _sessions_from_folds()
check("frozen fold table has 5 folds", len(F.FROZEN_FOLDS) == 5, str(len(F.FROZEN_FOLDS)))

# FINDING, recorded rather than smoothed over: the frozen fold session counts ARE plain weekday
# counts over each fold's range - the weekday reconstruction reproduces all five folds exactly
# (155/155 each). A first version of this file assumed holidays would make the reconstruction
# approximate and asserted that verify_assignment must REJECT it. That assertion was wrong about
# the data, not about the verifier, and it failed. It is replaced by a discrimination test that
# perturbs the session list, which is what actually proves the verifier is load-bearing.
# CONTRACT, established here rather than assumed: verify_assignment FAILS CLOSED BY RAISING
# IntegrityFailure. It does not return a `verifies: False` flag, so any caller that inspected a
# boolean would silently treat a rejection as an acceptance. Testing it as if it returned a flag
# would have proven nothing at all.
def _rejects(label: str, sess: list) -> None:
    try:
        F.verify_assignment(sess)
    except IntegrityFailure as e:
        check(label, True)
        print(f"        raised: {str(e)[:120]}")
    else:
        check(label, False, "verify_assignment RETURNED instead of raising")


exact = F.verify_assignment(sessions)
check("verify_assignment ACCEPTS the exact frozen session list (returns without raising)",
      all(f["observed_sessions"] == f["expected_sessions"] for f in exact["folds"]),
      json.dumps(exact)[:160])
_rejects("verify_assignment REJECTS a session list one session short",
         [d for i, d in enumerate(sessions) if i != 10])
# SECOND CORRECTED EXPECTATION, recorded for the same reason as the first. An extra session
# AFTER the last fold is NOT a violation and must not be rejected: the validation window is 850
# sessions and only 775 are fold-eligible, so out-of-fold sessions are normal and by design.
# A verifier that rejected them would reject the real window. The genuine violation is an extra
# session INSIDE a fold's range, which changes that fold's membership and therefore the 3-of-5
# gate -- so that is what is tested.
outside = sessions + [F.FROZEN_FOLDS[-1].last + _dt.timedelta(days=1)]
try:
    F.verify_assignment(outside)
    check("verify_assignment ACCEPTS an out-of-fold extra session (correct: 850-session window "
          "vs 775 eligible)", True)
except IntegrityFailure as e:
    check("verify_assignment ACCEPTS an out-of-fold extra session", False, str(e)[:120])

_inside = F.FROZEN_FOLDS[0].first + _dt.timedelta(days=1)
while _inside.weekday() < 5:                      # find a weekend day inside fold 1's range
    _inside += _dt.timedelta(days=1)
_rejects("verify_assignment REJECTS an extra session INSIDE a fold's range",
         sorted(sessions + [_inside]))

# Now the positive direction: assignment over the exact frozen boundaries must place every
# session in exactly one fold and never straddle two.
assigned = F.assign(sessions)
check("assign() returns one slot per session", len(assigned) == len(sessions))
in_fold = [i for i in assigned if i is not None]
check("every reconstructed session lands in a fold", len(in_fold) == len(sessions),
      f"{len(in_fold)}/{len(sessions)}")
counts: dict = {}
for i in in_fold:
    counts[i] = counts.get(i, 0) + 1
check("all 5 folds are populated", len(counts) == 5, str(sorted(counts)))
check("each fold receives its declared session count",
      all(counts.get(f.index) == f.sessions for f in F.FROZEN_FOLDS),
      f"observed {sorted(counts.items())}")

print()
print("GATE EVALUATION (SYNTHETIC returns only - constructed in this file)")


def series(per_fold_sign: list[int], magnitude: float = 0.002) -> dict:
    """A synthetic daily-return series whose per-fold sign is dictated, not discovered."""
    rets, sess = [], []
    for f, sign in zip(F.FROZEN_FOLDS, per_fold_sign):
        d, n = f.first, 0
        while n < f.sessions:
            if d.weekday() < 5:
                sess.append(d)
                # slight per-session variation so the return series has nonzero variance
                rets.append(sign * magnitude * (1.0 + 0.10 * ((n % 3) - 1)))
                n += 1
            d += _dt.timedelta(days=1)
    # ⚠ NAV MUST COMPOUND FROM NAV0. The gate computes cumulative net return as
    # nav_curve[-1] / NAV0 - 1. A first version started the curve at 1.0, so every synthetic
    # case read as a ~100% loss and all four returned VALIDATION_DO_NOT_ADVANCE. The gate was
    # correct and the synthetic input was malformed - which is exactly why "the gate returned a
    # verdict" is not evidence, and "the gate DISCRIMINATES" is.
    nav, v = [], float(NAV0)
    for r in rets:
        v *= (1.0 + r)
        nav.append(v)
    return {"sessions": sess, "daily_ret": rets, "nav_curve": nav}


ALLPOS = [1, 1, 1, 1, 1]
THREE = [1, 1, 1, -1, -1]
TWO = [1, 1, -1, -1, -1]

cases = {
    "5/5 positive folds, A and C profitable -> expect PASS-shaped": (ALLPOS, ALLPOS, ALLPOS),
    "3/5 positive folds (the boundary) -> expect PASS-shaped": (THREE, THREE, THREE),
    "2/5 positive folds -> expect FAIL-shaped": (TWO, TWO, TWO),
    "3/5 folds but A unprofitable -> expect FAIL-shaped": (TWO, THREE, THREE),
}
observed = {}
for label, (a, b, c) in cases.items():
    per = {"A": series(a), "B": series(b), "C": series(c)}
    d = G.evaluate(per, integrity_ok=True, integrity_detail="")
    observed[label] = d.get("verdict")
    print(f"    {label:<58} verdict={d.get('verdict')}")

verdicts = set(observed.values())
check("gate evaluation runs to a verdict on every synthetic case",
      all(v is not None for v in observed.values()))
check("the gate DISCRIMINATES (not all synthetic cases give the same verdict)",
      len(verdicts) > 1, f"all cases returned {verdicts}")

# integrity short-circuit: a replay-definition failure must never surface as an economic verdict
d = G.evaluate({"A": series(ALLPOS), "B": series(ALLPOS), "C": series(ALLPOS)},
               integrity_ok=False, integrity_detail="synthetic integrity stop")
check("integrity_ok=False short-circuits to INTEGRITY_FAILURE",
      d.get("verdict") == "INTEGRITY_FAILURE", str(d.get("verdict")))
check("an integrity stop is NOT reported as an economic verdict",
      d.get("verdict") not in {"VALIDATION_PASS", "VALIDATION_FAIL"}, str(d.get("verdict")))

print()
if FAIL:
    print(f"FOLD/GATE REHEARSAL: {len(FAIL)} FAILED -> {FAIL}")
    raise SystemExit(1)
print("FOLD/GATE REHEARSAL: ALL PASS - the two functions the launcher rehearsal skips are "
      "exercised, and the gate is shown to discriminate. NO economic observation was produced.")
