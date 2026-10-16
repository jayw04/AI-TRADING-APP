"""Fixed circular-shift set for the BREADTH-CN-001-D primary null (SPEC amendment A1, section 1).

The dev-segment setup dates are rotated by k sessions with wrap-around.  k is drawn WITHOUT replacement from
[MIN_SHIFT, L - MIN_SHIFT], so the circular distance from the identity is at least MIN_SHIFT sessions in both directions
(|shift| < MIN_SHIFT excluded).  L is the number of exchange sessions in the dev segment.  The set depends only on
(L, n, MIN_SHIFT, SEED), so it is generated and committed BEFORE any outcome exists; nothing here touches prices.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

N_SHIFTS = 500
MIN_SHIFT = 20
SEED = 20261016  # fixed 2026-10-16
DEV_START, DEV_END = "2016-10-17", "2023-12-31"


def shift_set(
    length: int, n: int = N_SHIFTS, min_shift: int = MIN_SHIFT, seed: int = SEED
) -> list[int]:
    lo, hi = min_shift, length - min_shift
    if hi - lo + 1 < n:
        raise ValueError("not enough admissible shifts")
    rng = np.random.default_rng(seed)
    return sorted(int(k) for k in rng.choice(np.arange(lo, hi + 1), size=n, replace=False))


def digest(shifts: list[int], length: int) -> str:
    blob = f"L={length};min={MIN_SHIFT};seed={SEED};" + ",".join(map(str, shifts))
    return hashlib.sha256(blob.encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calendar-csv", required=True, help="exchange sessions, column 'date'")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cal = pd.to_datetime(pd.read_csv(a.calendar_csv)["date"].astype(str))
    length = int(((cal >= DEV_START) & (cal <= DEV_END)).sum())
    s = shift_set(length)
    Path(a.out).write_text("shift\n" + "\n".join(map(str, s)) + "\n", encoding="utf-8")
    print(
        f"L={length} sessions in {DEV_START}..{DEV_END}; {len(s)} shifts in [{s[0]}, {s[-1]}]; sha256={digest(s, length)}"
    )


if __name__ == "__main__":
    main()
